# Test Terraform Branch Deploy

E2E test repository for [terraform-branch-deploy](https://github.com/scarowar/terraform-branch-deploy) v0.2.0.

> **This test suite is merge-blocking**. Every test is verified against the current architecture branch and proven to hit intended code paths.

## Quick Start

```bash
# Install dependencies
uv sync --dev

# Get token (easiest method)
export GITHUB_TOKEN=$(gh auth token)

# Run smoke tests first
uv run pytest tests/e2e/test_smoke.py -v

# Run full suite
uv run pytest tests/e2e/ -v
```

---

## Commands Reference

### Full Suite
```bash
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/e2e/ -v
```

### By Scenario Group
```bash
# Core workflows (plan, apply, lock)
GITHUB_TOKEN=$(gh auth token) uv run pytest -m core -v

# Failure modes
GITHUB_TOKEN=$(gh auth token) uv run pytest -m failures -v

# Smoke tests only
GITHUB_TOKEN=$(gh auth token) uv run pytest -m smoke -v

# Chaos tests
GITHUB_TOKEN=$(gh auth token) uv run pytest -m chaos -v
```

### By File
```bash
# Plan/Apply tests
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/e2e/test_plan_apply.py -v

# Locking tests
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/e2e/test_locking.py -v

# Failure mode tests
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/e2e/test_failure_modes.py -v
```

### Individual Tests
```bash
# Single test
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/e2e/test_plan_apply.py::TestPlan::test_plan_dev -v

# By keyword
GITHUB_TOKEN=$(gh auth token) uv run pytest -k "plan" -v
```

### Local vs CI
```bash
# Local (uses gh auth token)
export GITHUB_TOKEN=$(gh auth token)
uv run pytest tests/e2e/ -v

# CI (uses secrets.E2E_PAT)
# Set in repository secrets, workflow handles automatically
```

---

## Coverage Mapping

### Success Paths

| Test | Feature | Code Path |
|------|---------|-----------|
| `test_plan_dev` | Basic plan | `cli.py:_handle_plan` → `executor.py:plan()` |
| `test_plan_prod` | Production env | Same path, `TF_BD_ENVIRONMENT=prod` |
| `test_plan_with_extra_args` | `-target` flag | `cli.py:_parse_extra_args` → executor |
| `test_plan_with_var` | `-var` flag | Shell quoting in `_parse_extra_args` |
| `test_apply_after_plan` | Standard apply | `cli.py:_apply_with_plan` → `executor.py:apply(plan_file)` |
| `test_rollback_to_main` | Rollback | `action.yml:IS_ROLLBACK=true` → direct apply |

### Apply Failures

| Test | Feature | Code Path |
|------|---------|-----------|
| `test_apply_without_plan_fails` | Missing plan | `cli.py:404` `if not plan_file.exists()` |
| `test_apply_stale_plan_fails` | SHA mismatch | Cache key changes → plan not found |

### Locking

| Test | Feature | Code Path |
|------|---------|-----------|
| `test_lock_unlock_cycle` | Lock/unlock | branch-deploy lock mechanism |
| `test_deploy_while_locked_by_owner_succeeds` | Owner bypass | branch-deploy allows owner |
| `test_wcid_shows_lock_status` | Lock info | branch-deploy wcid command |

### Failure Modes

| Test | Feature | Code Path |
|------|---------|-----------|
| `test_invalid_environment_fails` | Bad env | branch-deploy rejects before action |
| `test_malformed_command_ignored` | No trigger | Workflow not triggered |

---

## Test Files

| File | Tests | Category | Coverage |
|------|-------|----------|----------|
| `test_smoke.py` | 3 | Smoke | Basic sanity |
| `test_plan_apply.py` | 7 | Core | Plan/apply/rollback |
| `test_locking.py` | 3 | Core | Lock/unlock/wcid |
| `test_failure_modes.py` | 5 | Failures | Error handling |
| `test_comprehensive.py` | 20+ | Core | CLI modes, operations |
| `test_edge_cases.py` | 8 | Edge | Complex args, branching |
| `chaos/test_chaos.py` | 2 | Chaos | Concurrency, recovery |

---

## Architecture

v0.2.0 uses a **two-phase trigger/execute** architecture:

```
┌─────────────┐    TF_BD_*     ┌─────────────┐
│   TRIGGER   │ ─────vars────▶ │   EXECUTE   │
│  (Job 1)    │                │  (Job 2)    │
│  - Parse    │                │  - Checkout │
│  - Export   │                │  - Terraform│
│  - STOP     │                │  - Complete │
└─────────────┘                └─────────────┘
```

### Test Flow

```
Test → runner.post_and_wait → GitHub API → Workflow (issue_comment)
  → action.yml (trigger) → branch-deploy → action.yml (execute)
  → cli.py → executor.py → Terraform → Comment → Assertion
```

---

## Environments

| Environment | Directory | Production |
|-------------|-----------|------------|
| `dev` | `terraform/dev` | No |
| `prod` | `terraform/prod` | Yes |

---

## Supported Commands

| Command | Description |
|---------|-------------|
| `.plan to dev` | Plan to development |
| `.plan to prod` | Plan to production |
| `.apply to dev` | Apply after plan |
| `.apply main to dev` | Rollback to stable |
| `.lock dev` | Lock environment |
| `.unlock dev` | Unlock |
| `.wcid` | Who is deploying |
| `.help` | Show help |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | Required | GitHub PAT with repo access |
| `E2E_FORCE_CLEANUP` | `true` | Auto-cleanup test PRs/branches |
| `E2E_CLEANUP_DELAY` | `0.5` | Rate limit delay (seconds) |
| `E2E_USE_MOCKS` | `false` | Enable VCR-style mock testing |

---

## CI Workflow

```yaml
# .github/workflows/e2e-tests.yml
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6am UTC
  workflow_dispatch:
    inputs:
      test_filter:
        description: 'Test filter (e.g., "smoke" or "core")'
```

---

## Validation Criteria

Each test satisfies:

1. ✅ **Hits intended code paths** - Traces through action.yml → cli.py → executor.py
2. ✅ **Fails when code broken** - Assertions target specific outputs
3. ✅ **No false positives** - Comments checked with specific patterns
4. ✅ **No skipped tests** - All tests execute
5. ✅ **Maps to feature** - Clear feature/execution path documentation
