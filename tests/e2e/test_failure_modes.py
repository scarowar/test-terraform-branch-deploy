"""
Failure Mode Tests - Error Handling and Edge Cases

Tests that validate error handling and failure scenarios.
These tests expect workflows to fail in specific ways.

Run with: pytest tests/e2e/test_failure_modes.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.failures
class TestFailureModes:
    """Tests that validate error handling."""

    @pytest.mark.critical
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

    @pytest.mark.critical
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
        runner.assert_logs_contain(apply_run.id, "No plan file found")
        runner.assert_no_direct_apply_without_plan(apply_run.id)

    @pytest.mark.edge
    def test_malformed_command_ignored(self, runner: E2ETestRunner) -> None:
        """
        Random comment should not trigger workflow.
        
        Expected:
        - No workflow triggered
        - No bot response
        """
        branch, pr, sha = runner.setup_test_pr("malformed")
        
        # Post non-command comment
        before_comment = datetime.now(timezone.utc).isoformat()
        runner.post_comment(pr, "This is just a regular comment")

        runner.assert_no_workflow_after(before_comment)
        
        # Should have no bot response for random comment
        comment = runner.get_latest_bot_comment(pr)
        # Bot might respond with "not a valid trigger" or not at all
        # Either is acceptable
        if comment:
            assert "Deployment Results" not in comment.body


@pytest.mark.e2e
@pytest.mark.failures
class TestTerraformErrors:
    """Tests for Terraform execution failures."""

    @pytest.mark.critical
    def test_terraform_init_failure(self, runner: E2ETestRunner) -> None:
        """
        Terraform init fails due to invalid backend config.
        
        Risk: Backend misconfiguration, S3 bucket access denied
        Code Path: cli.py:366-369
        """
        branch = f"e2e-init-fail-{int(id(self)):x}"
        
        runner.create_branch(branch)
        
        # Create invalid backend config
        runner.commit_file(
            branch=branch,
            path="terraform/dev/backend.tf",
            content='terraform {\n  backend "s3" {\n    bucket = "nonexistent-bucket-12345"\n    key = "test.tfstate"\n    region = "us-east-1"\n  }\n}\n',
            message="test: add invalid backend",
        )
        
        runner.commit_file(
            branch=branch,
            path="terraform/dev/test.tfvars",
            content="init_fail = true",
            message="test: init failure scenario",
        )
        
        pr = runner.create_pr(branch=branch, title="E2E: Init Failure")
        
        try:
            run = runner.post_and_wait(pr, ".plan to dev", timeout=300)
            # Init should fail
            runner.assert_workflow_failure(run)
            runner.assert_comment_contains(pr, "Cannot proceed with deployment")
            runner.assert_no_direct_apply_without_plan(run.id)
        finally:
            runner.cleanup_test_pr(branch, pr)

@pytest.mark.e2e
@pytest.mark.failures
class TestSafetyChecks:
    """Tests that validate safety mechanisms."""

    @pytest.mark.critical
    def test_command_injection_blocked(self, runner: E2ETestRunner) -> None:
        """
        Shell injection via -var is NOT executed.
        
        Risk: `-var='$(rm -rf /)'` could execute malicious commands
        Prevention: Proper arg parsing without shell expansion (cli.py _parse_extra_args)
        """
        branch, pr, sha = runner.setup_test_pr("injection")
        
        # Attempt shell injection via -var
        malicious_cmd = ".plan to dev | -var='test=$(echo INJECTED)'"
        run = runner.post_and_wait(pr, malicious_cmd, timeout=300)
        
        # Should complete (injection fails silently or is escaped)
        # The key test is that no actual shell command ran
        # We verify by checking the comment doesn't contain "INJECTED"
        comment = runner.get_latest_bot_comment(pr)
        assert comment is not None, "Expected deployment result comment"
        assert "INJECTED" not in comment.body, "Shell injection was executed!"

    @pytest.mark.edge
    def test_help_command(self, runner: E2ETestRunner) -> None:
        """
        .help command returns help text.
        
        Risk: Help text outdated or incorrect
        """
        branch, pr, sha = runner.setup_test_pr("help")
        
        run = runner.post_and_wait(pr, ".help", timeout=180)
        
        runner.assert_workflow_success(run)
        # Help should mention available commands
        runner.assert_comment_contains(pr, ".plan")
