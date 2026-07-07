"""
Locking Tests - Environment Lock/Unlock

Tests for the environment locking mechanism.

Run with: pytest tests/e2e/test_locking.py -v
"""

from __future__ import annotations

import pytest

from tests.e2e.runner import QUICK_TIMEOUT, E2ETestRunner


@pytest.fixture(scope="module", autouse=True)
def clear_existing_locks(runner: E2ETestRunner) -> None:
    """Clear stale locks before asserting lock creation behavior."""
    runner.delete_lock_ref_if_exists("dev")
    runner.delete_lock_ref_if_exists("global")

    branch, pr, sha = runner.setup_test_pr("lock_preflight")
    try:
        for command in (".unlock dev", ".unlock --global"):
            run = runner.post_and_wait(pr, command, timeout=QUICK_TIMEOUT)
            assert run.is_complete
    finally:
        runner.cleanup_test_pr(branch, pr)
        runner.delete_lock_ref_if_exists("dev")
        runner.delete_lock_ref_if_exists("global")


@pytest.mark.e2e
@pytest.mark.core
@pytest.mark.stateful
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
        branch, pr, sha = runner.setup_test_pr("lock_cycle")
        
        # Lock
        lock_run = runner.post_and_wait(pr, ".lock dev", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(lock_run)
        runner.assert_comment_contains(pr, "Lock Claimed")
        runner.assert_lock_ref_exists("dev")
        
        # Unlock
        unlock_run = runner.post_and_wait(pr, ".unlock dev", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(unlock_run)
        runner.assert_comment_contains(pr, "Deployment Lock Removed")
        runner.assert_no_lock_ref("dev")

    def test_deploy_while_locked_by_owner_succeeds(self, runner: E2ETestRunner) -> None:
        """
        .plan to dev while locked by SAME user - SHOULD SUCCEED.
        
        Note: Cannot test blocking other users in single-user E2E environment.
        Validation focuses on confirming the owner isn't blocked (sticky lock).
        """
        # PR1: Lock
        branch1, pr1, sha1 = runner.setup_test_pr("lock_holder")
        lock_run = runner.post_and_wait(pr1, ".lock dev", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(lock_run)
        runner.assert_comment_contains(pr1, "Lock Claimed")
        runner.assert_lock_ref_exists("dev")
        
        # PR2: Try to plan (should succeed for same user)
        branch2, pr2, sha2 = runner.setup_test_pr("lock_owner")
        plan_run = runner.post_and_wait(pr2, ".plan to dev", timeout=QUICK_TIMEOUT)
        
        # Verify allowed
        runner.assert_workflow_success(plan_run)
        runner.assert_comment_contains(pr2, "Deployment Results")
        runner.assert_lock_ref_exists("dev")
        
        # Cleanup: unlock from PR1
        unlock_run = runner.post_and_wait(pr1, ".unlock dev", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(unlock_run)
        runner.assert_no_lock_ref("dev")

    def test_wcid_shows_lock_status(self, runner: E2ETestRunner) -> None:
        """
        .wcid shows correct lock status.
        
        Expected:
        - When no locks: shows "no active deployment locks"
        - After lock: shows who holds the lock
        """
        branch, pr, sha = runner.setup_test_pr("wcid_test")
        
        # Check initial state
        wcid_run = runner.post_and_wait(pr, ".wcid", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(wcid_run)
        
        # Lock and check again
        lock_run = runner.post_and_wait(pr, ".lock dev", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(lock_run)
        runner.assert_comment_contains(pr, "Lock Claimed")
        runner.assert_lock_ref_exists("dev")
        wcid_run2 = runner.post_and_wait(pr, ".wcid", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(wcid_run2)
        runner.assert_comment_contains(pr, "dev")
        
        # Cleanup
        unlock_run = runner.post_and_wait(pr, ".unlock dev", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(unlock_run)
        runner.assert_no_lock_ref("dev")

    def test_global_lock(self, runner: E2ETestRunner) -> None:
        """
        .lock --global should lock all environments.
        
        Risk: Global lock not blocking all environments
        Code Path: action.yml global-lock-flag input
        """
        branch, pr, sha = runner.setup_test_pr("global_lock")
        
        # Global lock
        lock_run = runner.post_and_wait(pr, ".lock --global", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(lock_run)
        runner.assert_comment_contains(pr, "Lock Claimed")
        runner.assert_lock_ref_exists("global")
        
        # Verify lock status shows global
        wcid_run = runner.post_and_wait(pr, ".wcid", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(wcid_run)
        runner.assert_comment_contains(pr, "(?i)global")
        
        # Cleanup: unlock global
        unlock_run = runner.post_and_wait(pr, ".unlock --global", timeout=QUICK_TIMEOUT)
        runner.assert_workflow_success(unlock_run)
        runner.assert_no_lock_ref("global")
