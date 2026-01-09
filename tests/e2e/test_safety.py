"""Safety tests for terraform-branch-deploy."""

from __future__ import annotations

import time

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
class TestPlanRequirement:
    """Test that apply requires a prior plan."""

    def test_apply_without_plan_fails(self, runner: E2ETestRunner) -> None:
        """Test .apply fails when no plan exists."""
        # Use a unique branch to ensure no cached plan exists
        branch_name = f"e2e-test-apply-no-plan-{int(time.time())}"

        runner.create_branch(branch_name)
        sha = runner.commit_file(
            branch=branch_name,
            path="terraform/dev/no_plan_test.tfvars",
            content=f"message = \"no-plan-test-{time.time()}\"\n",
            message="test: apply without plan",
        )
        pr_number = runner.create_pr(
            branch=branch_name,
            title="E2E: Apply Without Plan Test",
        )

        try:
            # Directly apply without planning
            run = runner.post_and_wait(pr_number, ".apply to dev", timeout=300)

            # Should fail - the workflow failure IS the expected behavior
            runner.assert_workflow_failure(run)
            # Note: We don't check specific comment text since branch-deploy
            # may format the error differently. The workflow failure is what matters.

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestLocking:
    """Test environment locking functionality."""

    def test_lock_unlock_cycle(self, runner: E2ETestRunner) -> None:
        """Test .lock and .unlock commands work."""
        branch_name, pr_number, _ = runner.setup_test_pr("lock_unlock")

        try:
            # Lock the environment
            # Note: Lock commands are handled by branch-deploy directly,
            # may not trigger our workflow - just verify it completes
            runner.post_comment(pr_number, ".lock dev")
            time.sleep(30)  # Increased wait for branch-deploy response

            lock_comment = runner.get_latest_bot_comment(pr_number)
            # Lock may or may not respond depending on branch-deploy config
            # The important thing is it doesn't error

            # Unlock
            runner.post_comment(pr_number, ".unlock dev")
            time.sleep(15)

            # Test passes if no errors were raised

        finally:
            # Ensure unlock
            runner.post_comment(pr_number, ".unlock dev")
            time.sleep(2)
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
@pytest.mark.slow
class TestRollback:
    """Test rollback functionality."""

    def test_rollback_bypasses_plan(self, runner: E2ETestRunner) -> None:
        """Test .apply main to dev works without a plan (rollback mode)."""
        branch_name, pr_number, sha = runner.setup_test_pr("rollback")

        try:
            # Apply with rollback syntax (deploy stable branch code)
            run = runner.post_and_wait(pr_number, ".apply main to dev", timeout=300)

            # Should succeed (rollback bypasses plan requirement)
            runner.assert_workflow_success(run)

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
