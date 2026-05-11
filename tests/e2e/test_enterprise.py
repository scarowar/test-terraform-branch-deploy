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
        
        sha = runner.commit_file(
            branch=branch,
            path="terraform/dev/test.tfvars",
            content="retry_test = true\n",
            message="test: retry scenario",
        )
        
        pr = runner.create_pr(branch=branch, title="E2E: Retry Test")
        
        try:
            # First plan should fail
            run1 = runner.post_and_wait(pr, ".plan to dev", timeout=300)
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
            run2 = runner.post_and_wait(pr, ".plan to dev", timeout=300)
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
        dev_run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(dev_run)
        
        # Plan to prod
        prod_run = runner.post_and_wait(pr, ".plan to prod", timeout=300)
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
            timeout=300
        )
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")

    def test_target_resource_arg(self, runner: E2ETestRunner) -> None:
        """Test -target for an existing resource.
        
        Risk: Terraform target arguments must be forwarded without shell parsing.
        """
        branch, pr, sha = runner.setup_test_pr("target_arg")
        
        run = runner.post_and_wait(
            pr,
            ".plan to dev | -target=local_file.test",
            timeout=300
        )
        
        runner.assert_workflow_success(run)
        runner.assert_logs_contain(run.id, "-target=local_file.test")
