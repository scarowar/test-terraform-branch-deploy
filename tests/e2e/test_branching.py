"""Pull request lifecycle tests for terraform-branch-deploy."""

from __future__ import annotations

import time

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.stateful
class TestAutoMergePrevention:
    """Test that deployments don't auto-merge PRs."""

    def test_pr_remains_open_after_apply(self, runner: E2ETestRunner) -> None:
        """Test that PR stays open after successful apply."""
        branch_name, pr_number, sha = runner.setup_test_pr("auto_merge_test")

        try:
            # Plan first
            plan_run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            runner.assert_workflow_success(plan_run)

            # Apply
            apply_run = runner.post_and_wait(pr_number, ".apply to dev", timeout=300)
            runner.assert_workflow_success(apply_run)

            # Check PR is still open
            time.sleep(5)
            pr = runner.get_pr(pr_number)
            assert pr["state"] == "open", "PR should remain open after apply"
            assert pr["merged"] is False, "PR should not be merged"

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
