"""
Enterprise Edge Case Tests

High-signal tests for enterprise-scale Terraform deployments:
- Concurrency and race conditions
- Recovery from failures
- Multi-environment deployments
- Complex argument parsing

Run with: pytest tests/e2e/test_enterprise.py -v
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.edge
class TestRecovery:
    """Test recovery from failure states."""

    def test_retry_after_terraform_failure(self, runner: E2ETestRunner) -> None:
        """Test that a failed plan can be retried after fix.
        
        Risk: Team member fixes error, retry must work
        """
        branch = f"e2e-retry-{int(id(self)):x}"
        
        runner.create_branch(branch)
        
        # First commit with error
        runner.commit_file(
            branch=branch,
            path="terraform/dev/will_fail.tf",
            content='resource "bad" {\n',  # Invalid
            message="test: add failing code",
        )
        
        runner.commit_file(
            branch=branch,
            path="terraform/dev/test.tfvars",
            content="retry_test = true\n",
            message="test: retry scenario",
        )
        
        pr = runner.create_pr(branch=branch, title="E2E: Retry Test")
        
        try:
            # First plan should fail
            run1 = runner.post_and_wait(pr, ".plan to dev")
            runner.assert_workflow_failure(run1)
            runner.assert_comment_contains(pr, "Cannot proceed with deployment")
            
            # Fix the error
            runner.commit_file(
                branch=branch,
                path="terraform/dev/will_fail.tf",
                content='resource "local_file" "fixed" {\n  filename = "/tmp/fixed.txt"\n  content = "fixed"\n}\n',
                message="fix: correct terraform syntax",
            )
            
            # Retry should succeed
            run2 = runner.post_and_wait(pr, ".plan to dev")
            runner.assert_workflow_success(run2)
        finally:
            runner.cleanup_test_pr(branch, pr)


@pytest.mark.e2e
@pytest.mark.core
class TestMultiEnvironment:
    """Test multi-environment deployment workflows."""

    def test_sequential_dev_to_prod(self, runner: E2ETestRunner) -> None:
        """Test deploying to dev then prod sequentially.
        
        Risk: Standard enterprise workflow - plan dev, plan prod
        """
        branch, pr, sha = runner.setup_test_pr("multi_env")
        
        # Plan to dev
        dev_run = runner.post_and_wait(pr, ".plan to dev")
        runner.assert_workflow_success(dev_run)
        
        # Plan to prod
        prod_run = runner.post_and_wait(pr, ".plan to prod")
        runner.assert_workflow_success(prod_run)


@pytest.mark.e2e
@pytest.mark.args
class TestComplexParsing:
    """Test complex argument parsing edge cases."""

    def test_var_with_equals_in_value(self, runner: E2ETestRunner) -> None:
        """Test -var with equals sign in value.
        
        Risk: Connection strings, URLs have embedded equals
        """
        branch, pr, sha = runner.setup_test_pr("equals_var")
        
        # Simple string with equals - avoid complex shell escaping
        run = runner.post_and_wait(
            pr,
            ".plan to dev | -var='connection_string=postgres://user:p@host/db?sslmode=require&x=y'",
        )
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")

    def test_config_plan_args_append_comment_args(self, runner: E2ETestRunner) -> None:
        """Test configured plan-args compose with PR comment args.

        Risk: Config-driven plan args and comment args must not overwrite each other.
        """
        branch, pr, sha = runner.setup_test_pr("config_plan_args")

        runner.commit_file(
            branch=branch,
            path=".tf-branch-deploy.yml",
            content=dedent("""
                default-environment: dev
                production-environments:
                  - prod
                stable-branch: main
                defaults:
                  plan-args:
                    args:
                      - "-parallelism=7"
                environments:
                  dev:
                    working-directory: ./terraform/dev
                    var-files:
                      paths:
                        - ../common.tfvars
                        - dev.tfvars
                  prod:
                    working-directory: ./terraform/prod
                    var-files:
                      paths:
                        - ../common.tfvars
                        - prod.tfvars
            """).lstrip(),
            message="test: add configured plan args",
        )

        run = runner.post_and_wait(
            pr,
            ".plan to dev | -target=local_file.test",
        )

        runner.assert_workflow_success(run)
        runner.assert_logs_contain(run.id, "-parallelism=7")
        runner.assert_logs_contain(run.id, "-target=local_file.test")
