"""
Smoke Tests - Run First

These are the most critical tests that validate basic functionality.
If any of these fail, there's a fundamental issue with the integration.

Run with: pytest tests/e2e/test_smoke.py -v
"""

from __future__ import annotations

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.smoke
class TestSmoke:
    """Smoke tests - must pass before running full suite."""

    def test_plan_dev_basic(self, runner: E2ETestRunner) -> None:
        """
        Most basic test: .plan to dev
        
        Expected:
        - Workflow completes successfully
        - Bot posts plan output comment
        - Plan file is created
        """
        branch, pr, sha = runner.setup_test_pr("smoke_plan")
        
        run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Terraform will perform")

    def test_help_command(self, runner: E2ETestRunner) -> None:
        """
        .help command returns help text.
        
        Expected:
        - Workflow completes
        - Bot posts help message
        """
        branch, pr, sha = runner.setup_test_pr("smoke_help")
        
        run = runner.post_and_wait(pr, ".help", timeout=180)
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, ".plan")

    def test_wcid_command(self, runner: E2ETestRunner) -> None:
        """
        .wcid (Who Currently Is Deploying) shows lock status.
        
        Expected:
        - Workflow completes
        - Bot posts lock status
        """
        branch, pr, sha = runner.setup_test_pr("smoke_wcid")
        
        run = runner.post_and_wait(pr, ".wcid", timeout=180)
        
        runner.assert_workflow_success(run)
        # Should show "no locks" or lock info
        runner.assert_comment_contains(pr, "lock")
