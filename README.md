# Test Terraform Branch Deploy

E2E test repository for [terraform-branch-deploy](https://github.com/scarowar/terraform-branch-deploy) v0.2.0.

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

## Test Groups

Tests are organized by priority for efficient debugging:

| Group | Command | Purpose |
|-------|---------|---------|
| **Smoke** | `pytest -m smoke` | Run first - basic sanity |
| **Core** | `pytest -m core` | Plan, apply, lock workflows |
| **Failures** | `pytest -m failures` | Error handling |
| **All** | `pytest tests/e2e/` | Complete suite |

## Quick Start

```bash
# Install
uv sync --dev

# Export token
export GITHUB_TOKEN=ghp_xxx  # or E2E_PAT

# Run smoke tests first
uv run pytest tests/e2e/test_smoke.py -v

# Run core tests
uv run pytest tests/e2e/ -m core -v

# Run all tests
uv run pytest tests/e2e/ -v
```

## Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `test_smoke.py` | 3 | Basic plan, help, wcid |
| `test_plan_apply.py` | 7 | Plan/apply workflows |
| `test_locking.py` | 3 | Lock/unlock |
| `test_failure_modes.py` | 5 | Error handling |

## Environments

| Environment | Directory | Production |
|-------------|-----------|------------|
| `dev` | `terraform/dev` | No |
| `prod` | `terraform/prod` | Yes |

## Commands

| Command | Description |
|---------|-------------|
| `.plan to dev` | Plan to development |
| `.apply to dev` | Apply after plan |
| `.apply main to dev` | Rollback |
| `.lock dev` | Lock environment |
| `.unlock dev` | Unlock |
| `.wcid` | Who is deploying |
| `.help` | Help |

## CI

The E2E test workflow runs:
- Daily at 6am UTC
- On-demand via workflow_dispatch

```yaml
# .github/workflows/e2e-tests.yml
on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:
    inputs:
      test_filter:
        description: 'Test filter (e.g., "smoke" or "core")'
```

## Configuration

```yaml
# Environment variables
GITHUB_TOKEN           # Required - GitHub PAT with repo access
E2E_FORCE_CLEANUP=true # Auto-cleanup test PRs/branches
E2E_CLEANUP_DELAY=0.5  # Rate limit delay (seconds)
```
