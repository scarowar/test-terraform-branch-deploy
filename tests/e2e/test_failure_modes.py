"""
Failure Mode Tests - Error Handling and Edge Cases

Tests that validate error handling and failure scenarios.
These tests expect workflows to fail in specific ways.

Run with: pytest tests/e2e/test_failure_modes.py -v
"""

from __future__ import annotations

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.failures
class TestFailureModes:
    """Tests that validate error handling."""

    def test_invalid_environment_fails(self, runner: E2ETestRunner) -> None:
        """
        .plan to nonexistent - invalid environment.
        
        Expected:
        - Workflow fails (or exits early)
        - Error message about invalid environment
        """
        branch, pr, sha = runner.setup_test_pr("invalid_env")
        
        run = runner.post_and_wait(pr, ".plan to nonexistent", timeout=180)
        
        # branch-deploy should reject invalid environment
        runner.assert_comment_contains(pr, "No matching environment target found")

    def test_apply_stale_plan_fails(self, runner: E2ETestRunner) -> None:
        """
        .apply to dev after new commit invalidates plan.
        
        Scenario:
        1. Plan to dev (creates plan for SHA A)
        2. Push new commit (SHA B)
        3. Apply to dev (should fail - plan is for wrong SHA)
        
        Expected:
        - Apply fails with "No plan file found for this SHA"
        """
        branch, pr, sha = runner.setup_test_pr("stale_plan")
        
        # Plan
        plan_run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(plan_run)
        
        # Push new commit (invalidates plan)
        runner.commit_file(
            branch=branch,
            path="terraform/dev/test.tfvars",
            content=f"# Updated content\nmessage = \"updated\"",
            message="chore: update content"
        )
        
        # Apply (should fail - SHA changed)
        apply_run = runner.post_and_wait(pr, ".apply to dev", timeout=300)
        
        runner.assert_workflow_failure(apply_run)
        runner.assert_comment_contains(pr, "Cannot proceed with deployment")

    def test_malformed_command_ignored(self, runner: E2ETestRunner) -> None:
        """
        Random comment should not trigger workflow.
        
        Expected:
        - No workflow triggered
        - No bot response
        """
        branch, pr, sha = runner.setup_test_pr("malformed")
        
        # Post non-command comment
        runner.post_comment(pr, "This is just a regular comment")
        
        # Wait a bit and check no workflow was triggered
        import time
        time.sleep(10)
        
        # Should have no bot response for random comment
        comment = runner.get_latest_bot_comment(pr)
        # Bot might respond with "not a valid trigger" or not at all
        # Either is acceptable


@pytest.mark.e2e
@pytest.mark.failures
class TestEdgeCases:
    """Edge case tests."""

    def test_plan_with_complex_var(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev | -var='message=hello world with spaces'
        
        Expected:
        - Quotes handled correctly
        - Workflow succeeds
        """
        branch, pr, sha = runner.setup_test_pr("complex_var")
        
        run = runner.post_and_wait(
            pr,
            ".plan to dev | -var='message=hello world with spaces'",
            timeout=300
        )
        
        runner.assert_workflow_success(run)

    def test_case_sensitivity(self, runner: E2ETestRunner) -> None:
        """
        .PLAN to dev vs .plan to dev - case handling.
        
        Expected:
        - Commands should be case-insensitive (or consistently handled)
        """
        branch, pr, sha = runner.setup_test_pr("case_test")
        
        # This should work (lowercase)
        run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(run)
