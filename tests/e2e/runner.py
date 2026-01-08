"""
E2E Test Runner for terraform-branch-deploy.

Uses GitHub API to:
- Create test branches and PRs
- Post comments to trigger workflows
- Monitor workflow runs
- Validate results and assertions
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class WorkflowRun:
    """Represents a GitHub Actions workflow run."""

    id: int
    name: str
    status: str
    conclusion: str | None
    html_url: str
    logs_url: str
    created_at: str
    updated_at: str
    head_sha: str
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def is_success(self) -> bool:
        return self.conclusion == "success"

    @property
    def is_failure(self) -> bool:
        return self.conclusion == "failure"


@dataclass
class PRComment:
    """Represents a GitHub PR comment."""

    id: int
    body: str
    user: str
    created_at: str
    html_url: str


class E2ETestRunner:
    """
    Core E2E test runner for terraform-branch-deploy.

    Provides methods to:
    - Create and manage test PRs
    - Post comments that trigger workflows
    - Wait for workflow completion
    - Assert on results
    """

    def __init__(
        self,
        repo: str = "scarowar/test-terraform-branch-deploy",
        token: str | None = None,
        base_branch: str = "main",
    ):
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_branch = base_branch
        self.base_url = "https://api.github.com"

        if not self.token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN env var.")

        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> E2ETestRunner:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # === Branch Management ===

    def create_branch(self, branch_name: str, from_branch: str | None = None) -> str:
        """Create a new branch. Returns the SHA."""
        from_branch = from_branch or self.base_branch

        # Get the SHA of the base branch
        ref_resp = self.client.get(f"/repos/{self.repo}/git/refs/heads/{from_branch}")
        ref_resp.raise_for_status()
        sha = ref_resp.json()["object"]["sha"]

        # Create the new branch
        resp = self.client.post(
            f"/repos/{self.repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )
        resp.raise_for_status()
        return sha

    def delete_branch(self, branch_name: str) -> None:
        """Delete a branch."""
        resp = self.client.delete(f"/repos/{self.repo}/git/refs/heads/{branch_name}")
        if resp.status_code != 204:
            # Ignore 422 (branch doesn't exist)
            if resp.status_code != 422:
                resp.raise_for_status()

    def commit_file(
        self,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> str:
        """Create or update a file on a branch. Returns commit SHA."""
        # Check if file exists
        existing_sha = None
        get_resp = self.client.get(
            f"/repos/{self.repo}/contents/{path}",
            params={"ref": branch},
        )
        if get_resp.status_code == 200:
            existing_sha = get_resp.json()["sha"]

        import base64

        encoded = base64.b64encode(content.encode()).decode()

        data: dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if existing_sha:
            data["sha"] = existing_sha

        resp = self.client.put(f"/repos/{self.repo}/contents/{path}", json=data)
        resp.raise_for_status()
        return resp.json()["commit"]["sha"]

    # === PR Management ===

    def create_pr(
        self,
        branch: str,
        title: str,
        body: str = "",
        base: str | None = None,
    ) -> int:
        """Create a pull request. Returns PR number."""
        resp = self.client.post(
            f"/repos/{self.repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": base or self.base_branch,
            },
        )
        resp.raise_for_status()
        return resp.json()["number"]

    def close_pr(self, pr_number: int) -> None:
        """Close a pull request."""
        resp = self.client.patch(
            f"/repos/{self.repo}/pulls/{pr_number}",
            json={"state": "closed"},
        )
        resp.raise_for_status()

    def get_pr(self, pr_number: int) -> dict[str, Any]:
        """Get PR details."""
        resp = self.client.get(f"/repos/{self.repo}/pulls/{pr_number}")
        resp.raise_for_status()
        return resp.json()

    # === Comment Management ===

    def post_comment(self, pr_number: int, body: str) -> int:
        """Post a comment on a PR. Returns comment ID."""
        # Use issues API for PR comments
        resp = self.client.post(
            f"/repos/{self.repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def post_and_wait(
        self,
        pr_number: int,
        command: str,
        timeout: int = 300,
    ) -> WorkflowRun:
        """Post a comment and wait for the triggered workflow to complete.
        
        This is the preferred method for tests - it handles the timestamp
        tracking automatically.
        """
        from datetime import datetime, timezone
        before_comment = datetime.now(timezone.utc).isoformat()
        
        self.post_comment(pr_number, command)
        
        return self.wait_for_workflow(after_timestamp=before_comment, timeout=timeout)

    def get_comments(self, pr_number: int) -> list[PRComment]:
        """Get all comments on a PR."""
        resp = self.client.get(
            f"/repos/{self.repo}/issues/{pr_number}/comments",
            params={"per_page": 100},
        )
        resp.raise_for_status()
        return [
            PRComment(
                id=c["id"],
                body=c["body"],
                user=c["user"]["login"],
                created_at=c["created_at"],
                html_url=c["html_url"],
            )
            for c in resp.json()
        ]

    def get_latest_bot_comment(self, pr_number: int) -> PRComment | None:
        """Get the most recent comment from github-actions bot."""
        comments = self.get_comments(pr_number)
        for comment in reversed(comments):
            if comment.user in ("github-actions[bot]", "github-actions"):
                return comment
        return None

    # === Workflow Management ===

    def get_workflow_runs(
        self,
        event: str = "issue_comment",
        per_page: int = 10,
    ) -> list[WorkflowRun]:
        """Get recent workflow runs."""
        resp = self.client.get(
            f"/repos/{self.repo}/actions/runs",
            params={"event": event, "per_page": per_page},
        )
        resp.raise_for_status()
        runs = resp.json()["workflow_runs"]
        return [
            WorkflowRun(
                id=r["id"],
                name=r["name"],
                status=r["status"],
                conclusion=r["conclusion"],
                html_url=r["html_url"],
                logs_url=r["logs_url"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                head_sha=r["head_sha"],
                raw=r,
            )
            for r in runs
        ]

    def get_workflow_run(self, run_id: int) -> WorkflowRun:
        """Get a specific workflow run."""
        resp = self.client.get(f"/repos/{self.repo}/actions/runs/{run_id}")
        resp.raise_for_status()
        r = resp.json()
        return WorkflowRun(
            id=r["id"],
            name=r["name"],
            status=r["status"],
            conclusion=r["conclusion"],
            html_url=r["html_url"],
            logs_url=r["logs_url"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            head_sha=r["head_sha"],
            raw=r,
        )

    def wait_for_workflow(
        self,
        after_timestamp: str | None = None,
        timeout: int = 300,
        poll_interval: int = 10,
    ) -> WorkflowRun:
        """
        Wait for a workflow run to complete.

        Args:
            after_timestamp: ISO timestamp - only consider runs created after this
            timeout: Maximum seconds to wait
            poll_interval: Seconds between polls

        Returns:
            The completed WorkflowRun

        Raises:
            TimeoutError: If workflow doesn't complete in time
        """
        from datetime import datetime, timezone

        start = time.time()
        
        # Use current time if no timestamp provided
        if after_timestamp is None:
            after_dt = datetime.now(timezone.utc)
        else:
            after_dt = datetime.fromisoformat(after_timestamp.replace("Z", "+00:00"))

        # Track the run we're waiting for
        target_run_id: int | None = None

        while time.time() - start < timeout:
            runs = self.get_workflow_runs(per_page=20)
            
            for run in runs:
                # Parse the created_at timestamp
                created = datetime.fromisoformat(run.created_at.replace("Z", "+00:00"))
                
                # Only consider runs created after our timestamp
                if created > after_dt:
                    if target_run_id is None:
                        target_run_id = run.id
                    
                    # If this is our target run, check if complete
                    if run.id == target_run_id:
                        if run.is_complete:
                            return run
                        break  # Found our run but it's not complete yet
            
            time.sleep(poll_interval)

        msg = f"Workflow did not complete within {timeout}s"
        if target_run_id:
            msg += f" (run_id: {target_run_id})"
        raise TimeoutError(msg)

    def get_workflow_logs(self, run_id: int) -> str:
        """Get workflow run logs as text."""
        resp = self.client.get(
            f"/repos/{self.repo}/actions/runs/{run_id}/logs",
            follow_redirects=True,
        )
        if resp.status_code == 200:
            # Logs come as a zip file, return raw for now
            return f"[Logs available at workflow run {run_id}]"
        return ""

    # === Assertions ===

    def assert_workflow_success(self, run: WorkflowRun) -> None:
        """Assert that a workflow run succeeded."""
        if not run.is_success:
            msg = f"Workflow failed: {run.html_url} (conclusion: {run.conclusion})"
            raise AssertionError(msg)

    def assert_workflow_failure(self, run: WorkflowRun) -> None:
        """Assert that a workflow run failed."""
        if not run.is_failure:
            msg = f"Workflow should have failed: {run.html_url}"
            raise AssertionError(msg)

    def assert_comment_contains(
        self,
        pr_number: int,
        pattern: str,
        from_bot: bool = True,
    ) -> PRComment:
        """Assert that a PR comment contains a pattern."""
        if from_bot:
            comment = self.get_latest_bot_comment(pr_number)
            if not comment:
                raise AssertionError("No bot comment found")
            if pattern not in comment.body and not re.search(pattern, comment.body):
                msg = f"Pattern '{pattern}' not found in comment: {comment.body[:200]}"
                raise AssertionError(msg)
            return comment
        else:
            comments = self.get_comments(pr_number)
            for comment in reversed(comments):
                if pattern in comment.body or re.search(pattern, comment.body):
                    return comment
            msg = f"Pattern '{pattern}' not found in any comment"
            raise AssertionError(msg)

    # === Test Helpers ===

    def setup_test_pr(
        self,
        test_name: str,
        file_content: str | None = None,
    ) -> tuple[str, int, str]:
        """
        Create a test branch and PR.

        Returns: (branch_name, pr_number, head_sha)
        """
        branch_name = f"e2e-test-{test_name}-{int(time.time())}"

        # Create branch
        sha = self.create_branch(branch_name)

        # Make a commit to trigger PR
        content = file_content or f"# Test {test_name}\nmessage = \"{test_name}\"\n"
        commit_sha = self.commit_file(
            branch=branch_name,
            path="terraform/dev/test.tfvars",
            content=content,
            message=f"test: {test_name}",
        )

        # Create PR
        pr_number = self.create_pr(
            branch=branch_name,
            title=f"E2E Test: {test_name}",
            body=f"Automated E2E test for {test_name}",
        )

        # Register artifacts for automatic cleanup
        if hasattr(self, '_artifact_tracker') and self._artifact_tracker:
            self._artifact_tracker.add_branch(branch_name)
            self._artifact_tracker.add_pr(pr_number)

        return branch_name, pr_number, commit_sha

    def cleanup_test_pr(self, branch_name: str, pr_number: int) -> None:
        """Clean up test resources.
        
        Note: With automatic cleanup enabled in conftest.py, you typically
        don't need to call this manually. It's kept for backwards compatibility.
        """
        try:
            self.close_pr(pr_number)
        except Exception:
            pass
        try:
            self.delete_branch(branch_name)
        except Exception:
            pass

    def run_command_test(
        self,
        test_name: str,
        command: str,
        expect_success: bool = True,
        comment_pattern: str | None = None,
        timeout: int = 300,
    ) -> tuple[WorkflowRun, PRComment | None]:
        """
        Run a complete E2E test.

        Args:
            test_name: Name of the test
            command: Comment to post (e.g., ".plan to dev")
            expect_success: Whether workflow should succeed
            comment_pattern: Pattern to find in bot response
            timeout: Max seconds to wait

        Returns:
            (WorkflowRun, PRComment or None)
        """
        branch_name, pr_number, sha = self.setup_test_pr(test_name)

        try:
            # Record timestamp BEFORE posting comment
            from datetime import datetime, timezone
            before_comment = datetime.now(timezone.utc).isoformat()

            # Post command
            self.post_comment(pr_number, command)

            # Wait for workflow triggered after our comment
            run = self.wait_for_workflow(after_timestamp=before_comment, timeout=timeout)

            # Verify result
            if expect_success:
                self.assert_workflow_success(run)
            else:
                self.assert_workflow_failure(run)

            # Check comment if pattern provided
            comment = None
            if comment_pattern:
                comment = self.assert_comment_contains(pr_number, comment_pattern)

            return run, comment

        finally:
            self.cleanup_test_pr(branch_name, pr_number)
