# E2E Testing

These tests validate terraform-branch-deploy against real GitHub pull requests, issue comments, workflow runs, deployments, locks, and action cache behavior.

## Live Runs

Live E2E tests create temporary branches, PRs, comments, and workflow runs in `scarowar/test-terraform-branch-deploy`.

```bash
export GITHUB_TOKEN="$(gh auth token)"
uv run pytest tests/e2e/ -v
```

Run live validation in severity order:

```bash
python3 scripts/run-certification.py --live
```

Stop on the first failing stage, inspect the workflow URL from the failure, fix the issue, then restart from the relevant marker.

For pull request validation, run the GitHub Actions workflow from this repository so the candidate ref and result are recorded:

```bash
gh workflow run e2e-tests.yml \
  -f candidate_ref=<terraform-branch-deploy-sha> \
  -f source_pr=<pull-request-number> \
  -f stage=critical
```

Use `stage=all` for the full release gate. Set `TFBD_STATUS_TOKEN` before using `source_pr`.

## Severity Markers

| Marker | Purpose |
|--------|---------|
| `critical` | Apply safety scenarios |
| `core` | Essential plan, apply, and rollback paths |
| `stateful` | Locks, lifecycle, and persistent state |
| `args` | Terraform argument parsing and forwarding |
| `edge` | Lower-priority graceful handling scenarios |
| `slow` | Longer-running or lower-frequency scenarios |

## Live Test Selection

Live tests should cover behavior that only a real GitHub workflow can prove.

| Area | Live coverage |
| --- | --- |
| Saved apply safety | Missing plan, stale plan, targeted plan then plain apply, fresh apply args rejected |
| Config argument safety | Configured plan args compose with comment args, unsafe configured apply target rejected |
| Lifecycle and locks | Non-sticky locks clear after success/failure, manual environment/global locks can be claimed and released |
| Failure recovery | Init failure cleanup and retry after a fixed Terraform error |
| Command parsing | Complex `-var` value and shell-injection attempt |
| Branch Deploy pass-through | Invalid environment, help, `.wcid`, global lock |

Apply safety includes both negative and positive checks:
missing plans must fail, stale plans must fail, and plain apply after a targeted
plan must use the saved targeted `.tfplan` file. Configured plan args must
compose with comment args. Apply and rollback commands must also reject fresh
Terraform arguments and unsafe configured apply targets.

Stateful checks also assert Branch Deploy lock refs directly:
successful plan/apply runs must remove non-sticky environment locks, and
manual environment/global locks must exist after `.lock` and disappear after
`.unlock`.

Examples:

```bash
uv run pytest tests/e2e/ -m critical --maxfail=1
uv run pytest tests/e2e/ -m "core and not critical" --maxfail=1
uv run pytest tests/e2e/ -m "args and not critical" --maxfail=1
uv run pytest tests/e2e/ -m slow --maxfail=1
```

## Local Non-Mutating Checks

These checks do not call GitHub:

```bash
uv run pytest tests/test_release_contract.py tests/test_runner_mocked.py
```

They validate the workflow contract and the local GitHub API runner. They do not replace live E2E validation.

## Cleanup

Tests register created PRs and branches for automatic cleanup after each test. If a run is interrupted, use the cleanup script:

```bash
python3 scripts/cleanup-e2e.py
python3 scripts/cleanup-e2e.py --execute
```

Use `--cleanup-first` with live validation when you want to clear previous E2E artifacts before starting:

```bash
python3 scripts/run-certification.py --live --cleanup-first
```

The live suite does not include tests that mutate shared branches such as `main`.
