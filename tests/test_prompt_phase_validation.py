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


def test_validation_bundles_match_workflow_boundaries():
    phase1 = build_prompts.render(1)
    phase2 = build_prompts.render(2)
    phase3 = build_prompts.render(3)
    phase4 = build_prompts.render(4)
    validator1 = (ROOT / "scripts" / "phase_validation" / "phase1.py").read_text(encoding="utf-8").rstrip()
    validator2 = (ROOT / "scripts" / "phase_validation" / "phase2.py").read_text(encoding="utf-8").rstrip()
    validator2_state = (ROOT / "scripts" / "phase_validation" / "phase2_state.py").read_text(encoding="utf-8").rstrip()
    validator4 = (ROOT / "scripts" / "phase_validation" / "phase4.py").read_text(encoding="utf-8").rstrip()

    assert validator1 in phase1
    assert validator2 not in phase1
    assert validator4 not in phase1

    # Normal Phase 2 reuses the exact Phase 1 deterministic census gate on input,
    # then uses its own validator on output.
    assert validator1 in phase2
    assert validator2 in phase2
    assert validator2_state in phase2
    assert validator4 not in phase2

    assert "<!-- BEGIN VERBATIM scripts/phase_validation/" not in phase3

    assert validator4 in phase4
    assert validator1 not in phase4
    assert validator2 not in phase4


def test_phase4_entry_validates_phase3_product_with_phase4_validator():
    rendered = build_prompts.render(4)
    entry = rendered.split("## Step 1 — deterministic input gate", 1)[1].split(
        "## Shared semantic principles", 1
    )[0]
    assert (
        "validation_bundle/scripts/phase_validation/phase4.py --review-only" in entry
    )
