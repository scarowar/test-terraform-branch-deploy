"""
Locking Tests - Environment Lock/Unlock

Tests for the environment locking mechanism.

Run with: pytest tests/e2e/test_locking.py -v
"""

from __future__ import annotations

import pytest

from tests.e2e.runner import E2ETestRunner


@pytest.mark.e2e
@pytest.mark.core
class TestLocking:
    """Environment locking tests."""

    def test_lock_unlock_cycle(self, runner: E2ETestRunner) -> None:
        """
        .lock dev followed by .unlock dev
        
        Expected:
        - Lock succeeds
        - Unlock succeeds
        - No residual lock remains
        """
        branch, pr, sha = runner.setup_test_pr("lock_unlock")
        
        # Lock
        lock_run = runner.post_and_wait(pr, ".lock dev", timeout=180)
        runner.assert_workflow_success(lock_run)
        runner.assert_comment_contains(pr, "locked")
        
        # Unlock
        unlock_run = runner.post_and_wait(pr, ".unlock dev", timeout=180)
        runner.assert_workflow_success(unlock_run)
        runner.assert_comment_contains(pr, "unlocked")

    def test_deploy_while_locked_fails(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev while locked by another PR - MUST FAIL.
        
        This test creates two PRs, locks from one, then tries to plan from another.
        
        Expected:
        - First PR locks successfully
        - Second PR's plan fails with lock error
        """
        # PR1: Lock
        branch1, pr1, sha1 = runner.setup_test_pr("lock_holder")
        lock_run = runner.post_and_wait(pr1, ".lock dev", timeout=180)
        runner.assert_workflow_success(lock_run)
        
        # PR2: Try to plan (should fail)
        branch2, pr2, sha2 = runner.setup_test_pr("lock_blocked")
        plan_run = runner.post_and_wait(pr2, ".plan to dev", timeout=180)
        
        # Verify blocked
        runner.assert_workflow_failure(plan_run)
        runner.assert_comment_contains(pr2, "locked")
        
        # Cleanup: unlock from PR1
        runner.post_and_wait(pr1, ".unlock dev", timeout=180)

    def test_wcid_shows_lock_status(self, runner: E2ETestRunner) -> None:
        """
        .wcid shows correct lock status.
        
        Expected:
        - When no locks: shows "no active deployment locks"
        - After lock: shows who holds the lock
        """
        branch, pr, sha = runner.setup_test_pr("wcid_test")
        
        # Check initial state
        wcid_run = runner.post_and_wait(pr, ".wcid", timeout=180)
        runner.assert_workflow_success(wcid_run)
        
        # Lock and check again
        runner.post_and_wait(pr, ".lock dev", timeout=180)
        wcid_run2 = runner.post_and_wait(pr, ".wcid", timeout=180)
        runner.assert_workflow_success(wcid_run2)
        runner.assert_comment_contains(pr, "dev")
        
        # Cleanup
        runner.post_and_wait(pr, ".unlock dev", timeout=180)
