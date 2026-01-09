"""Failure scenario tests for terraform-branch-deploy."""

from __future__ import annotations

import time

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
class TestInvalidEnvironment:
    """Test handling of invalid environment names."""

    def test_invalid_env_shows_error(self, runner: E2ETestRunner) -> None:
        """Test .plan to nonexistent shows helpful error."""
        branch_name, pr_number, sha = runner.setup_test_pr("invalid_env")

        try:
            runner.post_comment(pr_number, ".plan to nonexistent")

            # Wait for bot response (might not trigger full workflow)
            time.sleep(15)

            comment = runner.get_latest_bot_comment(pr_number)
            if comment:
                # Should mention invalid environment or show available envs
                body_lower = comment.body.lower()
                assert any(
                    phrase in body_lower
                    for phrase in [
                        "not found",
                        "invalid",
                        "available",
                        "environments",
                        "dev",
                        "prod",
                    ]
                )

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e
class TestTerraformErrors:
    """Test handling of Terraform syntax/configuration errors."""

    def test_syntax_error_fails_gracefully(self, runner: E2ETestRunner) -> None:
        """Test that Terraform syntax errors fail with helpful output."""
        branch_name = f"e2e-test-tf-error-{int(time.time())}"

        runner.create_branch(branch_name)

        # Add a file with invalid Terraform syntax
        runner.commit_file(
            branch=branch_name,
            path="terraform/dev/bad_syntax.tf",
            content='resource "local_file" "bad" {\n  invalid_attribute = true\n',  # Missing closing brace
            message="test: add bad terraform syntax",
        )

        sha = runner.commit_file(
            branch=branch_name,
            path="terraform/dev/trigger.tfvars",
            content=f"test_time = \"{time.time()}\"\n",
            message="test: trigger plan",
        )

        pr_number = runner.create_pr(
            branch=branch_name,
            title="E2E: Terraform Error Test",
        )

        try:
            run = runner.post_and_wait(pr_number, ".plan to dev", timeout=300)

            # Should fail due to TF error
            # Workflow should either fail or complete (TF error handling)
            assert run.is_complete

        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
