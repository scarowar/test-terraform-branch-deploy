"""Mocked tests for the E2E runner.

These tests validate the local GitHub API client behavior without creating
branches, PRs, comments, or workflow runs in GitHub.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

import httpx
import pytest

from tests.e2e.runner import E2ETestRunner


REPO_PATH = "/repos/scarowar/test-terraform-branch-deploy"


def response(request: httpx.Request, status_code: int, data: dict[str, Any]) -> httpx.Response:
    """Create a JSON response bound to the incoming request."""
    return httpx.Response(status_code=status_code, json=data, request=request)


def workflow_run(
    *,
    run_id: int = 123,
    status: str = "completed",
    conclusion: str | None = "success",
    created_at: str = "2999-01-01T00:00:00Z",
) -> dict[str, Any]:
    """Build the GitHub Actions workflow run shape used by the runner."""
    return {
        "id": run_id,
        "name": "Terraform Deploy",
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.example/runs/{run_id}",
        "logs_url": f"https://api.github.example/runs/{run_id}/logs",
        "created_at": created_at,
        "updated_at": created_at,
        "head_sha": "abc123",
    }


def zip_logs(files: dict[str, str]) -> bytes:
    """Build a GitHub Actions logs zip payload."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as logs_zip:
        for name, content in files.items():
            logs_zip.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.mocked
def test_setup_test_pr_creates_branch_commit_and_pr_requests() -> None:
    """setup_test_pr should call the expected GitHub APIs in order."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path

        if request.method == "GET" and path == f"{REPO_PATH}/git/refs/heads/main":
            return response(request, 200, {"object": {"sha": "base-sha"}})

        if request.method == "POST" and path == f"{REPO_PATH}/git/refs":
            payload = json.loads(request.content)
            assert payload["ref"].startswith("refs/heads/e2e-test-mocked-")
            assert payload["sha"] == "base-sha"
            return response(request, 201, {})

        if request.method == "GET" and path == f"{REPO_PATH}/contents/terraform/dev/test.tfvars":
            return response(request, 404, {})

        if request.method == "PUT" and path == f"{REPO_PATH}/contents/terraform/dev/test.tfvars":
            payload = json.loads(request.content)
            assert payload["message"] == "test: mocked"
            assert payload["branch"].startswith("e2e-test-mocked-")
            assert payload["author"] == {
                "name": "terraform-branch-deploy-e2e",
                "email": "terraform-branch-deploy-e2e@example.invalid",
            }
            assert payload["committer"] == payload["author"]
            return response(request, 200, {"commit": {"sha": "commit-sha"}})

        if request.method == "POST" and path == f"{REPO_PATH}/pulls":
            payload = json.loads(request.content)
            assert payload["title"] == "E2E Test: mocked"
            assert payload["base"] == "main"
            return response(request, 201, {"number": 42})

        raise AssertionError(f"Unexpected request: {request.method} {path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        branch, pr_number, commit_sha = runner.setup_test_pr("mocked")

    assert branch.startswith("e2e-test-mocked-")
    assert pr_number == 42
    assert commit_sha == "commit-sha"
    assert [request.method for request in requests] == ["GET", "POST", "GET", "PUT", "POST"]


@pytest.mark.mocked
def test_post_and_wait_posts_comment_and_returns_completed_workflow() -> None:
    """post_and_wait should post the command and return the matching completed run."""
    posted_comments: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if request.method == "POST" and path == f"{REPO_PATH}/issues/42/comments":
            payload = json.loads(request.content)
            posted_comments.append(payload["body"])
            return response(request, 201, {"id": 1001})

        if request.method == "GET" and path == f"{REPO_PATH}/actions/runs":
            return response(request, 200, {"workflow_runs": [workflow_run(run_id=77)]})

        raise AssertionError(f"Unexpected request: {request.method} {path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        run = runner.post_and_wait(42, ".plan to dev", timeout=1)

    assert posted_comments == [".plan to dev"]
    assert run.id == 77
    assert run.is_success


@pytest.mark.mocked
def test_wait_for_workflow_times_out_without_matching_run() -> None:
    """wait_for_workflow should fail when no matching run appears."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"{REPO_PATH}/actions/runs":
            return response(request, 200, {"workflow_runs": []})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        with pytest.raises(TimeoutError, match="Workflow did not complete"):
            runner.wait_for_workflow(
                after_timestamp="2999-01-01T00:00:00+00:00",
                timeout=0.01,
                poll_interval=0.01,
            )


@pytest.mark.mocked
def test_assert_no_workflow_after_ignores_older_runs() -> None:
    """No-workflow assertions should ignore runs created before the comment."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"{REPO_PATH}/actions/runs":
            return response(
                request,
                200,
                {
                    "workflow_runs": [
                        workflow_run(
                            run_id=77,
                            created_at="2026-01-01T00:00:00Z",
                        )
                    ]
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        runner.assert_no_workflow_after(
            "2026-01-01T00:01:00+00:00",
            timeout=0.01,
            poll_interval=0.01,
        )


@pytest.mark.mocked
def test_cleanup_helpers_close_pr_and_ignore_missing_branch() -> None:
    """Cleanup helpers should close PRs and tolerate already-deleted branches."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))

        if request.method == "PATCH" and request.url.path == f"{REPO_PATH}/pulls/42":
            payload = json.loads(request.content)
            assert payload == {"state": "closed"}
            return response(request, 200, {})

        if request.method == "DELETE" and request.url.path == f"{REPO_PATH}/git/refs/heads/test-branch":
            return response(request, 422, {"message": "Reference does not exist"})

        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        runner.close_pr(42)
        runner.delete_branch("test-branch")

    assert calls == [
        ("PATCH", f"{REPO_PATH}/pulls/42"),
        ("DELETE", f"{REPO_PATH}/git/refs/heads/test-branch"),
    ]


@pytest.mark.mocked
def test_assert_comment_contains_checks_latest_bot_comment() -> None:
    """Comment assertions should inspect the newest bot comment first."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"{REPO_PATH}/issues/42/comments":
            return response(
                request,
                200,
                [
                    {
                        "id": 1,
                        "body": "older Deployment Results",
                        "user": {"login": "github-actions[bot]"},
                        "created_at": "2026-01-01T00:00:00Z",
                        "html_url": "https://github.example/comment/1",
                    },
                    {
                        "id": 2,
                        "body": "latest Deployment Results",
                        "user": {"login": "github-actions[bot]"},
                        "created_at": "2026-01-01T00:01:00Z",
                        "html_url": "https://github.example/comment/2",
                    },
                ],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        comment = runner.assert_comment_contains(42, "latest Deployment Results")

    assert comment.id == 2


@pytest.mark.mocked
def test_get_workflow_logs_decodes_zip_payload() -> None:
    """Workflow logs are returned by GitHub as a zip archive."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"{REPO_PATH}/actions/runs/77/logs":
            return httpx.Response(
                200,
                content=zip_logs({"1_build.txt": "$ terraform plan\n"}),
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        logs = runner.get_workflow_logs(77)

    assert "1_build.txt" in logs
    assert "$ terraform plan" in logs


@pytest.mark.mocked
def test_assert_no_direct_apply_without_plan_rejects_unsafe_apply() -> None:
    """Direct terraform apply without a .tfplan file is unsafe."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"{REPO_PATH}/actions/runs/77/logs":
            return httpx.Response(
                200,
                content=zip_logs({"1_apply.txt": "$ terraform apply -input=false -auto-approve\n"}),
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        with pytest.raises(AssertionError, match="Unsafe direct terraform apply"):
            runner.assert_no_direct_apply_without_plan(77)


@pytest.mark.mocked
def test_assert_apply_used_plan_accepts_saved_plan_apply() -> None:
    """Applying a saved .tfplan file is the expected non-rollback path."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == f"{REPO_PATH}/actions/runs/77/logs":
            return httpx.Response(
                200,
                content=zip_logs(
                    {
                        "1_apply.txt": (
                            "$ terraform apply -input=false -auto-approve "
                            "tfplan-dev-abc12345.tfplan\n"
                        )
                    }
                ),
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    with E2ETestRunner(token="token", transport=httpx.MockTransport(handler)) as runner:
        logs = runner.assert_apply_used_plan(77, "tfplan-dev-abc12345.tfplan")

    assert "tfplan-dev-abc12345.tfplan" in logs
