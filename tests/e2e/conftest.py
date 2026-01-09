"""Pytest configuration and fixtures for E2E tests."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import pytest

from tests.e2e.runner import E2ETestRunner


# =============================================================================
# CONFIGURATION
# =============================================================================

# Set to True to enable VCR-style mock testing (replay recorded responses)
E2E_USE_MOCKS = os.environ.get("E2E_USE_MOCKS", "false").lower() == "true"

# Set to True to force cleanup even if test passes
E2E_FORCE_CLEANUP = os.environ.get("E2E_FORCE_CLEANUP", "true").lower() == "true"

# Delay between cleanup operations to avoid rate limiting
E2E_CLEANUP_DELAY = float(os.environ.get("E2E_CLEANUP_DELAY", "0.5"))


# =============================================================================
# ARTIFACT TRACKING
# =============================================================================

@dataclass
class TestArtifacts:
    """Track test artifacts for cleanup."""
    branches: list[str] = field(default_factory=list)
    prs: list[int] = field(default_factory=list)
    
    def add_branch(self, branch: str) -> None:
        if branch not in self.branches:
            self.branches.append(branch)
    
    def add_pr(self, pr_number: int) -> None:
        if pr_number not in self.prs:
            self.prs.append(pr_number)
    
    def clear(self) -> None:
        self.branches.clear()
        self.prs.clear()


# Global artifact tracker
_artifacts = TestArtifacts()


def get_artifact_tracker() -> TestArtifacts:
    """Get the global artifact tracker."""
    return _artifacts


# =============================================================================
# PYTEST HOOKS
# =============================================================================

def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest markers."""
    config.addinivalue_line("markers", "e2e: mark test as E2E (requires GitHub token)")
    config.addinivalue_line("markers", "slow: mark test as slow")
    config.addinivalue_line("markers", "chaos: mark test as chaos testing")
    config.addinivalue_line("markers", "vcr: mark test for VCR-style mock testing")


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip E2E tests if no GitHub token is available."""
    if not os.environ.get("GITHUB_TOKEN") and not E2E_USE_MOCKS:
        skip_e2e = pytest.mark.skip(reason="GITHUB_TOKEN not set (set E2E_USE_MOCKS=true for mock testing)")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def runner() -> E2ETestRunner:
    """Create a shared E2E test runner for the session.
    
    The runner is shared across all tests in the session for efficiency.
    Cleanup happens after each individual test via the cleanup fixture.
    """
    with E2ETestRunner() as r:
        # Inject artifact tracker
        r._artifact_tracker = _artifacts
        yield r


@pytest.fixture
def fresh_runner() -> E2ETestRunner:
    """Create a fresh runner for each test."""
    with E2ETestRunner() as r:
        r._artifact_tracker = _artifacts
        yield r


@pytest.fixture(autouse=True)
def cleanup_test_artifacts(runner: E2ETestRunner, request: pytest.FixtureRequest):
    """Automatically cleanup test artifacts after each test.
    
    This fixture:
    1. Runs before each test (clears artifact tracker)
    2. Yields control to the test
    3. Cleans up all tracked artifacts (branches, PRs) after test
    
    Cleanup happens regardless of test outcome (pass/fail/error).
    """
    # Clear tracker before test
    _artifacts.clear()
    
    yield  # Run the test
    
    # Cleanup after test
    if not E2E_FORCE_CLEANUP:
        return
    
    # Close PRs first (so branches can be deleted)
    for pr_number in _artifacts.prs:
        try:
            runner.close_pr(pr_number)
            time.sleep(E2E_CLEANUP_DELAY)
        except Exception as e:
            print(f"⚠️ Failed to close PR #{pr_number}: {e}")
    
    # Delete branches
    for branch in _artifacts.branches:
        try:
            runner.delete_branch(branch)
            time.sleep(E2E_CLEANUP_DELAY)
        except Exception as e:
            print(f"⚠️ Failed to delete branch {branch}: {e}")
    
    _artifacts.clear()


@pytest.fixture
def artifacts() -> TestArtifacts:
    """Provide access to the artifact tracker for tests."""
    return _artifacts


# =============================================================================
# VCR/MOCK TESTING (Future Enhancement)
# =============================================================================

# To enable VCR-style testing, install pytest-vcr and add:
#
# @pytest.fixture(scope="module")
# def vcr_config():
#     return {
#         "cassette_library_dir": "tests/e2e/cassettes",
#         "record_mode": "once",  # or "none" for pure playback
#         "match_on": ["method", "scheme", "host", "port", "path", "query"],
#         "filter_headers": ["authorization"],
#     }
#
# Then mark tests with @pytest.mark.vcr()
