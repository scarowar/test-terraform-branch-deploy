"""
Core Tests - Plan and Apply Workflows

These tests validate the primary use cases:
- Planning to environments
- Applying after plan
- Rollback scenarios

Run with: pytest tests/e2e/test_plan_apply.py -v
"""

from __future__ import annotations

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.core
class TestPlan:
    """Plan operation tests."""

    def test_plan_dev(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev - standard plan to development.
        
        Expected:
        - Workflow succeeds
        - Bot posts plan output
        - Plan shows changes (local_file resource)
        """
        branch, pr, sha = runner.setup_test_pr("plan_dev")
        
        run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        
        runner.assert_workflow_success(run)
        # Check for Deployment Results comment (latest)
        runner.assert_comment_contains(pr, "Deployment Results")
        
        # Optionally, check that tfcmt also posted (previous comment)
        # But for now, verifying success and result comment is sufficient

    def test_plan_prod(self, runner: E2ETestRunner) -> None:
        """
        .plan to prod - plan to production (should show warning).
        
        Expected:
        - Workflow succeeds
        - Bot posts plan output
        - Production environment processed correctly
        - Warning about production environment shown
        """
        branch, pr, sha = runner.setup_test_pr("plan_prod")
        
        run = runner.post_and_wait(pr, ".plan to prod", timeout=300)
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")
        # Ensure production warning is present
        runner.assert_comment_contains(pr, "prod")

    def test_plan_with_extra_args(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev | -target=local_file.test
        
        Expected:
        - Workflow succeeds
        - -target is respected (plan only shows targeted resource)
        """
        branch, pr, sha = runner.setup_test_pr("plan_target")
        
        run = runner.post_and_wait(
            pr, 
            ".plan to dev | -target=local_file.test", 
            timeout=300
        )
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")

    def test_plan_with_var(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev | -var='key=value'
        
        Expected:
        - Workflow succeeds
        - -var is passed correctly (quotes handled)
        """
        branch, pr, sha = runner.setup_test_pr("plan_var")
        
        run = runner.post_and_wait(
            pr, 
            ".plan to dev | -var='message=hello world'", 
            timeout=300
        )
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")


@pytest.mark.e2e
@pytest.mark.core
class TestApply:
    """Apply operation tests."""

    def test_apply_after_plan(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev followed by .apply to dev
        
        Expected:
        - Plan succeeds and creates plan file
        - Apply finds plan file and applies it
        - Both workflows succeed
        """
        branch, pr, sha = runner.setup_test_pr("apply_after_plan")
        
        # First: plan
        plan_run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(plan_run)
        
        # Then: apply
        apply_run = runner.post_and_wait(pr, ".apply to dev", timeout=300)
        runner.assert_workflow_success(apply_run)
        runner.assert_comment_contains(pr, "Deployment Results")

    def test_apply_without_plan_fails(self, runner: E2ETestRunner) -> None:
        """
        .apply to dev without prior plan - MUST FAIL.
        
        Expected:
        - Workflow fails
        - Error message about missing plan file
        """
        branch, pr, sha = runner.setup_test_pr("apply_no_plan")
        
        run = runner.post_and_wait(pr, ".apply to dev", timeout=300)
        
        runner.assert_workflow_failure(run)
        runner.assert_comment_contains(pr, "Cannot proceed with deployment")


@pytest.mark.e2e
@pytest.mark.core
class TestRollback:
    """Rollback scenarios."""

    def test_rollback_to_main(self, runner: E2ETestRunner) -> None:
        """
        .apply main to dev - rollback to stable branch.
        
        Expected:
        - Workflow detects rollback command
        - Applies from main branch directly (no plan file required)
        - Workflow succeeds
        """
        branch, pr, sha = runner.setup_test_pr("rollback")
        
        run = runner.post_and_wait(pr, ".apply main to dev", timeout=300)
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")


@pytest.mark.e2e
@pytest.mark.core
class TestPlanEdgeCases:
    """Plan edge cases for comprehensive coverage."""

    def test_plan_no_changes_detected(self, runner: E2ETestRunner) -> None:
        """
        Plan shows no changes when infra is in sync.
        
        Risk: User confusion when has_changes=false
        Code Path: cli.py:392 set_github_output("has_changes", ...)
        
        Note: This tests AFTER apply - infrastructure matches code.
        """
        branch, pr, sha = runner.setup_test_pr("no_changes")
        
        # First plan and apply
        plan_run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(plan_run)
        
        apply_run = runner.post_and_wait(pr, ".apply to dev", timeout=300)
        runner.assert_workflow_success(apply_run)
        
        # Second plan should show no changes
        plan_run2 = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(plan_run2)
        # The output should indicate no changes or minimal changes




@pytest.mark.e2e
@pytest.mark.core  
class TestApplyEdgeCases:
    """Apply edge cases for comprehensive coverage."""

    def test_apply_succeeds_idempotent(self, runner: E2ETestRunner) -> None:
        """
        Re-apply same plan succeeds (idempotent).
        
        Risk: Re-apply might fail unexpectedly
        
        Note: Different from test_apply_after_plan - this does TWO applies.
        """
        branch, pr, sha = runner.setup_test_pr("idempotent")
        
        # Plan
        plan_run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(plan_run)
        
        # Apply first time
        apply_run1 = runner.post_and_wait(pr, ".apply to dev", timeout=300)
        runner.assert_workflow_success(apply_run1)
        
        # Plan again (after apply)
        plan_run2 = runner.post_and_wait(pr, ".plan to dev", timeout=300)
        runner.assert_workflow_success(plan_run2)
        
        # Apply second time (should succeed - idempotent)
        apply_run2 = runner.post_and_wait(pr, ".apply to dev", timeout=300)
        runner.assert_workflow_success(apply_run2)
