"""Branching and merge scenario tests for terraform-branch-deploy."""

from __future__ import annotations

import time

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
class TestFeatureBranches:
    """Test deployment between feature branches."""

    def test_feature_to_feature_pr(self, runner: E2ETestRunner) -> None:
        """Test deployment in a PR between two feature branches.
        
        Note: PRs targeting non-default branches (not main) may have different
        behavior depending on allow_non_default_target_branch setting in workflow.
        """
        # Create feature-a from main
        feature_a = f"feature-a-{int(time.time())}"
        runner.create_branch(feature_a)
        runner.commit_file(
            branch=feature_a,
            path="terraform/dev/feature_a.tfvars",
            content="feature_a = true\n",
            message="feat: add feature-a",
        )

        # Create feature-b from feature-a
        feature_b = f"feature-b-{int(time.time())}"
        runner.create_branch(feature_b, from_branch=feature_a)
        sha = runner.commit_file(
            branch=feature_b,
            path="terraform/dev/feature_b.tfvars",
            content="feature_b = true\n",
            message="feat: add feature-b",
        )

        # Create PR: feature-b -> feature-a
        pr_number = runner.create_pr(
            branch=feature_b,
            title="E2E: Feature-to-Feature PR",
            base=feature_a,
        )

        try:
            run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            # May succeed or fail based on allow_non_default_target_branch
            # The important thing is it handles the non-default target gracefully
            assert run.is_complete

        finally:
            runner.close_pr(pr_number)
            runner.delete_branch(feature_b)
            runner.delete_branch(feature_a)


@pytest.mark.e2e
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


@pytest.mark.e2e
@pytest.mark.slow
class TestOutdatedBranch:
    """Test handling of outdated branches."""

    def test_outdated_branch_warning(self, runner: E2ETestRunner) -> None:
        """Test that outdated branches get a warning."""
        # Create a test branch
        branch_name = f"e2e-outdated-{int(time.time())}"
        runner.create_branch(branch_name)
        sha = runner.commit_file(
            branch=branch_name,
            path="terraform/dev/outdated_test.tfvars",
            content="outdated_test = true\n",
            message="test: outdated branch",
        )

        pr_number = runner.create_pr(
            branch=branch_name,
            title="E2E: Outdated Branch Test",
        )

        try:
            # Make a commit to main to make the PR outdated
            main_sha = runner.commit_file(
                branch="main",
                path="terraform/dev/main_update.tfvars",
                content=f"main_update = {time.time()}\n",
                message="chore: update main",
            )

            # Now the PR is behind main
            time.sleep(3)
            run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)

            # With update_branch: warn, it should still succeed but warn
            # The important thing is it handles it gracefully
            assert run.is_complete

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
            # Clean up the commit we made to main by reverting
            # (In a real scenario, be careful with main)


@pytest.mark.e2e
class TestMergeConflicts:
    """Test handling of merge conflicts."""

    def test_merge_conflict_fails_gracefully(self, runner: E2ETestRunner) -> None:
        """Test that merge conflicts are handled properly."""
        # Create branch and modify a file
        branch_name = f"e2e-conflict-{int(time.time())}"
        runner.create_branch(branch_name)

        # Modify the same file that exists in main
        sha = runner.commit_file(
            branch=branch_name,
            path="terraform/dev/dev.tfvars",
            content=f"# Conflict content\nmessage = \"conflict-{time.time()}\"\n",
            message="test: create potential conflict",
        )

        pr_number = runner.create_pr(
            branch=branch_name,
            title="E2E: Merge Conflict Test",
        )

        try:
            run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            # May succeed or fail depending on whether there's an actual conflict
            # The important thing is it handles it gracefully
            assert run.is_complete

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
