"""Release harness checks for the E2E repository."""

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "terraform-deploy.yml"
E2E_WORKFLOW = ROOT / ".github" / "workflows" / "e2e-tests.yml"
WORKFLOW_FILES = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
CANDIDATE_REF = ROOT / ".github" / "terraform-branch-deploy-ref"
CERTIFICATION_SCRIPT = ROOT / "scripts" / "run-certification.py"
ACTION_REF_RE = re.compile(r"@[0-9a-f]{40}$")


def test_candidate_ref_is_pinned() -> None:
    """The E2E harness must not certify a floating branch."""
    ref = CANDIDATE_REF.read_text().strip()

    assert ref
    assert ref not in {"main", "master"}


def test_workflow_uses_checked_out_candidate_action() -> None:
    """The deploy workflow should use the checked-out candidate action."""
    workflow = WORKFLOW.read_text()

    assert "repository: scarowar/terraform-branch-deploy" in workflow
    assert "ref: ${{ steps.tfbd-ref.outputs.ref }}" in workflow
    assert "uses: ./.terraform-branch-deploy-action" in workflow
    assert "uses: scarowar/terraform-branch-deploy@" not in workflow


def test_deploy_workflow_run_name_includes_comment_id() -> None:
    """Live tests must wait for the workflow run triggered by their own comment."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "run-name:" in workflow
    assert "${{ github.event.issue.number }}" in workflow
    assert "${{ github.event.comment.id }}" in workflow


def test_workflow_rejects_main_as_candidate_ref() -> None:
    """The workflow should fail before deploying when configured with main."""
    workflow = WORKFLOW.read_text()

    assert '[ "$ref" = "main" ]' in workflow
    assert '[ "$ref" = "master" ]' in workflow
    assert "release tag or commit SHA" in workflow


def test_workflows_do_not_use_pull_request_target() -> None:
    """E2E workflows must not run privileged pull_request_target automation."""
    for path in WORKFLOW_FILES:
        assert "pull_request_target" not in path.read_text(encoding="utf-8"), path


def test_runtime_actions_are_pinned_to_full_commit_sha() -> None:
    """The E2E repo should not rely on mutable action tags during release validation."""
    for path in WORKFLOW_FILES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped.startswith("uses: "):
                continue
            action_ref = stripped.removeprefix("uses: ").split("#", 1)[0].strip()
            if action_ref.startswith("./"):
                continue
            assert ACTION_REF_RE.search(action_ref), (
                f"{path}:{line_number} uses {action_ref}"
            )


def test_e2e_workflow_accepts_pinned_candidate_dispatch() -> None:
    """Manual E2E dispatch should validate and run an exact action ref."""
    workflow = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "candidate_ref:" in workflow
    assert "source_pr:" in workflow
    assert "stage:" in workflow
    assert "main|master" in workflow
    assert "TF_BRANCH_DEPLOY_REF" in workflow
    assert "terraform-branch-deploy/e2e" in workflow


def test_e2e_workflow_does_not_mutate_candidate_repo_variable() -> None:
    """Candidate refs should be carried by test PR metadata, not global repo state."""
    workflow = E2E_WORKFLOW.read_text(encoding="utf-8")

    assert "gh variable set TF_BRANCH_DEPLOY_REF" not in workflow
    assert "gh variable delete TF_BRANCH_DEPLOY_REF" not in workflow
    assert 'TF_BRANCH_DEPLOY_REF: ${{ env.CANDIDATE_REF }}' in workflow


def test_deploy_workflow_resolves_candidate_from_pr_body() -> None:
    """The deploy workflow should prefer the candidate marker on the test PR."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "terraform-branch-deploy-ref:" in workflow
    assert "GITHUB_EVENT_PATH" in workflow
    assert "event.get(\"issue\", {}).get(\"body\")" in workflow
    assert "gh api \"repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}\"" not in workflow
    assert "vars.TF_BRANCH_DEPLOY_REF" in workflow
    assert ".github/terraform-branch-deploy-ref" in workflow


def test_deploy_workflow_uses_runtime_github_token() -> None:
    """Internal issue-comment deploy runs should use the runtime GitHub token."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "secrets.GITHUB_TOKEN" not in workflow
    assert "${{ github.token }}" in workflow
    assert "issues: write" in workflow
    assert "pull-requests: write" in workflow


def test_external_workflows_start_with_harden_runner() -> None:
    """Runtime workflows should start with Step Security monitoring."""
    for path in WORKFLOW_FILES:
        workflow = path.read_text(encoding="utf-8")
        if "actions/checkout@" not in workflow:
            continue
        assert "step-security/harden-runner@" in workflow
        assert workflow.index("step-security/harden-runner@") < workflow.index(
            "actions/checkout@"
        )


def test_checkout_steps_do_not_persist_credentials() -> None:
    """The E2E workflows should not leave checkout credentials in git config."""
    for path in WORKFLOW_FILES:
        workflow = path.read_text(encoding="utf-8")
        checkout_count = workflow.count("actions/checkout@")
        if checkout_count == 0:
            continue
        assert workflow.count("persist-credentials: false") >= checkout_count


def test_e2e_dispatch_inputs_are_not_shell_source() -> None:
    """Manual inputs should enter shell scripts through environment variables."""
    workflow = E2E_WORKFLOW.read_text(encoding="utf-8")
    run_lines: list[str] = []
    in_run = False
    run_indent = 0

    for line in workflow.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("run:"):
            in_run = True
            run_indent = indent
            run_lines.append(line)
            continue
        if (
            in_run
            and stripped
            and indent <= run_indent
            and not stripped.startswith(("|", ">"))
        ):
            in_run = False
        if in_run:
            run_lines.append(line)

    assert "${{ github.event.inputs" not in "\n".join(run_lines)


def test_stage_selection_requires_live_mode() -> None:
    """A stage-specific run must be an explicit live E2E run."""
    result = subprocess.run(
        [sys.executable, str(CERTIFICATION_SCRIPT), "--stage", "critical"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "--stage requires --live." in result.stderr


def test_certification_stages_do_not_rerun_critical_args() -> None:
    """Critical arg safety tests should not be repeated in the args stage."""
    script = CERTIFICATION_SCRIPT.read_text(encoding="utf-8")

    assert '"args and not critical"' in script
