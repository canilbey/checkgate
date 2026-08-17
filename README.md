# checkgate

`checkgate` is a read-only CLI that audits the contract between GitHub Actions
workflow jobs and required check names. It catches configuration drift that can
leave a pull request permanently waiting for a status that the workflow cannot
emit.

It works offline: you supply the required check names, and `checkgate` reads
local workflow YAML. It does not need a GitHub token and never modifies files.

## What it detects

- `REQUIRED_CHECK_NEVER_EMITTED` — no static job emits the required name.
- `REQUIRED_CONTEXT_RENAMED` — a similar job name suggests configuration drift.
- `REQUIRED_CHECK_NOT_ON_PULL_REQUEST` — the matching job cannot run for PRs.
- `WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED` — workflow-level `paths` or
  `paths-ignore` can skip the entire required workflow.
- `MERGE_GROUP_TRIGGER_MISSING` — opt-in merge-queue validation finds a missing
  `merge_group` trigger.
- `REQUIRED_CONTEXT_UNVERIFIABLE` — an expression or matrix makes the emitted
  check names dynamic; this is a warning rather than a false certainty.

Output is available as human-readable text, stable JSON, or SARIF 2.1.0.

## Install

Python 3.10+ is required.

```console
python -m pip install .
```

For development from a clone:

```console
python -m pip install -e .
```

## Quick start

Copy the required check names from your branch protection or ruleset into a
newline-delimited file:

```text
unit-tests
lint
security-scan
```

Audit the repository's workflows:

```console
checkgate audit \
  --workflows .github/workflows \
  --required-file required-checks.txt
```

You can also repeat or comma-separate values:

```console
checkgate audit --required unit-tests,lint --required security-scan
```

If the repository uses GitHub merge queues, enable the additional contract
check explicitly:

```console
checkgate audit --required-file required-checks.txt --require-merge-group
```

Machine-readable output:

```console
checkgate audit --required-file required-checks.txt --format json
checkgate audit --required-file required-checks.txt --format sarif > checkgate.sarif
```

## Included demo

The intentionally broken fixture demonstrates renamed and missing contexts,
workflow-level path-filter risk, and an absent merge-queue trigger:

```console
checkgate audit \
  --workflows fixtures/workflows \
  --required-file fixtures/required.txt \
  --require-merge-group
```

The safe fixture exits successfully:

```console
checkgate audit \
  --workflows fixtures/safe/workflows \
  --required-file fixtures/safe/required.txt
```

## Exit codes

- `0`: no errors (warnings may be present)
- `1`: one or more contract errors
- `2`: invalid CLI input, unreadable input, or invalid workflow YAML

## Why this exists

GitHub users have repeatedly documented required checks getting stuck when a
workflow is skipped by path filters, including long-running community threads
[#13690](https://github.com/orgs/community/discussions/13690),
[#44490](https://github.com/orgs/community/discussions/44490), and
[#26251](https://github.com/orgs/community/discussions/26251). Existing tools
are excellent at workflow syntax or path selection; `checkgate` focuses on the
small contract between names, PR triggers, path filters, and merge queues.

## Honest limits

Version 0.1 audits local YAML against a user-supplied list. It does not discover
branch protection or rulesets through the GitHub API, resolve reusable
workflows, or expand expressions/matrices. Dynamic names produce a warning.
The `--require-merge-group` check is opt-in because a workflow without that
trigger is only defective when the repository actually uses merge queues.

## Development

```console
python -m pytest
python -m ruff check src tests
```

See [`VALIDATION.md`](VALIDATION.md) for fixture and public-repository dry-run
evidence.

## License

MIT
