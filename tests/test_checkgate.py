from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from checkgate.audit import AuditInputError, audit, discover_workflows, load_workflow
from checkgate.cli import main, render_text

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_import_does_not_mutate_pyyaml_safe_loader() -> None:
    assert yaml.safe_load("on: value") == {True: "value"}


def test_github_on_key_and_triggers_are_preserved() -> None:
    workflow = load_workflow(FIXTURES / "workflows" / "ci.yml")
    assert workflow.has_pull_request
    assert not workflow.has_merge_group
    assert workflow.pull_request_filters == ("paths",)


def test_audit_detects_required_contract_failures() -> None:
    result = audit(
        discover_workflows(FIXTURES / "workflows"),
        ["unit-tests", "lint", "security-scan"],
        require_merge_group=True,
    )
    codes = {(item.code, item.required_context) for item in result.findings}
    assert ("REQUIRED_CONTEXT_RENAMED", "unit-tests") in codes
    assert ("REQUIRED_CHECK_NEVER_EMITTED", "security-scan") in codes
    assert ("WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED", "lint") in codes
    assert ("MERGE_GROUP_TRIGGER_MISSING", "lint") in codes
    assert result.error_count == 4


def test_safe_contract_has_no_findings() -> None:
    result = audit(discover_workflows(FIXTURES / "safe" / "workflows"), ["unit-tests", "lint"])
    assert result.findings == ()
    assert result.error_count == 0


def test_merge_group_check_is_opt_in() -> None:
    workflows = discover_workflows(FIXTURES / "workflows")
    default_result = audit(workflows, ["lint"])
    merge_queue_result = audit(workflows, ["lint"], require_merge_group=True)
    assert "MERGE_GROUP_TRIGGER_MISSING" not in {item.code for item in default_result.findings}
    assert "MERGE_GROUP_TRIGGER_MISSING" in {item.code for item in merge_queue_result.findings}


def test_required_context_must_run_for_pull_requests(tmp_path: Path) -> None:
    (tmp_path / "push-only.yml").write_text(
        "name: CI\non: [push]\njobs:\n  lint:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    result = audit(discover_workflows(tmp_path), ["lint"])
    assert [item.code for item in result.findings] == ["REQUIRED_CHECK_NOT_ON_PULL_REQUEST"]


def test_unfiltered_pr_emitter_makes_same_context_safe(tmp_path: Path) -> None:
    (tmp_path / "push.yml").write_text(
        "on: [push]\njobs:\n  lint:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    (tmp_path / "pr.yml").write_text(
        "on: [pull_request]\njobs:\n  lint:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    assert audit(discover_workflows(tmp_path), ["lint"]).findings == ()


def test_dynamic_job_name_is_reported_as_unverifiable_not_missing(tmp_path: Path) -> None:
    workflow = tmp_path / "dynamic.yml"
    workflow.write_text(
        "name: CI\non: [pull_request, merge_group]\njobs:\n  test:\n    name: test-${{ matrix.python }}\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    result = audit(discover_workflows(tmp_path), ["test-3.12"])
    assert [item.code for item in result.findings] == ["REQUIRED_CONTEXT_UNVERIFIABLE"]
    assert result.error_count == 0
    assert result.warning_count == 1


def test_matrix_job_name_is_not_treated_as_a_static_context(tmp_path: Path) -> None:
    workflow = tmp_path / "matrix.yml"
    workflow.write_text(
        "name: CI\non: [pull_request]\njobs:\n  test:\n    name: Tests\n    strategy:\n      matrix:\n        python: ['3.11', '3.12']\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    result = audit(discover_workflows(tmp_path), ["Tests"])
    assert result.emitted_contexts == ()
    assert [item.code for item in result.findings] == ["REQUIRED_CONTEXT_UNVERIFIABLE"]


def test_deduplicates_required_contexts() -> None:
    workflows = discover_workflows(FIXTURES / "safe" / "workflows")
    result = audit(workflows, ["lint", "lint", " lint "])
    assert result.required_contexts == ("lint",)


def test_text_output_is_actionable() -> None:
    result = audit(discover_workflows(FIXTURES / "workflows"), ["lint"])
    output = render_text(result)
    assert "WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED" in output
    assert "Fix:" in output
    assert "1 error(s)" in output


def test_json_cli_output_and_error_exit(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([
        "audit", "--workflows", str(FIXTURES / "workflows"),
        "--required", "unit-tests,lint,security-scan", "--require-merge-group", "--format", "json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["schema_version"] == 1
    assert payload["summary"]["errors"] == 4
    assert {item["code"] for item in payload["findings"]} >= {
        "REQUIRED_CONTEXT_RENAMED", "REQUIRED_CHECK_NEVER_EMITTED",
        "WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED", "MERGE_GROUP_TRIGGER_MISSING",
    }


def test_sarif_cli_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([
        "audit", "--workflows", str(FIXTURES / "workflows"),
        "--required", "lint", "--format", "sarif",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["version"] == "2.1.0"
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "checkgate"
    assert run["results"][0]["ruleId"] == "WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED"
    uri = run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri.endswith("ci.yml")


def test_clean_cli_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([
        "audit", "--workflows", str(FIXTURES / "safe" / "workflows"),
        "--required-file", str(FIXTURES / "safe" / "required.txt"),
    ])
    assert code == 0
    assert "OK:" in capsys.readouterr().out


def test_missing_workflow_directory_returns_input_exit(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["audit", "--workflows", str(tmp_path / "absent"), "--required", "lint"])
    captured = capsys.readouterr()
    assert code == 2
    assert "input error" in captured.err


def test_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "broken.yml").write_text("jobs: [", encoding="utf-8")
    with pytest.raises(AuditInputError, match="cannot parse workflow"):
        discover_workflows(tmp_path)


def test_empty_required_list_is_rejected() -> None:
    with pytest.raises(AuditInputError, match="at least one"):
        audit(discover_workflows(FIXTURES / "safe" / "workflows"), [])


def test_required_file_ignores_comments(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    required = tmp_path / "required.txt"
    required.write_text("# branch rule export\n\nlint\n", encoding="utf-8")
    code = main([
        "audit", "--workflows", str(FIXTURES / "safe" / "workflows"),
        "--required-file", str(required), "--format", "json",
    ])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["required_contexts"] == ["lint"]
