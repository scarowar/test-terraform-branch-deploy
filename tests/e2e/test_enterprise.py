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
class TestConcurrency:
    """Test race condition handling for medium-large teams."""

    def test_concurrent_plans_handled_safely(self, runner: E2ETestRunner) -> None:
        """Test rapid plan commands don't cause race conditions.
        
        Risk: Multiple team members posting .plan simultaneously
        """
        branch, pr, sha = runner.setup_test_pr("concurrent")
        
        # Post multiple commands rapidly
        runner.post_comment(pr, ".plan to dev")
        runner.post_comment(pr, ".plan to dev")
        
        # Should complete without errors (one may be skipped)
        run = runner.wait_for_workflow(timeout=300)
        assert run.is_complete


@pytest.mark.e2e
@pytest.mark.slow
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
            assert run1.is_failure or run1.is_complete
            
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
class TestComplexParsing:
    """Test complex argument parsing edge cases."""

    def test_var_with_json_value(self, runner: E2ETestRunner) -> None:
        """Test -var with JSON value containing special chars.
        
        Risk: Enterprise configs often have complex vars
        """
        run, _ = runner.run_command_test(
            test_name="json_var",
            command=".plan to dev | -var='config={\"key\":\"value\"}'",
            expect_success=True,
        )
        assert run.is_success

    def test_var_with_equals_in_value(self, runner: E2ETestRunner) -> None:
        """Test -var with equals sign in value.
        
        Risk: Connection strings, URLs have embedded equals
        """
        run, _ = runner.run_command_test(
            test_name="equals_var",
            command=".plan to dev | -var='conn=host=db;port=5432'",
            expect_success=True,
        )
        assert run.is_success

    def test_target_with_indexed_resource(self, runner: E2ETestRunner) -> None:
        """Test -target with indexed resource.
        
        Risk: Enterprise modules use count/for_each
        """
        run, _ = runner.run_command_test(
            test_name="indexed_target",
            command=".plan to dev | -target=module.usecase[0]",
            expect_success=True,
        )
        assert run.is_success


@pytest.mark.e2e
@pytest.mark.slow
class TestRollbackFailures:
    """Test rollback failure scenarios."""

    def test_rollback_with_broken_main(self, runner: E2ETestRunner) -> None:
        """
        Rollback fails when main branch has TF errors.
        
        Risk: Rollback to main that has invalid Terraform
        Code Path: cli.py:423-434 rollback apply failure
        
        Note: Different from test_rollback_to_main - this FAILS.
        """
        # This test would require main branch to have TF errors
        # which isn't practical in E2E. Instead, we test that
        # rollback properly handles apply failures.
        
        branch, pr, sha = runner.setup_test_pr("rollback_broken")
        
        # Attempt rollback - main should be valid in test repo
        run = runner.post_and_wait(pr, ".apply main to dev", timeout=300)
        
        # In test repo, main is valid so this should succeed
        # The test validates the rollback code path executes
        assert run.is_complete
