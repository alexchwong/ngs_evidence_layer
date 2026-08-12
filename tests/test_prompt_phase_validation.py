from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_prompts

PHASE_MARKERS = {
    1: "PHASE1_VALIDATION_BUNDLE",
    2: "PHASE2_VALIDATION_BUNDLE",
    4: "PHASE4_VALIDATION_BUNDLE",
    5: "PHASE5_VALIDATION_BUNDLE",
}


def test_only_phases_with_validators_embed_phase_specific_markers():
    for phase, marker in PHASE_MARKERS.items():
        template = (
            ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
        ).read_text(encoding="utf-8")
        assert template.count("{{" + marker + "}}") == 1
    for path in (
        ROOT / "prompts" / "templates" / "phase3_prompt.md",
        ROOT / "prompts" / "templates" / "phase5_review_prompt.md",
    ):
        template = path.read_text(encoding="utf-8")
        assert "_VALIDATION_BUNDLE}}" not in template


def test_builder_embeds_only_the_active_phase_validator():
    for phase in PHASE_MARKERS:
        rendered = build_prompts.render(phase)
        expected_source = (
            ROOT / "scripts" / "phase_validation" / f"phase{phase}.py"
        ).read_text(encoding="utf-8").rstrip()
        assert expected_source in rendered
        for other in PHASE_MARKERS:
            if other != phase:
                other_source = (
                    ROOT / "scripts" / "phase_validation" / f"phase{other}.py"
                ).read_text(encoding="utf-8").rstrip()
                assert other_source not in rendered
    assert "<!-- BEGIN VERBATIM scripts/phase_validation/" not in build_prompts.render(3)
    assert (
        "<!-- BEGIN VERBATIM scripts/phase_validation/"
        not in build_prompts.render_phase5_review()
    )


def test_phase4_entry_validates_phase3_product_with_phase4_validator():
    rendered = build_prompts.render(4)
    entry = rendered.split("## Entry validation", 1)[1].split(
        "## Mandatory human adjudication", 1
    )[0]
    assert (
        "validation_bundle/scripts/phase_validation/phase4.py --review-only" in entry
    )
