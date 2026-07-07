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
        
        run = runner.post_and_wait(pr, ".plan to prod")
        
        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")
        # Ensure production warning is present
        runner.assert_comment_contains(pr, "prod")


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
        plan_run = runner.post_and_wait(pr, ".plan to dev")
        runner.assert_workflow_success(plan_run)
        runner.assert_plan_artifacts_exist("dev", sha)
        runner.assert_no_lock_ref("dev")

        # Then: apply
        apply_run = runner.post_and_wait(pr, ".apply to dev")
        runner.assert_workflow_success(apply_run)
        runner.assert_comment_contains(pr, "Deployment Results")
        runner.assert_apply_used_plan(apply_run.id, f"tfplan-dev-{sha[:8]}.tfplan")
        runner.assert_no_lock_ref("dev")

    @pytest.mark.critical
    def test_apply_after_targeted_plan_uses_saved_target_plan(
        self, runner: E2ETestRunner
    ) -> None:
        """
        .plan to dev | -target=... followed by plain .apply to dev.

        Expected:
        - Plan succeeds with the target argument
        - Plain apply uses the saved targeted plan file
        - Apply does not run a fresh untargeted terraform apply
        """
        branch, pr, sha = runner.setup_test_pr("apply_targeted_plan")

        plan_run = runner.post_and_wait(
            pr,
            ".plan to dev | -target=local_file.test",
        )
        runner.assert_workflow_success(plan_run)
        runner.assert_logs_contain(plan_run.id, "-target=local_file.test")

        apply_run = runner.post_and_wait(pr, ".apply to dev")
        runner.assert_workflow_success(apply_run)
        runner.assert_apply_used_plan(apply_run.id, f"tfplan-dev-{sha[:8]}.tfplan")
        runner.assert_logs_contain(
            apply_run.id,
            "Plan was created with args: -target=local_file.test",
        )

    @pytest.mark.critical
    @pytest.mark.args
    def test_apply_rejects_extra_args_after_saved_targeted_plan(
        self, runner: E2ETestRunner
    ) -> None:
        """
        .plan with target followed by .apply with fresh args must fail.

        Expected:
        - Plan succeeds and saves the targeted plan.
        - Apply with new args is rejected before Terraform can run apply.
        - The saved plan remains the only allowed normal apply input.
        """
        branch, pr, sha = runner.setup_test_pr("apply_rejects_fresh_args")

        plan_run = runner.post_and_wait(
            pr,
            ".plan to dev | -target=local_file.test",
        )
        runner.assert_workflow_success(plan_run)

        apply_run = runner.post_and_wait(
            pr,
            ".apply to dev | -target=local_file.test",
        )

        runner.assert_workflow_failure(apply_run)
        runner.assert_logs_contain(
            apply_run.id,
            "Extra Terraform arguments are only supported on plan commands",
        )
        runner.assert_no_direct_apply_without_plan(apply_run.id)
        runner.assert_no_lock_ref("dev")
        runner.assert_comment_contains(pr, "Cannot proceed with deployment")

    @pytest.mark.critical
    def test_apply_without_plan_fails(self, runner: E2ETestRunner) -> None:
        """
        .apply to dev without prior plan - MUST FAIL.
        
        Expected:
        - Workflow fails
        - Error message about missing plan file
        """
        branch, pr, sha = runner.setup_test_pr("apply_no_plan")
        
        run = runner.post_and_wait(pr, ".apply to dev")

        runner.assert_workflow_failure(run)
        runner.assert_logs_contain(run.id, "No saved plan artifact found")
        runner.assert_no_direct_apply_without_plan(run.id)
        runner.assert_no_lock_ref("dev")
        runner.assert_comment_contains(pr, "Cannot proceed with deployment")

    @pytest.mark.critical
    def test_apply_refuses_superseded_plan_after_failed_replan(
        self, runner: E2ETestRunner
    ) -> None:
        """
        Incident regression: a superseded targeted plan must never be applied.

        Scenario (the production incident class this guards against):
        1. Targeted .plan succeeds - plan A is persisted.
        2. A second .plan for the SAME commit fails (undeclared -var), so its
           intent record exists but no plan artifact was produced.
        3. Plain .apply must refuse - applying plan A now would execute
           arguments that no longer match the latest plan command.

        Expected:
        - Apply fails and posts an actionable comment
        - Logs state the latest plan attempt produced no applyable plan
        - No terraform apply runs at all
        """
        branch, pr, sha = runner.setup_test_pr("superseded_plan")

        plan_a = runner.post_and_wait(
            pr,
            ".plan to dev | -target=local_file.test",
        )
        runner.assert_workflow_success(plan_a)
        runner.assert_plan_artifacts_exist("dev", sha)

        # Same commit, failing plan: -var for a variable the config does not
        # declare makes terraform plan error after the intent is recorded.
        plan_b = runner.post_and_wait(
            pr,
            ".plan to dev | -var=e2e_undeclared_guardrail_var=1",
        )
        runner.assert_workflow_failure(plan_b)
        runner.assert_comment_contains(pr, "Cannot proceed with deployment")

        apply_run = runner.post_and_wait(pr, ".apply to dev")

        runner.assert_workflow_failure(apply_run)
        runner.assert_logs_contain(apply_run.id, "did not produce an applyable plan")
        runner.assert_no_direct_apply_without_plan(apply_run.id)
        runner.assert_no_lock_ref("dev")
        runner.assert_comment_contains(pr, "did not produce an applyable plan")


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
        - Does not consume a stale saved plan for the PR branch
        - Workflow succeeds
        """
        branch, pr, sha = runner.setup_test_pr("rollback")

        plan_run = runner.post_and_wait(
            pr,
            ".plan to dev | -target=local_file.test",
        )
        runner.assert_workflow_success(plan_run)

        run = runner.post_and_wait(pr, ".apply main to dev")

        runner.assert_workflow_success(run)
        runner.assert_comment_contains(pr, "Deployment Results")
        runner.assert_logs_contain(run.id, "Rollback detected")
        runner.assert_logs_do_not_contain(run.id, "Plan was created with args")

    @pytest.mark.critical
    @pytest.mark.args
    def test_rollback_rejects_extra_args(self, runner: E2ETestRunner) -> None:
        """
        .apply main to dev with Terraform args must fail.

        Expected:
        - Workflow detects rollback.
        - CLI rejects the extra Terraform arguments because Terraform has no
          deterministic target-only rollback.
        - Rollback does not run a targeted direct apply.
        """
        branch, pr, sha = runner.setup_test_pr("rollback_rejects_args")

        run = runner.post_and_wait(
            pr,
            ".apply main to dev | -target=local_file.test",
        )

        runner.assert_workflow_failure(run)
        runner.assert_logs_contain(
            run.id,
            "Terraform does not provide a deterministic target-only rollback",
        )
        runner.assert_no_direct_apply_without_plan(run.id)
        runner.assert_no_lock_ref("dev")
        runner.assert_comment_contains(pr, "Cannot proceed with deployment")
