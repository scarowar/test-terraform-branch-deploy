"""Release harness checks for the E2E repository."""

from pathlib import Path


ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "terraform-deploy.yml"
CANDIDATE_REF = ROOT / ".github" / "terraform-branch-deploy-ref"


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


def test_workflow_rejects_main_as_candidate_ref() -> None:
    """The workflow should fail before deploying when configured with main."""
    workflow = WORKFLOW.read_text()

    assert '[ "$ref" = "main" ]' in workflow
    assert "release tag or commit SHA" in workflow
