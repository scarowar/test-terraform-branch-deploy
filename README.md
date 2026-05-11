# Test Terraform Branch Deploy

E2E test repository for [terraform-branch-deploy](https://github.com/scarowar/terraform-branch-deploy) v0.2.0.

> **Lean, high-signal E2E suite**: 22 E2E tests focused on deterministic release risks.

## Quick Start

```bash
# Install
uv sync --dev

# Local non-mutating checks
uv run pytest tests/test_release_contract.py tests/test_runner_mocked.py

# Get token for live E2E
export GITHUB_TOKEN=$(gh auth token)

# Run all tests
uv run pytest tests/e2e/ -v

# Run release certification in severity order
python3 scripts/run-certification.py --live

# Run by category
uv run pytest -m core -v      # Core workflows
uv run pytest -m failures -v  # Error handling
uv run pytest -m slow -v      # Enterprise scenarios
```

---

## Test Suite Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `test_plan_apply.py` | 7 | Plan, apply, rollback, saved targeted plans |
| `test_locking.py` | 4 | Lock, unlock, wcid, global lock |
| `test_failure_modes.py` | 6 | Invalid env, stale plan, TF errors, safety checks |
| `test_branching.py` | 1 | PR lifecycle |
| `test_enterprise.py` | 4 | Recovery, multi-env, argument parsing |
| **TOTAL** | **22** | **Deterministic release coverage** |

Additional local release-contract checks verify that the E2E workflow tests a pinned candidate action ref instead of a floating branch.

---

## Scenario Groups

### Core Workflows (`test_plan_apply.py`)
| Test | Code Path |
|------|-----------|
| `test_plan_dev` | Basic plan → executor.plan() |
| `test_plan_prod` | Production env handling |
| `test_apply_after_plan` | Plan → apply flow |
| `test_apply_after_targeted_plan_uses_saved_target_plan` | Targeted plan → plain apply safety |
| `test_apply_without_plan_fails` | Missing plan detection |
| `test_rollback_to_main` | Rollback bypasses plan |
| `test_plan_with_var` | `-var` parsing |

### Locking (`test_locking.py`)
| Test | Code Path |
|------|-----------|
| `test_lock_unlock_cycle` | Lock/unlock mechanism |
| `test_deploy_while_locked_by_owner` | Sticky lock bypass |
| `test_wcid_shows_lock_status` | Lock info display |
| `test_global_lock` | Global lock behavior |

### Failure Modes (`test_failure_modes.py`)
| Test | Code Path |
|------|-----------|
| `test_invalid_environment_fails` | Bad env rejected |
| `test_apply_stale_plan_fails` | SHA mismatch detection |
| `test_malformed_command_ignored` | No workflow triggered |
| `test_terraform_init_failure` | Init failure handling |
| `test_command_injection_blocked` | Shell injection guard |
| `test_help_command` | Help command behavior |

### Enterprise (`test_enterprise.py`)
| Test | Risk |
|------|------|
| `test_retry_after_terraform_failure` | Recovery from errors |
| `test_sequential_dev_to_prod` | Multi-env deployment |
| `test_var_with_equals_in_value` | Connection strings |
| `test_target_resource_arg` | `-target` forwarding |

### Branching (`test_branching.py`)
| Test | Risk |
|------|------|
| `test_pr_remains_open_after_apply` | No auto-merge |

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
| `TF_BRANCH_DEPLOY_REF` | `.github/terraform-branch-deploy-ref` | Candidate action ref used by the deploy workflow |
| `E2E_COMMIT_AUTHOR_NAME` | `terraform-branch-deploy-e2e` | Author and committer name for commits made by live tests |
| `E2E_COMMIT_AUTHOR_EMAIL` | `terraform-branch-deploy-e2e@example.invalid` | Author and committer email for commits made by live tests |
| `E2E_FORCE_CLEANUP` | `true` | Auto-cleanup test PRs |
| `E2E_CLEANUP_DELAY` | `0.5` | Rate limit delay (seconds) |

`TF_BRANCH_DEPLOY_REF` may be set as a repository variable for temporary certification runs. Otherwise, update `.github/terraform-branch-deploy-ref` to the exact commit SHA or release tag under test. Do not use `main` for release certification.

## Certification Order

`python3 scripts/run-certification.py --live` runs live E2E in this order:

1. `critical`
2. `core`
3. `stateful`
4. `args`
5. `edge`
6. `slow`

The script stops on the first failing stage. Local release-contract and mocked runner tests run first and do not create GitHub resources.
