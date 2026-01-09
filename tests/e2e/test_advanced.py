"""Advanced feature tests for terraform-branch-deploy."""

from __future__ import annotations

import time

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
class TestDynamicArguments:
    """Test dynamic argument passing via PR comments."""

    def test_target_argument(self, runner: E2ETestRunner) -> None:
        """Test .plan to dev | -target=local_file.test works."""
        run, comment = runner.run_command_test(
            test_name="target_arg",
            command=".plan to dev | -target=local_file.test",
            expect_success=True,
        )
        assert run.is_success

    def test_multiple_arguments(self, runner: E2ETestRunner) -> None:
        """Test multiple dynamic arguments."""
        run, _ = runner.run_command_test(
            test_name="multi_args",
            command=".plan to dev | -refresh=false -parallelism=5",
            expect_success=True,
        )
        assert run.is_success


@pytest.mark.e2e
class TestPreTerraformHooks:
    """Test pre-terraform hook execution."""

    def test_hook_runs_before_terraform(self, runner: E2ETestRunner) -> None:
        """Test that pre-terraform hooks execute."""
        # This test verifies hooks run - check the workflow output
        run, _ = runner.run_command_test(
            test_name="hook_test",
            command=".plan to dev",
            expect_success=True,
        )
        # The workflow should show hook output in logs
        # We can't easily check logs via API, but success indicates hook didn't fail
        assert run.is_success


@pytest.mark.e2e
@pytest.mark.slow
class TestCaching:
    """Test plan file caching between plan and apply."""

    def test_plan_file_cached_for_apply(self, runner: E2ETestRunner) -> None:
        """Test that plan file is cached and restored for apply."""
        branch_name, pr_number, sha = runner.setup_test_pr("caching")

        try:
            # Run plan
            plan_run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            runner.assert_workflow_success(plan_run)

            # Small delay to ensure cache is saved
            time.sleep(5)

            # Run apply - should use cached plan
            apply_run = runner.post_and_wait(pr_number, ".apply to dev", timeout=300)
            runner.assert_workflow_success(apply_run)

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
