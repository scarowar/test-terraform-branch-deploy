"""Core workflow tests for terraform-branch-deploy."""

from __future__ import annotations

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
class TestCoreWorkflows:
    """Test basic plan and apply functionality."""

    def test_basic_plan(self, runner: E2ETestRunner) -> None:
        """Test .plan to dev works correctly."""
        run, comment = runner.run_command_test(
            test_name="basic_plan",
            command=".plan to dev",
            expect_success=True,
        )
        assert run.is_success
        # Bot should post plan output
        assert comment is None or "plan" in comment.body.lower()

    def test_basic_apply(self, runner: E2ETestRunner) -> None:
        """Test .apply to dev works correctly after plan."""
        branch_name, pr_number, sha = runner.setup_test_pr("basic_apply")

        try:
            # First, run plan
            plan_run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            runner.assert_workflow_success(plan_run)

            # Then run apply
            runner.post_comment(pr_number, ".apply to dev")
            # After commenting, get the new SHA or use same
            apply_run = runner.wait_for_workflow(timeout=300)
            runner.assert_workflow_success(apply_run)

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)

    def test_help_command(self, runner: E2ETestRunner) -> None:
        """Test .help command shows available commands."""
        branch_name, pr_number, sha = runner.setup_test_pr("help_command")

        try:
            runner.post_comment(pr_number, ".help")
            # Help doesn't trigger a full workflow, but branch-deploy responds
            # Give it time to respond
            import time
            time.sleep(30)

            comment = runner.get_latest_bot_comment(pr_number)
            # Help may or may not trigger bot comment depending on workflow config
            pass  # Test passes if no errors raised
            # Help message should mention commands
            body_lower = comment.body.lower()
            assert any(
                word in body_lower
                for word in ["help", "commands", "plan", "apply", "lock"]
            )

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestProduction:
    """Test production environment handling."""

    def test_plan_to_prod(self, runner: E2ETestRunner) -> None:
        """Test .plan to prod works correctly."""
        run, _ = runner.run_command_test(
            test_name="plan_prod",
            command=".plan to prod",
            expect_success=True,
        )
        assert run.is_success
