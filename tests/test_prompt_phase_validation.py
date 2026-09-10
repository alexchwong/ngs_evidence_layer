from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_prompts

PHASE_MARKERS = {
    1: "PHASE1_VALIDATION_BUNDLE",
    2: "PHASE2_VALIDATION_BUNDLE",
    4: "PHASE4_VALIDATION_BUNDLE",
}

def test_only_phases_with_validators_embed_phase_specific_markers():
    for phase, marker in PHASE_MARKERS.items():
        template = (
            ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
        ).read_text(encoding="utf-8")
        assert template.count("{{" + marker + "}}") == 1
    for path in (ROOT / "prompts" / "templates" / "phase3_prompt.md",):
        template = path.read_text(encoding="utf-8")
        assert "_VALIDATION_BUNDLE}}" not in template

def test_phase4_entry_validates_phase3_product_with_phase4_validator():
    rendered = build_prompts.render(4)
    entry = rendered.split("## Step 1 — deterministic input gate", 1)[1].split(
        "## Shared semantic principles", 1
    )[0]
    assert (
        "validation_bundle/scripts/phase_validation/phase4.py --review-only" in entry
    )


def test_phase2_output_boundary_validates_evidence_against_paper():
    rendered = build_prompts.render(2)
    assert "--source paper.md" in rendered
    assert "final action" in rendered.lower()
    assert "successful" in rendered.lower()


def test_phase4_failed_card_evidence_repairs_stay_in_phase4():
    rendered = build_prompts.render(4)
    assert (
        "The fact that the defective evidence originated in Phase 2 does not make the repair Phase 2R work"
        in rendered
    )
    assert (
        "A Phase 2R request must never target a card the active Phase 3 review marked `fail`"
        in rendered
    )
    assert (
        "Do not encode a failed-card evidence repair as a `phase2r_request`" in rendered
    )


def test_phase4_owns_source_failures_for_phase4_authored_evidence():
    rendered = build_prompts.render(4)
    assert "--source paper.md" in rendered
    assert "Phase 4 output-boundary defect" in rendered
    assert "Do not send the failed card to Phase 2R or Phase 3" in rendered


def test_phase4_allows_evidence_only_verbatim_repair_on_passed_cards():
    rendered = build_prompts.render(4)
    assert "Direct Phase 4 **semantic card adjudication** is limited" in rendered
    assert "evidence-only source-fidelity repair" in rendered
    assert "regardless of whether Phase 3 marked the card `pass` or `fail`" in rendered
    assert "except for the evidence-only verbatim repair exception above" in rendered
    assert "preserve the card fields and interpretation unchanged" in rendered
    assert "does not require Phase 2R or another Phase 3 cycle" in rendered
    assert "Direct Phase 4 card adjudication is limited to cards the active Phase 3 review marked `fail`." not in rendered
