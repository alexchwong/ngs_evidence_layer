from pathlib import Path

import build_prompts


ROOT = Path(__file__).resolve().parent.parent


def test_phase3_omits_validation_while_other_templates_embed_it():
    for phase in (1, 2, 4):
        template = (ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md").read_text(encoding="utf-8")
        assert template.count("{{PHASE_VALIDATION_BUNDLE}}") == 1
        assert f"--phase {phase}" in template
    phase3 = (ROOT / "prompts" / "templates" / "phase3_prompt.md").read_text(
        encoding="utf-8"
    )
    assert "{{PHASE_VALIDATION_BUNDLE}}" not in phase3
    assert "validation_bundle/scripts/final_validation.py" not in phase3


def test_builder_excludes_validator_from_phase3_only():
    validator = (ROOT / "scripts" / "final_validation.py").read_text(encoding="utf-8").rstrip()
    for phase in (1, 2, 4):
        rendered = build_prompts.render(phase)
        assert "{{PHASE_VALIDATION_BUNDLE}}" not in rendered
        assert validator in rendered
        assert f"--phase {phase}" in rendered
    assert validator not in build_prompts.render(3)


def test_phase4_entry_validates_phase3_product():
    rendered = build_prompts.render(4)
    entry = rendered.split("## Entry validation", 1)[1].split(
        "## Mandatory human adjudication", 1
    )[0]
    assert "validation_bundle/scripts/final_validation.py --phase 3" in entry
