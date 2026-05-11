# E2E Testing

These tests validate terraform-branch-deploy against real GitHub pull requests, issue comments, workflow runs, deployments, locks, and action cache behavior.

## Live Runs

Live E2E tests create temporary branches, PRs, comments, and workflow runs in `scarowar/test-terraform-branch-deploy`.

```bash
export GITHUB_TOKEN="$(gh auth token)"
uv run pytest tests/e2e/ -v
```

Run release certification in severity order:

```bash
python3 scripts/run-certification.py --live
```

Stop on the first failing stage, inspect the workflow URL from the failure, fix the issue, then restart from the relevant marker or rerun certification.

## Severity Markers

| Marker | Purpose |
|--------|---------|
| `critical` | Release-blocking safety scenarios |
| `core` | Essential plan, apply, and rollback paths |
| `stateful` | Locks, lifecycle, and persistent state |
| `args` | Terraform argument parsing and forwarding |
| `edge` | Lower-priority graceful handling scenarios |
| `slow` | Longer-running or lower-frequency scenarios |

Examples:

```bash
uv run pytest tests/e2e/ -m critical --maxfail=1
uv run pytest tests/e2e/ -m "core and not critical" --maxfail=1
uv run pytest tests/e2e/ -m slow --maxfail=1
```

## Local Non-Mutating Checks

These checks do not call GitHub:

```bash
uv run pytest tests/test_release_contract.py tests/test_runner_mocked.py
```

They validate the release harness and the local GitHub API runner. They do not replace live E2E certification.

## Cleanup

Tests register created PRs and branches for automatic cleanup after each test. If a run is interrupted, use the cleanup script:

```bash
python3 scripts/cleanup-e2e.py
python3 scripts/cleanup-e2e.py --execute
```

Use `--cleanup-first` with live certification when you want to clear previous E2E artifacts before starting:

```bash
python3 scripts/run-certification.py --live --cleanup-first
```

The release suite does not include tests that mutate shared branches such as `main`.
