# Test Terraform Branch Deploy

E2E test repository for [terraform-branch-deploy](https://github.com/scarowar/terraform-branch-deploy).

This repository validates Terraform Branch Deploy against real GitHub pull requests, comments, workflow runs, deployments, locks, and saved plan behavior.

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

# Run live validation in severity order
python3 scripts/run-certification.py --live

# Run one live validation stage
python3 scripts/run-certification.py --live --stage critical

# Run by category
uv run pytest -m core -v      # Core workflows
uv run pytest -m failures -v  # Error handling
uv run pytest -m slow -v      # Enterprise scenarios
```

---

## Test Suite Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `test_plan_apply.py` | 7 | Plan, apply, rollback, saved targeted plans, and apply/rollback arg rejection |
| `test_locking.py` | 4 | Lock, unlock, wcid, global lock ref assertions |
| `test_failure_modes.py` | 7 | Invalid env, stale plan, unsafe config args, TF errors, safety checks |
| `test_enterprise.py` | 4 | Recovery, multi-env, argument parsing, config plan args |
| **TOTAL** | **22** | **Live workflow coverage** |

Local contract checks verify that the E2E workflow tests a pinned action ref instead of a floating branch.

---

## Pull Request Validation

Pull requests in `terraform-branch-deploy` run local CI without repository secrets. After review, a maintainer can start live validation from the pull request:

```text
/e2e
/e2e critical
```

`/e2e` runs the full release gate. Stage-specific commands are for diagnosis.

You can also dispatch this workflow directly from the test repository:

```bash
gh workflow run e2e-tests.yml \
  -f candidate_ref=<terraform-branch-deploy-sha> \
  -f source_pr=<pull-request-number> \
  -f stage=critical
```

Use `stage=all` for the full release gate. When `source_pr` is set, the workflow writes a commit status to the source pull request with `TFBD_STATUS_TOKEN`.

---

## Scenario Groups

### Core Workflows (`test_plan_apply.py`)
| Test | Code Path |
|------|-----------|
| `test_plan_prod` | Production env handling |
| `test_apply_after_plan` | Plan → apply flow |
| `test_apply_after_targeted_plan_uses_saved_target_plan` | Targeted plan → plain apply safety |
| `test_apply_without_plan_fails` | Missing plan detection |
| `test_apply_rejects_extra_args_after_saved_targeted_plan` | Apply must not accept fresh Terraform args |
| `test_rollback_to_main` | Rollback bypasses plan |
| `test_rollback_rejects_extra_args` | Rollback must not accept Terraform args |

### Locking (`test_locking.py`)
| Test | Code Path |
|------|-----------|
| `test_lock_unlock_cycle` | Lock/unlock mechanism with lock ref assertions |
| `test_deploy_while_locked_by_owner` | Sticky lock bypass |
| `test_wcid_shows_lock_status` | Lock info display |
| `test_global_lock` | Global lock behavior with lock ref assertions |

### Failure Modes (`test_failure_modes.py`)
| Test | Code Path |
|------|-----------|
| `test_invalid_environment_fails` | Bad env rejected |
| `test_apply_stale_plan_fails` | SHA mismatch detection |
| `test_apply_args_target_in_config_fails_before_init` | Unsafe config apply target rejected before Terraform init |
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
| `test_config_plan_args_append_comment_args` | Config plan args and comment args are both applied |

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
| `GITHUB_TOKEN` | Required locally | GitHub PAT with repo access for local live tests |
| `E2E_PAT` | GitHub Actions secret | Token used by scheduled and manual workflow runs to create test resources |
| `TF_BRANCH_DEPLOY_REF` | `.github/terraform-branch-deploy-ref` | Optional local or fallback action ref used by the deploy workflow |
| `TFBD_STATUS_TOKEN` | optional GitHub Actions secret | Token used by the manual E2E workflow to write commit status to `terraform-branch-deploy` |
| `E2E_COMMIT_AUTHOR_NAME` | `terraform-branch-deploy-e2e` | Author and committer name for commits made by live tests |
| `E2E_COMMIT_AUTHOR_EMAIL` | `terraform-branch-deploy-e2e@example.invalid` | Author and committer email for commits made by live tests |
| `E2E_FORCE_CLEANUP` | `true` | Auto-cleanup test PRs |
| `E2E_CLEANUP_DELAY` | `0.5` | Rate limit delay (seconds) |

The normal `/e2e` path records the candidate ref on each temporary test pull request. For scheduled or local runs, set `TF_BRANCH_DEPLOY_REF` or update `.github/terraform-branch-deploy-ref` to the exact commit SHA or release tag under test. Do not use `main`.

## Validation Order

`python3 scripts/run-certification.py --live` runs live E2E in this order:

1. `critical`
2. `core`
3. `stateful`
4. `args`
5. `edge`
6. `slow`

The script stops on the first failing stage. Local contract and mocked runner tests run first and do not create GitHub resources.
