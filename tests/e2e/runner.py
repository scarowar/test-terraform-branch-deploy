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
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import httpx


E2E_COMMIT_AUTHOR_NAME = os.environ.get(
    "E2E_COMMIT_AUTHOR_NAME",
    "terraform-branch-deploy-e2e",
)
E2E_COMMIT_AUTHOR_EMAIL = os.environ.get(
    "E2E_COMMIT_AUTHOR_EMAIL",
    "terraform-branch-deploy-e2e@example.invalid",
)
CANDIDATE_REF_RE = re.compile(
    r"^(v[0-9]+(\.[0-9]+){0,2}(-[0-9A-Za-z.-]+)?|[0-9a-f]{40})$"
)
CANDIDATE_REF_MARKER = "terraform-branch-deploy-ref"
BRANCH_DEPLOY_TRANSIENT_AUTH_PATTERNS = (
    "HttpError: Bad credentials - https://docs.github.com/rest",
    "validPermissions",
    "github/branch-deploy",
)


def candidate_ref_from_env() -> str:
    """Return the candidate action ref for PR body metadata."""
    candidate_ref = os.environ.get("TF_BRANCH_DEPLOY_REF", "").strip()
    if not candidate_ref:
        return ""
    if not CANDIDATE_REF_RE.fullmatch(candidate_ref):
        raise ValueError(
            "TF_BRANCH_DEPLOY_REF must be a release tag or full commit SHA."
        )
    return candidate_ref


def build_test_pr_body(test_name: str) -> str:
    """Build the E2E pull request body."""
    body = f"Automated E2E test for {test_name}"
    candidate_ref = candidate_ref_from_env()
    if candidate_ref:
        body += f"\n\n<!-- {CANDIDATE_REF_MARKER}: {candidate_ref} -->"
    return body


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
    display_title: str | None = None
    trigger_comment_id: int | None = None
    triggered_after: str | None = None
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

    def matches_comment(self, comment_id: int | None) -> bool:
        """Return whether this workflow run belongs to a posted comment."""
        if comment_id is None:
            return True
        if self.display_title is None:
            return False
        return (
            re.search(
                rf"(?:^|\s)comment\s+{re.escape(str(comment_id))}(?:\s|$)",
                self.display_title,
            )
            is not None
        )


@dataclass
class PRComment:
    """Represents a GitHub PR comment."""

    id: int
    body: str
    user: str
    created_at: str
    html_url: str


def _parse_github_timestamp(value: str) -> datetime:
    """Parse a GitHub timestamp into an aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _default_github_api_url() -> str:
    """Return the GitHub API URL for github.com or GitHub Enterprise Server."""
    if api_url := os.environ.get("GITHUB_API_URL"):
        return api_url.rstrip("/")

    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    if server_url == "https://github.com":
        return "https://api.github.com"

    return f"{server_url}/api/v3"


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
        transport: httpx.BaseTransport | None = None,
        api_url: str | None = None,
    ):
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_branch = base_branch
        self.base_url = (api_url or _default_github_api_url()).rstrip("/")

        if not self.token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN env var.")

        self._last_command_timestamp_by_pr: dict[int, str] = {}
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
            transport=transport,
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

    def lock_ref_name(self, environment: str) -> str:
        """Return the Branch Deploy lock ref name for an environment or global lock."""
        if environment == "global":
            return "global-branch-deploy-lock"
        return f"{environment}-branch-deploy-lock"

    def lock_ref_exists(self, environment: str) -> bool:
        """Return whether a Branch Deploy lock branch exists."""
        lock_ref = self.lock_ref_name(environment)
        resp = self.client.get(f"/repos/{self.repo}/git/refs/heads/{lock_ref}")
        if resp.status_code == 200:
            return True
        if resp.status_code in (404, 422):
            return False
        resp.raise_for_status()
        return False

    def delete_lock_ref_if_exists(self, environment: str) -> None:
        """Delete a Branch Deploy lock branch when preflight cleanup needs it."""
        lock_ref = self.lock_ref_name(environment)
        resp = self.client.delete(f"/repos/{self.repo}/git/refs/heads/{lock_ref}")
        if resp.status_code not in (204, 404, 422):
            resp.raise_for_status()

    def assert_lock_ref_exists(self, environment: str) -> None:
        """Assert that a Branch Deploy lock branch exists."""
        if not self.lock_ref_exists(environment):
            lock_ref = self.lock_ref_name(environment)
            raise AssertionError(f"Expected lock ref to exist: {lock_ref}")

    def assert_no_lock_ref(self, environment: str) -> None:
        """Assert that a Branch Deploy lock branch does not exist."""
        if self.lock_ref_exists(environment):
            lock_ref = self.lock_ref_name(environment)
            raise AssertionError(f"Expected lock ref to be absent: {lock_ref}")

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
            "author": {
                "name": E2E_COMMIT_AUTHOR_NAME,
                "email": E2E_COMMIT_AUTHOR_EMAIL,
            },
            "committer": {
                "name": E2E_COMMIT_AUTHOR_NAME,
                "email": E2E_COMMIT_AUTHOR_EMAIL,
            },
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
        for attempt in range(2):
            before_comment = datetime.now(timezone.utc).isoformat()

            comment_id = self.post_comment(pr_number, command)
            self._last_command_timestamp_by_pr[pr_number] = before_comment

            run = self.wait_for_workflow(
                after_timestamp=before_comment,
                timeout=timeout,
                comment_id=comment_id,
            )
            run.trigger_comment_id = comment_id
            run.triggered_after = before_comment

            if attempt == 0 and self.is_retryable_branch_deploy_auth_failure(run):
                print(
                    "Retrying command after branch-deploy permission check "
                    f"returned transient Bad credentials: {run.html_url}"
                )
                continue

            return run

        return run

    def get_comments(self, pr_number: int) -> list[PRComment]:
        """Get all comments on a PR."""
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.client.get(
                f"/repos/{self.repo}/issues/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            page_comments = resp.json()
            comments.extend(page_comments)
            if len(page_comments) < 100:
                break
            page += 1
        return [
            PRComment(
                id=c["id"],
                body=c["body"],
                user=c["user"]["login"],
                created_at=c["created_at"],
                html_url=c["html_url"],
            )
            for c in comments
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
                display_title=r.get("display_title"),
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
            display_title=r.get("display_title"),
            raw=r,
        )

    def wait_for_workflow(
        self,
        after_timestamp: str | None = None,
        timeout: int = 300,
        poll_interval: int = 10,
        comment_id: int | None = None,
    ) -> WorkflowRun:
        """
        Wait for a workflow run to complete.

        Args:
            after_timestamp: ISO timestamp - only consider runs created after this
            timeout: Maximum seconds to wait
            poll_interval: Seconds between polls
            comment_id: GitHub issue comment id that should appear in the run name

        Returns:
            The completed WorkflowRun

        Raises:
            TimeoutError: If workflow doesn't complete in time
        """
        start = time.time()

        # Use current time if no timestamp provided
        if after_timestamp is None:
            after_dt = datetime.now(timezone.utc)
        else:
            after_dt = _parse_github_timestamp(after_timestamp)

        # Track the run we're waiting for
        target_run_id: int | None = None

        while time.time() - start < timeout:
            runs = self.get_workflow_runs(per_page=20)

            for run in runs:
                # Parse the created_at timestamp
                created = datetime.fromisoformat(run.created_at.replace("Z", "+00:00"))

                # Only consider runs created after our timestamp
                if created > after_dt and run.matches_comment(comment_id):
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
        if comment_id:
            msg += f" (comment_id: {comment_id})"
        raise TimeoutError(msg)

    def get_workflow_logs(self, run_id: int) -> str:
        """Get workflow run logs as text."""
        resp = self.client.get(
            f"/repos/{self.repo}/actions/runs/{run_id}/logs",
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return ""

        try:
            with zipfile.ZipFile(BytesIO(resp.content)) as logs_zip:
                chunks = []
                for name in sorted(logs_zip.namelist()):
                    if name.endswith("/"):
                        continue
                    content = logs_zip.read(name).decode("utf-8", errors="replace")
                    chunks.append(f"===== {name} =====\n{content}")
                return "\n".join(chunks)
        except zipfile.BadZipFile:
            return resp.text

    def is_retryable_branch_deploy_auth_failure(self, run: WorkflowRun) -> bool:
        """Return whether a run hit branch-deploy's transient permission-check 401."""
        if not run.is_failure:
            return False

        logs = self.get_workflow_logs(run.id)
        return all(pattern in logs for pattern in BRANCH_DEPLOY_TRANSIENT_AUTH_PATTERNS)

    def assert_logs_contain(self, run_id: int, pattern: str) -> str:
        """Assert that workflow logs contain a string or regex pattern."""
        logs = self.get_workflow_logs(run_id)
        if pattern not in logs and not re.search(pattern, logs):
            raise AssertionError(f"Pattern '{pattern}' not found in workflow logs")
        return logs

    def assert_logs_do_not_contain(self, run_id: int, pattern: str) -> str:
        """Assert that workflow logs do not contain a string or regex pattern."""
        logs = self.get_workflow_logs(run_id)
        if pattern in logs or re.search(pattern, logs):
            raise AssertionError(
                f"Pattern '{pattern}' unexpectedly found in workflow logs"
            )
        return logs

    def assert_no_direct_apply_without_plan(self, run_id: int) -> str:
        """Assert terraform apply was not run without a saved plan file."""
        logs = self.get_workflow_logs(run_id)
        for line in logs.splitlines():
            if "terraform apply" not in line or "-auto-approve" not in line:
                continue
            if ".tfplan" not in line:
                raise AssertionError(f"Unsafe direct terraform apply found: {line}")
        return logs

    def assert_apply_used_plan(self, run_id: int, plan_filename: str) -> str:
        """Assert terraform apply used the expected saved plan."""
        logs = self.assert_logs_contain(run_id, plan_filename)
        self.assert_no_direct_apply_without_plan(run_id)
        return logs

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
        after_timestamp: str | None = None,
    ) -> PRComment:
        """Assert that a PR comment contains a pattern."""
        after_timestamp = after_timestamp or self._last_command_timestamp_by_pr.get(
            pr_number
        )
        after_dt = _parse_github_timestamp(after_timestamp) if after_timestamp else None
        comments = self.get_comments(pr_number)

        def created_after_trigger(comment: PRComment) -> bool:
            if after_dt is None:
                return True
            return _parse_github_timestamp(comment.created_at) > after_dt

        if from_bot:
            comment = next(
                (
                    c
                    for c in reversed(comments)
                    if c.user in ("github-actions[bot]", "github-actions")
                    and created_after_trigger(c)
                ),
                None,
            )
            if not comment:
                raise AssertionError("No bot comment found after command under test")
            if pattern not in comment.body and not re.search(pattern, comment.body):
                msg = f"Pattern '{pattern}' not found in comment: {comment.body[:200]}"
                raise AssertionError(msg)
            return comment
        else:
            for comment in reversed(comments):
                if created_after_trigger(comment) and (
                    pattern in comment.body or re.search(pattern, comment.body)
                ):
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
        branch_name = f"e2e-test-{test_name}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

        # Create branch
        self.create_branch(branch_name)
        if hasattr(self, "_artifact_tracker") and self._artifact_tracker:
            self._artifact_tracker.add_branch(branch_name)

        # Make a commit to trigger PR
        content = file_content or f'# Test {test_name}\nmessage = "{test_name}"\n'
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
            body=build_test_pr_body(test_name),
        )

        if hasattr(self, "_artifact_tracker") and self._artifact_tracker:
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
            run = self.wait_for_workflow(
                after_timestamp=before_comment, timeout=timeout
            )

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
