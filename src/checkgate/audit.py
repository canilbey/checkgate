from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from checkgate.models import AuditResult, Finding, Workflow


class AuditInputError(ValueError):
    """Raised when local audit inputs cannot be read safely."""


class GithubActionsLoader(yaml.SafeLoader):
    """YAML loader that does not turn the GitHub Actions `on` key into True."""


# Copy before editing so importing checkgate never changes PyYAML's global SafeLoader.
GithubActionsLoader.yaml_implicit_resolvers = {
    key: list(resolvers)
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for first_char, resolvers in list(GithubActionsLoader.yaml_implicit_resolvers.items()):
    GithubActionsLoader.yaml_implicit_resolvers[first_char] = [
        resolver
        for resolver in resolvers
        if resolver[0] != "tag:yaml.org,2002:bool"
    ]


def _triggers(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {value: None}
    if isinstance(value, list):
        return {str(item): None for item in value}
    if isinstance(value, dict):
        return {str(key): config for key, config in value.items()}
    return {}


def load_workflow(path: Path) -> Workflow:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=GithubActionsLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AuditInputError(f"cannot parse workflow {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AuditInputError(f"workflow {path} must contain a YAML mapping")

    jobs = raw.get("jobs", {})
    if jobs is None:
        jobs = {}
    if not isinstance(jobs, dict):
        raise AuditInputError(f"workflow {path} has a non-mapping 'jobs' value")

    contexts: list[str] = []
    dynamic: list[str] = []
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        value = job.get("name", job_id)
        if not isinstance(value, str):
            continue
        strategy = job.get("strategy")
        has_matrix = isinstance(strategy, dict) and "matrix" in strategy
        if "${{" in value or has_matrix:
            dynamic.append(value)
        else:
            contexts.append(value)

    return Workflow(
        path=path,
        name=str(raw.get("name", path.stem)),
        triggers=_triggers(raw.get("on")),
        contexts=tuple(contexts),
        dynamic_contexts=tuple(dynamic),
    )


def discover_workflows(directory: Path) -> list[Workflow]:
    if not directory.is_dir():
        raise AuditInputError(f"workflow directory does not exist: {directory}")
    paths = sorted({*directory.glob("*.yml"), *directory.glob("*.yaml")})
    if not paths:
        raise AuditInputError(f"no .yml or .yaml workflows found in: {directory}")
    return [load_workflow(path) for path in paths]


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _rename_candidate(required: str, emitted: Iterable[str]) -> str | None:
    target = _normalized(required)
    scored = [
        (difflib.SequenceMatcher(None, target, _normalized(candidate)).ratio(), candidate)
        for candidate in emitted
        if candidate != required
    ]
    if not scored:
        return None
    score, candidate = max(scored, key=lambda item: (item[0], item[1]))
    return candidate if score >= 0.78 else None


def audit(
    workflows: list[Workflow],
    required_contexts: Iterable[str],
    *,
    require_merge_group: bool = False,
) -> AuditResult:
    required = tuple(dict.fromkeys(item.strip() for item in required_contexts if item.strip()))
    if not required:
        raise AuditInputError("at least one required check context must be supplied")

    emitted = tuple(sorted({ctx for workflow in workflows for ctx in workflow.contexts}))
    dynamic_workflows = [workflow for workflow in workflows if workflow.dynamic_contexts]
    findings: list[Finding] = []

    for context in required:
        matching = [workflow for workflow in workflows if context in workflow.contexts]
        if not matching:
            renamed = _rename_candidate(context, emitted)
            if renamed:
                owner = next(workflow for workflow in workflows if renamed in workflow.contexts)
                findings.append(Finding(
                    code="REQUIRED_CONTEXT_RENAMED",
                    severity="error",
                    required_context=context,
                    workflow=str(owner.path),
                    message=f"Required context '{context}' is not emitted; closest job name is '{renamed}'.",
                    suggestion=f"Rename the job to '{context}' or update the required-check rule.",
                ))
            elif dynamic_workflows:
                names = ", ".join(str(workflow.path) for workflow in dynamic_workflows)
                findings.append(Finding(
                    code="REQUIRED_CONTEXT_UNVERIFIABLE",
                    severity="warning",
                    required_context=context,
                    message=f"Required context '{context}' has no static match, but dynamic job names exist in: {names}.",
                    suggestion="Resolve the expressions for this matrix/event or use a static aggregator job name.",
                ))
            else:
                findings.append(Finding(
                    code="REQUIRED_CHECK_NEVER_EMITTED",
                    severity="error",
                    required_context=context,
                    message=f"Required context '{context}' is not emitted by any workflow job.",
                    suggestion="Add a job with this exact name or update the required-check rule.",
                ))

        pull_request_matches = [workflow for workflow in matching if workflow.has_pull_request]
        if matching and not pull_request_matches:
            paths = ", ".join(str(workflow.path) for workflow in matching)
            findings.append(Finding(
                code="REQUIRED_CHECK_NOT_ON_PULL_REQUEST",
                severity="error",
                required_context=context,
                workflow=str(matching[0].path),
                message=f"No workflow emitting '{context}' handles pull_request ({paths}).",
                suggestion="Add 'pull_request:' under 'on:' to a workflow that emits this context.",
            ))

        if pull_request_matches and all(workflow.pull_request_filters for workflow in pull_request_matches):
            for workflow in pull_request_matches:
                filters = workflow.pull_request_filters
                findings.append(Finding(
                    code="WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED",
                    severity="error",
                    required_context=context,
                    workflow=str(workflow.path),
                    message=f"Workflow-level {', '.join(filters)} may skip required context '{context}'.",
                    suggestion="Remove workflow-level path filters or emit an always-running aggregator/fallback check.",
                ))

        if require_merge_group and matching and not any(workflow.has_merge_group for workflow in matching):
            paths = ", ".join(str(workflow.path) for workflow in matching)
            findings.append(Finding(
                code="MERGE_GROUP_TRIGGER_MISSING",
                severity="error",
                required_context=context,
                workflow=str(matching[0].path),
                message=f"No workflow emitting '{context}' handles merge_group ({paths}).",
                suggestion="Add 'merge_group:' under 'on:' to a workflow that emits this context.",
            ))

    findings.sort(key=lambda item: (item.code, item.required_context, item.workflow or ""))
    return AuditResult(required, len(workflows), emitted, tuple(findings))
