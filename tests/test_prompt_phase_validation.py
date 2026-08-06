from pathlib import Path

import build_prompts


ROOT = Path(__file__).resolve().parent.parent


def test_all_templates_embed_the_same_canonical_validator():
    for phase in (1, 2, 3, 4):
        template = (ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md").read_text(encoding="utf-8")
        assert template.count("{{PHASE_VALIDATION_SCRIPT}}") == 1
        assert f"--phase {phase}" in template
        assert "Do not search for the repository" in template


def test_builder_replaces_validation_marker_for_every_phase(monkeypatch):
    validator = (ROOT / "scripts" / "final_validation.py").read_text(encoding="utf-8").rstrip()
    for phase in (1, 2, 3, 4):
        rendered = build_prompts.render(phase)
        assert "{{PHASE_VALIDATION_SCRIPT}}" not in rendered
        assert validator in rendered
        assert f"--phase {phase}" in rendered
