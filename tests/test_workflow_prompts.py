from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
WORKFLOW_DIR = ROOT / "prompts" / "workflow"
RELEASE_MANIFEST = ROOT / "release" / "skill.txt"


REQUIRED_WORKFLOW_PROMPTS = {
    "capture_case.md",
    "structure_case.md",
    "adjudicate_diagnosis.md",
    "revise_diagnosis.md",
    "analyse_report.md",
    "format_report.md",
    "mark_validation_report.md",
}


def test_required_workflow_prompts_exist():
    assert REQUIRED_WORKFLOW_PROMPTS <= {path.name for path in WORKFLOW_DIR.glob("*.md")}


def test_every_workflow_prompt_referenced_by_skill_exists():
    skill = SKILL.read_text(encoding="utf-8")
    references = set(re.findall(r"prompts/workflow/[A-Za-z0-9_.-]+\.md", skill))
    assert references
    for reference in references:
        assert (ROOT / reference).is_file(), reference


def test_skill_no_longer_references_obsolete_prompt_paths():
    skill = SKILL.read_text(encoding="utf-8")
    assert "prompts/diagnostic_adjudication_prompt.md" not in skill
    assert "validation/marking_prompt.md" not in skill


def test_repository_no_longer_contains_obsolete_prompt_files():
    assert not (ROOT / "prompts" / "diagnostic_adjudication_prompt.md").exists()
    assert not (ROOT / "validation" / "marking_prompt.md").exists()


def test_release_manifest_includes_all_workflow_prompts():
    manifest = RELEASE_MANIFEST.read_text(encoding="utf-8").splitlines()
    assert "prompts/workflow/*" in manifest
    assert "prompts/diagnostic_adjudication_prompt.md" not in manifest
    assert "validation/marking_prompt.md" not in manifest


def test_format_integrity_rules_are_global_not_default_style_only():
    workflow = (WORKFLOW_DIR / "format_report.md").read_text(encoding="utf-8")
    default = (ROOT / "prompts" / "formatting" / "default.md").read_text(encoding="utf-8")

    for required in (
        "sole source of report content",
        "[card:<six-character-tag>]",
        "Do not create, infer, alter, shorten, parse, replace, or renumber",
        "Do not write numeric citations",
    ):
        assert required in workflow

    assert "## Referencing" not in default
    assert "## Source and output constraints" not in default
