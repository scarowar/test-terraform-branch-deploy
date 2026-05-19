"""Release harness checks for the E2E repository."""

import re
from pathlib import Path


ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "terraform-deploy.yml"
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
            assert ACTION_REF_RE.search(action_ref), f"{path}:{line_number} uses {action_ref}"


def test_e2e_dispatch_input_is_not_interpolated_into_shell() -> None:
    """Manual test filters are shell data, not script source."""
    workflow = (ROOT / ".github" / "workflows" / "e2e-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "${{ github.event.inputs.test_filter }}" in workflow
    assert 'if [ -n "${{ github.event.inputs.test_filter }}" ]' not in workflow
    assert (
        'uv run pytest tests/e2e/ -v --tb=long -k "${{ github.event.inputs.test_filter }}"'
        not in workflow
    )


def test_certification_stages_do_not_rerun_critical_args() -> None:
    """Critical arg safety tests should not be repeated in the args stage."""
    script = CERTIFICATION_SCRIPT.read_text(encoding="utf-8")

    assert '"args and not critical"' in script
