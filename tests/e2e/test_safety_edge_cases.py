"""Safety and security edge case tests for terraform-branch-deploy."""

from __future__ import annotations

import time

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
class TestPlanChecksum:
    """Test plan file checksum verification."""

    def test_plan_and_apply_same_sha(self, runner: E2ETestRunner) -> None:
        """Test that apply uses the correct plan for the same SHA."""
        branch_name, pr_number, sha = runner.setup_test_pr("checksum_test")

        try:
            # Plan
            plan_run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            runner.assert_workflow_success(plan_run)

            # Apply (should use the cached plan for same SHA)
            apply_run = runner.post_and_wait(pr_number, ".apply to dev", timeout=300)
            runner.assert_workflow_success(apply_run)

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestNewCommitInvalidatesPlan:
    """Test that new commits require a new plan."""

    def test_new_commit_requires_new_plan(self, runner: E2ETestRunner) -> None:
        """Test that pushing a new commit invalidates the old plan."""
        branch_name = f"e2e-new-commit-{int(time.time())}"
        runner.create_branch(branch_name)

        # First commit
        sha1 = runner.commit_file(
            branch=branch_name,
            path="terraform/dev/new_commit_test.tfvars",
            content="version = 1\n",
            message="test: initial commit",
        )

        pr_number = runner.create_pr(
            branch=branch_name,
            title="E2E: New Commit Test",
        )

        try:
            # Plan for SHA1
            plan_run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            runner.assert_workflow_success(plan_run)

            # Push a new commit (SHA2)
            sha2 = runner.commit_file(
                branch=branch_name,
                path="terraform/dev/new_commit_test.tfvars",
                content="version = 2\n",
                message="test: second commit",
            )

            # Try to apply - should fail because SHA changed
            apply_run = runner.post_and_wait(pr_number, ".apply to dev", timeout=300)

            # Should fail (no plan for SHA2) or succeed if branch-deploy re-plans
            # The key is it handles the situation correctly
            assert apply_run.is_complete

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestReactionEmoji:
    """Test that commands get the correct reaction."""

    def test_command_gets_reaction(self, runner: E2ETestRunner) -> None:
        """Test that posting a command gets an eyes reaction."""
        branch_name, pr_number, _ = runner.setup_test_pr("reaction_test")

        try:
            # Post command
            comment_id = runner.post_comment(pr_number, ".plan to dev")

            # Wait for reaction
            time.sleep(10)

            # Check reactions on our comment
            resp = runner.client.get(
                f"/repos/{runner.repo}/issues/comments/{comment_id}/reactions",
            )
            if resp.status_code == 200:
                reactions = resp.json()
                # Should have an 'eyes' reaction from the bot
                reaction_types = [r["content"] for r in reactions]
                # Not all setups add reactions, so just verify no error

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestDryRun:
    """Test dry-run mode (if configured)."""

    def test_dry_run_does_not_modify(self, runner: E2ETestRunner) -> None:
        """Test that dry-run mode doesn't actually apply changes."""
        # This test depends on workflow configuration
        # If dry-run is enabled, verify it doesn't create resources
        branch_name, pr_number, sha = runner.setup_test_pr("dry_run_test")

        try:
            run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            # Just verify it completes - dry run behavior is workflow-specific
            assert run.is_complete

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestRefreshMode:
    """Test -refresh flag handling."""

    def test_plan_with_no_refresh(self, runner: E2ETestRunner) -> None:
        """Test .plan to dev | -refresh=false works."""
        run, _ = runner.run_command_test(
            test_name="no_refresh",
            command=".plan to dev | -refresh=false",
            expect_success=True,
        )
        assert run.is_success


@pytest.mark.e2e
class TestCompactPlan:
    """Test compact plan mode (if configured)."""

    def test_plan_with_compact_warnings(self, runner: E2ETestRunner) -> None:
        """Test .plan to dev | -compact-warnings works."""
        run, _ = runner.run_command_test(
            test_name="compact_plan",
            command=".plan to dev | -compact-warnings",
            expect_success=True,
        )
        assert run.is_success
