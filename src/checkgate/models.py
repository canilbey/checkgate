from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Workflow:
    path: Path
    name: str
    triggers: dict[str, Any]
    contexts: tuple[str, ...]
    dynamic_contexts: tuple[str, ...]

    @property
    def has_pull_request(self) -> bool:
        return "pull_request" in self.triggers

    @property
    def has_merge_group(self) -> bool:
        return "merge_group" in self.triggers

    @property
    def pull_request_filters(self) -> tuple[str, ...]:
        config = self.triggers.get("pull_request")
        if not isinstance(config, dict):
            return ()
        return tuple(key for key in ("paths", "paths-ignore") if key in config)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    required_context: str
    workflow: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class AuditResult:
    required_contexts: tuple[str, ...]
    workflows_scanned: int
    emitted_contexts: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def error_count(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "summary": {
                "required_contexts": len(self.required_contexts),
                "workflows_scanned": self.workflows_scanned,
                "emitted_contexts": len(self.emitted_contexts),
                "errors": self.error_count,
                "warnings": self.warning_count,
            },
            "required_contexts": list(self.required_contexts),
            "emitted_contexts": list(self.emitted_contexts),
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def to_sarif(self) -> dict[str, Any]:
        rule_ids = sorted({finding.code for finding in self.findings})
        results = []
        for finding in self.findings:
            result: dict[str, Any] = {
                "ruleId": finding.code,
                "level": finding.severity,
                "message": {"text": finding.message},
                "properties": {"requiredContext": finding.required_context},
            }
            if finding.workflow:
                result["locations"] = [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": Path(finding.workflow).as_posix()},
                    },
                }]
            results.append(result)
        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {"driver": {
                    "name": "checkgate",
                    "informationUri": "https://github.com/canilbey/checkgate",
                    "rules": [{"id": rule_id} for rule_id in rule_ids],
                }},
                "results": results,
            }],
        }
