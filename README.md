# Test Terraform Branch Deploy

E2E test repository for [terraform-branch-deploy](https://github.com/scarowar/terraform-branch-deploy) v0.2.0.

> **Lean, high-signal test suite**: 28 tests covering full width and depth of scenarios.

## Quick Start

```bash
# Install
uv sync --dev

# Get token
export GITHUB_TOKEN=$(gh auth token)

# Run all tests
uv run pytest tests/e2e/ -v

# Run by category
uv run pytest -m core -v      # Core workflows
uv run pytest -m failures -v  # Error handling
uv run pytest -m slow -v      # Enterprise scenarios
```

---

## Test Suite Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `test_plan_apply.py` | 7 | Plan, apply, rollback, extra args |
| `test_locking.py` | 3 | Lock, unlock, wcid |
| `test_failure_modes.py` | 5 | Invalid env, stale plan, TF errors |
| `test_branching.py` | 4 | Feature branches, merge conflicts |
| `test_enterprise.py` | 6 | Concurrency, recovery, multi-env |
| `test_smoke.py` | 3 | Basic sanity |
| **TOTAL** | **28** | **Full width + depth** |

---

## Scenario Groups

### Core Workflows (`test_plan_apply.py`)
| Test | Code Path |
|------|-----------|
| `test_plan_dev` | Basic plan → executor.plan() |
| `test_plan_prod` | Production env handling |
| `test_apply_after_plan` | Plan → apply flow |
| `test_apply_without_plan_fails` | Missing plan detection |
| `test_rollback_to_main` | Rollback bypasses plan |
| `test_plan_with_extra_args` | `-target` parsing |
| `test_plan_with_var` | `-var` parsing |

### Locking (`test_locking.py`)
| Test | Code Path |
|------|-----------|
| `test_lock_unlock_cycle` | Lock/unlock mechanism |
| `test_deploy_while_locked_by_owner` | Sticky lock bypass |
| `test_wcid_shows_lock_status` | Lock info display |

### Failure Modes (`test_failure_modes.py`)
| Test | Code Path |
|------|-----------|
| `test_invalid_environment_fails` | Bad env rejected |
| `test_apply_stale_plan_fails` | SHA mismatch detection |
| `test_malformed_command_ignored` | No workflow triggered |
| `test_plan_with_complex_var` | Complex arg parsing |
| `test_case_sensitivity` | Command case handling |

### Enterprise (`test_enterprise.py`)
| Test | Risk |
|------|------|
| `test_concurrent_plans_handled_safely` | Race conditions |
| `test_retry_after_terraform_failure` | Recovery from errors |
| `test_sequential_dev_to_prod` | Multi-env deployment |
| `test_var_with_json_value` | Complex parsing |
| `test_var_with_equals_in_value` | Connection strings |
| `test_target_with_indexed_resource` | Count/for_each |

### Branching (`test_branching.py`)
| Test | Risk |
|------|------|
| `test_feature_to_feature_pr` | Non-main base branch |
| `test_pr_remains_open_after_apply` | No auto-merge |
| `test_outdated_branch_warning` | Stale branch detection |
| `test_merge_conflict_fails_gracefully` | Conflict handling |

---

## Commands

| Command | Description |
|---------|-------------|
| `.plan to dev` | Plan to development |
| `.apply to dev` | Apply after plan |
| `.apply main to dev` | Rollback |
| `.lock dev` | Lock environment |
| `.unlock dev` | Unlock |
| `.wcid` | Who is deploying |
| `.help` | Show help |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | Required | GitHub PAT with repo access |
| `E2E_FORCE_CLEANUP` | `true` | Auto-cleanup test PRs |
| `E2E_CLEANUP_DELAY` | `0.5` | Rate limit delay (seconds) |
