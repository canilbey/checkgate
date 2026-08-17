from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from checkgate.audit import AuditInputError, audit, discover_workflows
from checkgate.models import AuditResult


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="checkgate", description="Audit GitHub Actions required-check contracts offline.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("audit", help="audit local workflow YAML files")
    command.add_argument("--workflows", type=Path, default=Path(".github/workflows"), help="workflow directory")
    command.add_argument("--required", action="append", default=[], metavar="CONTEXT[,CONTEXT]", help="required context; repeat or comma-separate")
    command.add_argument("--required-file", type=Path, help="newline-delimited required contexts; # comments allowed")
    command.add_argument(
        "--require-merge-group",
        action="store_true",
        help="require matching checks to run for GitHub merge queues",
    )
    command.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    return parser


def _required(args: argparse.Namespace) -> list[str]:
    values = [part.strip() for item in args.required for part in item.split(",") if part.strip()]
    if args.required_file:
        try:
            lines = args.required_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise AuditInputError(f"cannot read required contexts from {args.required_file}: {exc}") from exc
        values.extend(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))
    return values


def render_text(result: AuditResult) -> str:
    lines = [
        f"checkgate: {result.error_count} error(s), {result.warning_count} warning(s)",
        f"scanned {result.workflows_scanned} workflow(s); checked {len(result.required_contexts)} required context(s)",
    ]
    if not result.findings:
        lines.append("OK: required-check contract is consistent.")
    for finding in result.findings:
        location = f" [{finding.workflow}]" if finding.workflow else ""
        lines.append(f"{finding.severity.upper()} {finding.code}{location}")
        lines.append(f"  {finding.message}")
        if finding.suggestion:
            lines.append(f"  Fix: {finding.suggestion}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = audit(
            discover_workflows(args.workflows),
            _required(args),
            require_merge_group=args.require_merge_group,
        )
    except AuditInputError as exc:
        print(f"checkgate: input error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif args.format == "sarif":
        print(json.dumps(result.to_sarif(), indent=2, sort_keys=True))
    else:
        print(render_text(result))
    return 1 if result.error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
