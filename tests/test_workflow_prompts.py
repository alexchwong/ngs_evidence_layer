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
    "reporting_rule_policy.md",
    "citation_rules.md",
    "format_report.md",
    "mark_validation_report.md",
    "analyse_diagnosis_prototype.md",
    "analyse_remainder_prototype.md",
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
    assert "prompts/workflow/prototype/*" in manifest
    assert "prompts/diagnostic_adjudication_prompt.md" not in manifest
    assert "validation/marking_prompt.md" not in manifest


def test_format_integrity_rules_are_shared_not_default_style_only():
    workflow = (WORKFLOW_DIR / "format_report.md").read_text(encoding="utf-8")
    citations = (WORKFLOW_DIR / "citation_rules.md").read_text(encoding="utf-8")
    default = (ROOT / "prompts" / "formatting" / "default.md").read_text(encoding="utf-8")

    for required in (
        "sole source of report content",
        "Do not write numeric citations",
        "OMIT:",
    ):
        assert required in workflow

    for required in (
        "## Rule-draft citation contract",
        "Cite **every evidence card directly supporting the answer**",
        "preserve card-level granularity",
        "union of all directly supporting runtime card markers",
        "## Final-report sentence citation contract",
        "Every sentence-ending full stop",
        "union of every runtime card marker",
        "When one source sentence is split",
        "do not count toward formatting-prompt word limits",
    ):
        assert required in citations

    assert "## Handling negative statements" not in default
    assert "The first sentence MUST summarise the detected NGS variants." in default
    assert "Formatting, compression, and word-count instructions MUST NOT remove" in default
    assert "## Referencing" not in default
    assert "## Source and output constraints" not in default


def test_analyse_report_uses_shared_reporting_rule_policy():
    analyse = (WORKFLOW_DIR / "analyse_report.md").read_text(encoding="utf-8")
    policy = (WORKFLOW_DIR / "reporting_rule_policy.md").read_text(encoding="utf-8")
    assert "Follow `prompts/workflow/reporting_rule_policy.md` exactly" in analyse
    assert "exactly one classification token: `REPORT:` or `OMIT:`" in analyse
    assert "Every rule MUST be classified" in analyse
    assert "if the answer's clinical conclusion would begin `No ...` or `Not applicable ...`" in policy
    assert "if a rule is conditional and its premise is not met" in policy
    assert "R0.1` is the explicit exception" in policy
    assert "Do not use `OMIT:` merely because a conclusion is negative in wording" in policy
    assert "Only text after `REPORT:` is eligible source prose" in (WORKFLOW_DIR / "format_report.md").read_text(encoding="utf-8")


def test_skill_refreshes_shared_citation_rules_at_required_steps():
    skill = SKILL.read_text(encoding="utf-8")
    assert "re-read `prompts/workflow/citation_rules.md` before repairing the citation defect" in skill
    assert skill.count("`prompts/workflow/citation_rules.md`;") >= 2
    assert "Step 6B citation invariant" in skill


def test_release_manifest_includes_validation_packagers():
    manifest = RELEASE_MANIFEST.read_text(encoding="utf-8").splitlines()
    assert "validation/package_marking.py" in manifest
    assert "validation/case_functional.md" in manifest
    assert "validation/case_functional_manifest.md" in manifest
    assert "scripts/package_run.py" in manifest
    assert "scripts/prototype_workflow.py" in manifest
    assert "0.2.2_prototype_skill.md" in manifest


def test_prototype_skill_uses_merged_setup_and_render_validation():
    prototype = (ROOT / "0.2.2_prototype_skill.md").read_text(encoding="utf-8")
    assert "prototype_workflow.py setup --mode ngs-report" in prototype
    assert "prototype_workflow.py setup --mode nel-demo --example <N>" in prototype
    assert "prototype_workflow.py setup --mode nel-validate --case-id <case-id>" in prototype
    assert "prototype_workflow.py setup --mode nel-validate-function --case-id <case-id>" in prototype
    assert "python scripts/case_major_categories.py" not in prototype
    assert "python validation/retrieve_cli.py case" not in prototype
    assert "prototype_workflow.py rules" not in prototype
    assert "python scripts/report_citations.py validate" not in prototype
    assert "Step 6C `render` performs the same strict validation before any write" in prototype
    assert "prototype_workflow.py remainder-rules" in prototype


def test_prototype_skill_is_parallel_and_keeps_cmc_fixed_after_step3():
    prototype = (ROOT / "0.2.2_prototype_skill.md").read_text(encoding="utf-8")
    remainder = (WORKFLOW_DIR / "analyse_remainder_prototype.md").read_text(encoding="utf-8")
    assert "Do not modify or substitute `SKILL.md`" in prototype
    assert "`nel-validate-function <case-id>`" in prototype
    assert "--case-file validation/case_functional.md" in prototype
    assert "prototype-diagnosis" in prototype
    assert "prototype-downstream" in prototype
    assert "CMC2 is fixed" in prototype
    assert "Do not change, re-route, propose, or emit another CMC" in remainder




def test_prototype_analysis_prompts_delegate_semantics_to_generated_rule_contracts():
    diagnosis = (WORKFLOW_DIR / "analyse_diagnosis_prototype.md").read_text(encoding="utf-8")
    remainder = (WORKFLOW_DIR / "analyse_remainder_prototype.md").read_text(encoding="utf-8")
    for prompt in (diagnosis, remainder):
        assert "prompt-owned analysis contract" in prompt
        assert "REPORT/OMIT taxonomy" in prompt
        assert "Rule-draft citation contract" in prompt
        assert "State the patient-level conclusion first" not in prompt
    assert "Do not change, re-route, propose, or emit another CMC" in remainder

def test_model_steps_are_not_described_as_deterministic_model_hybrids():
    skill = SKILL.read_text(encoding="utf-8")
    assert "deterministic/model" not in skill
    assert "Step 1B — model with deterministic setup" in skill


def test_skill_forbids_script_inspection_for_model_tasks():
    skill = SKILL.read_text(encoding="utf-8")
    for required in (
        "Treat declared deterministic commands as opaque operations",
        "do not open, read, search, grep, or otherwise inspect their Python source",
        "Do not search for or substitute another script or command to perform a model task",
        "The model, not a Python script, must author `<work-dir>/case-input.json`",
    ):
        assert required in skill
