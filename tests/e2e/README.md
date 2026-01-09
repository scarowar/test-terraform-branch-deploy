# E2E Testing Guide

This directory contains E2E tests for terraform-branch-deploy.

## Quick Start

```bash
# Run all E2E tests
GITHUB_TOKEN=xxx uv run pytest tests/e2e/ -v

# Run specific test
GITHUB_TOKEN=xxx uv run pytest tests/e2e/ -v -k "test_basic_plan"
```

## Test Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub token with repo access | Required |
| `E2E_FORCE_CLEANUP` | Cleanup artifacts after each test | `true` |
| `E2E_CLEANUP_DELAY` | Delay between cleanup operations (seconds) | `0.5` |
| `E2E_USE_MOCKS` | Enable VCR-style mock testing | `false` |

### Automatic Cleanup

Tests now automatically clean up after themselves:

1. Branches matching `e2e-test-*` are deleted
2. PRs created during tests are closed
3. Lock branches are removed

This happens regardless of test outcome (pass/fail/error).

## Manual Cleanup

If tests leave artifacts behind, use the cleanup script:

```bash
# Dry run (shows what would be deleted)
python scripts/cleanup-e2e.py

# Actually delete artifacts
python scripts/cleanup-e2e.py --execute

# Delete everything including closed PRs
python scripts/cleanup-e2e.py --execute --all
```

## Local Testing with `act`

For faster iteration without polluting GitHub:

### Install act

```bash
# macOS
brew install act

# Linux
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```

### Run workflows locally

```bash
cd terraform-branch-deploy

# Run the full workflow with a simulated comment event
act issue_comment -e tests/fixtures/events/plan-comment.json \
  -s GITHUB_TOKEN=xxx

# Run with extra args
act issue_comment -e tests/fixtures/events/plan-with-args.json \
  -s GITHUB_TOKEN=xxx
```

### Limitations of `act`

- No actual GitHub API calls (uses mocks)
- Some GitHub context differs from real execution
- Secrets must be passed via `-s` flag

## Test Structure

```
tests/
├── e2e/
│   ├── conftest.py         # Fixtures and cleanup
│   ├── runner.py           # Core test runner
│   ├── test_core.py        # Basic plan/apply tests
│   ├── test_comprehensive.py # Full feature tests
│   ├── test_permutations.py  # Parameter combinations
│   ├── test_edge_cases.py    # Edge cases
│   └── cassettes/          # VCR recordings (future)
└── fixtures/
    └── events/             # act event payloads
```

## Writing New Tests

```python
@pytest.mark.e2e
class TestMyFeature:
    def test_my_scenario(self, runner: E2ETestRunner) -> None:
        # Setup creates branch + PR, auto-cleaned after test
        branch, pr, sha = runner.setup_test_pr("my_test")
        
        # Post command and wait for workflow
        run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        
        # Assert results
        runner.assert_workflow_success(run)
        # No cleanup needed - happens automatically!
```

## Future Improvements

### VCR-Style Mock Testing

Record real API responses and replay them:

```bash
# Install pytest-vcr
uv add pytest-vcr --dev

# Run tests in record mode (first time)
E2E_RECORD=true uv run pytest tests/e2e/ -v

# Run tests in playback mode (fast, no GitHub calls)
uv run pytest tests/e2e/ -v
```

This will be implemented when we add the `@pytest.mark.vcr()` decorator to tests.
