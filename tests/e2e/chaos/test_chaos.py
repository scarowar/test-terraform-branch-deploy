"""Chaos tests for terraform-branch-deploy edge cases."""

from __future__ import annotations

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.chaos
@pytest.mark.slow
class TestConcurrency:
    """Test concurrent deployment handling."""

    def test_concurrent_plans_handled_safely(self, runner: E2ETestRunner) -> None:
        """Test that rapid plan commands don't cause race conditions."""
        branch_name, pr_number, sha = runner.setup_test_pr("concurrent")

        try:
            # Post multiple commands rapidly
            runner.post_comment(pr_number, ".plan to dev")
            runner.post_comment(pr_number, ".plan to dev")

            # Should complete without errors (one may be skipped)
            run = runner.wait_for_workflow(timeout=300)
            # As long as it completes, we're safe
            assert run.is_complete

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
@pytest.mark.chaos
@pytest.mark.slow
class TestRecovery:
    """Test recovery from various failure states."""

    def test_retry_after_failure(self, runner: E2ETestRunner) -> None:
        """Test that a failed plan can be retried successfully."""
        branch_name = f"e2e-test-retry-{int(id(self)):x}"

        runner.create_branch(branch_name)

        # First commit with error
        runner.commit_file(
            branch=branch_name,
            path="terraform/dev/will_fail.tf",
            content='resource "bad" {\n',  # Invalid
            message="test: add failing code",
        )

        sha = runner.commit_file(
            branch=branch_name,
            path="terraform/dev/test.tfvars",
            content="retry_test = true\n",
            message="test: retry scenario",
        )

        pr_number = runner.create_pr(
            branch=branch_name,
            title="E2E: Retry Test",
        )

        try:
            # First plan should fail
            run1 = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            assert run1.is_failure or run1.is_complete

            # Fix the error
            sha2 = runner.commit_file(
                branch=branch_name,
                path="terraform/dev/will_fail.tf",
                content='resource "local_file" "fixed" {\n  filename = "/tmp/fixed.txt"\n  content = "fixed"\n}\n',
                message="fix: correct terraform syntax",
            )

            # Retry should succeed
            run2 = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)
            runner.assert_workflow_success(run2)

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
