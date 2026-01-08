# Test Terraform Branch Deploy

This repository serves as a **test environment** for the [terraform-branch-deploy](https://github.com/scarowar/terraform-branch-deploy) GitHub Action.

## Purpose

- E2E testing of terraform-branch-deploy features
- Validation of PR comment workflows (`.plan`, `.apply`, etc.)
- Testing various configuration scenarios

## Repository Structure

```
test-terraform-branch-deploy/
├── .github/
│   └── workflows/
│       ├── terraform-deploy.yml    # Main deployment workflow
│       └── e2e-tests.yml           # Automated E2E test runner
├── terraform/
│   ├── common.tfvars               # Shared variables
│   ├── dev/                        # Dev environment config
│   │   ├── main.tf
│   │   └── dev.tfvars
│   └── prod/                       # Prod environment config
│       ├── main.tf
│       └── prod.tfvars
├── tests/
│   └── e2e/                        # E2E test suite
│       ├── conftest.py             # Test fixtures
│       ├── runner.py               # Test runner utilities
│       └── test_*.py               # Test files
├── scripts/
│   └── cleanup-e2e.py              # Cleanup test artifacts
├── .tf-branch-deploy.yml           # terraform-branch-deploy config
└── pyproject.toml                  # Python project config
```

## Environments

| Environment | Working Directory | Production | Description |
|-------------|-------------------|------------|-------------|
| `dev` | `terraform/dev` | No | Development environment |
| `prod` | `terraform/prod` | Yes | Production environment (requires confirmation) |

## Testing Commands

Comment on a PR to trigger these commands:

| Command | Description |
|---------|-------------|
| `.plan to dev` | Run terraform plan for dev |
| `.plan to prod` | Run terraform plan for prod (production warning) |
| `.apply to dev` | Apply changes to dev (requires prior plan) |
| `.lock dev` | Lock dev environment |
| `.unlock dev` | Unlock dev environment |
| `.help` | Show available commands |
| `.wcid` | Who Currently Is Deploying |

### Extra Arguments

Pass terraform arguments after `|`:

```
.plan to dev | -target=local_file.test
.plan to dev | -var='key=value'
.plan to dev | -refresh=false -parallelism=2
```

## E2E Test Suite

### Running Tests Locally

```bash
# Install dependencies
uv sync --dev

# Run all E2E tests
GITHUB_TOKEN=xxx uv run pytest tests/e2e/ -v

# Run specific tests
GITHUB_TOKEN=xxx uv run pytest tests/e2e/ -v -k "test_basic_plan"
```

### Cleaning Up Test Artifacts

```bash
# Dry run (see what would be deleted)
GITHUB_TOKEN=xxx uv run python scripts/cleanup-e2e.py

# Actually delete
GITHUB_TOKEN=xxx uv run python scripts/cleanup-e2e.py --execute
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | GitHub token with repo access | Yes |
| `E2E_FORCE_CLEANUP` | Cleanup after each test | Default: `true` |
| `E2E_CLEANUP_DELAY` | Rate limit delay (seconds) | Default: `0.5` |

## Terraform Configuration

This repo uses the `local_file` provider for testing - **no cloud credentials needed**.

The terraform configs:
- Create a simple text file as output
- Include test variables for E2E tests
- Use local backend (state stored locally)

### Test Variables

The following variables are available for testing `-var` arguments:

| Variable | Type | Description |
|----------|------|-------------|
| `environment` | string | Environment name (required) |
| `message` | string | Test message |
| `key` | string | Test variable for `-var='key=value'` |
| `msg` | string | Test variable for `-var='msg=hello world'` |
| `tags` | any | Test variable for JSON values |
| `connection_string` | string | Test for complex values |
| `test_var` | string | Generic test variable |

## Workflows

### terraform-deploy.yml

The main deployment workflow that:
- Triggers on PR comments
- Uses terraform-branch-deploy action
- Includes a pre-terraform hook example

### e2e-tests.yml

Automated E2E test workflow:
- Runs on schedule (daily at 6am UTC)
- Can be triggered manually with filters
- Uses a PAT token for test operations

## Development

### Adding New Tests

```python
# tests/e2e/test_my_feature.py
import pytest
from tests.e2e.runner import E2ETestRunner

@pytest.mark.e2e
class TestMyFeature:
    def test_my_scenario(self, runner: E2ETestRunner) -> None:
        # Setup creates branch + PR (auto-cleaned after test)
        branch, pr, sha = runner.setup_test_pr("my_test")
        
        # Post command and wait for workflow
        run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        
        # Assert results
        runner.assert_workflow_success(run)
```

### See Also

- [E2E Testing Guide](tests/e2e/README.md)
- [terraform-branch-deploy Documentation](https://github.com/scarowar/terraform-branch-deploy)
