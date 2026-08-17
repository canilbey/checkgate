# Validation evidence

Validated at: `2026-08-17T07:35:12Z`

## Automated checks

```console
$ python3 -m pytest -q
..................                                                       [100%]

$ python3 -m ruff check src tests
All checks passed!

$ python3 -m compileall -q src tests
# exit 0

$ python3 -m checkgate audit --workflows .github/workflows --required test
checkgate: 0 error(s), 0 warning(s)
scanned 1 workflow(s); checked 1 required context(s)
OK: required-check contract is consistent.
```

A wheel was built with `python3 -m pip wheel --no-build-isolation --no-deps .`
and installed into a fresh virtual environment. The installed `checkgate` entry
point returned `0` on the safe fixture. Built wheel:
`checkgate-0.1.0-py3-none-any.whl` (9,453 bytes,
SHA-256 `72977f087227038980359800e7bb99443dffff5f645a179060e1ed63911304d4`).

## Public-repository dry runs

The following repositories were shallow-cloned at the recorded commits. The
contexts below were selected from static job names in their workflow YAML;
these runs do **not** claim that those names are enabled in the repositories'
actual branch rules. They validate parser and diagnostic behavior against real,
current workflow structures.

### rhysd/actionlint

Source: <https://github.com/rhysd/actionlint/tree/011a6d15e749bb3f2d771eed9c7aa0e7e3e10ee7>

- Static `Lint` context: 6 workflows scanned, 0 errors, 0 warnings, exit `0`.
- Matrix-backed `Unit tests` context: 0 errors, 1
  `REQUIRED_CONTEXT_UNVERIFIABLE` warning, exit `0`. This verifies that matrix
  jobs are not falsely treated as one static check name.

### dorny/paths-filter

Source: <https://github.com/dorny/paths-filter/tree/ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d>

Using the static `build` job name, 2 workflows were scanned. Checkgate reported
`WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED` for
`.github/workflows/pull-request-verification.yml`, whose `pull_request` trigger
has `paths-ignore`. Exit: `1`.

### fkirc/skip-duplicate-actions

Source: <https://github.com/fkirc/skip-duplicate-actions/tree/a09bf677ad5e5dedb31a42070b6a180fde0ab6ce>

Using the static `Check dist` job name, 2 workflows were scanned. Checkgate
reported `WORKFLOW_PATH_FILTER_CAN_SKIP_REQUIRED` for
`.github/workflows/check-dist.yml`, whose `pull_request` trigger has
`paths-ignore`. Exit: `1`.

These are configuration-risk diagnostics, not claims that either upstream
repository is currently broken: a finding only becomes a merge blocker when
the supplied context is actually required by branch protection or a ruleset.
