from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
ROOT_SKILL = ROOT / "SKILL.md"
REGISTRY = ROOT / "workflows" / "registry.json"
LEGACY_SKILL = ROOT / "workflows" / "legacy_v1" / "SKILL.md"
CURRENT_SKILL = ROOT / "workflows" / "diagnosis_first_v1" / "SKILL.md"
SHARED_PROMPT_DIR = ROOT / "prompts" / "workflow"
LEGACY_PROMPT_DIR = ROOT / "workflows" / "legacy_v1" / "prompts"
CURRENT_PROMPT_DIR = ROOT / "workflows" / "diagnosis_first_v1" / "prompts"
CURRENT_RULE_DIR = CURRENT_PROMPT_DIR / "rule_views"
RELEASE_MANIFEST = ROOT / "release" / "skill.txt"

SHARED_PROMPTS = {
    "capture_case.md",
    "structure_case.md",
    "reporting_rule_policy.md",
    "citation_rules.md",
    "format_report.md",
    "mark_validation_report.md",
    "modify_blacklist.md",
}
LEGACY_PROMPTS = {"adjudicate_diagnosis.md", "revise_diagnosis.md", "analyse_report.md"}
CURRENT_PROMPTS = {"analyse_diagnosis.md", "analyse_remainder.md"}
CURRENT_RULE_PROMPTS = {"diagnosis_rule_view.md", "remainder_rule_view.md", "full_rule_view.md"}


def test_root_skill_routes_default_and_legacy_through_registry():
    skill = ROOT_SKILL.read_text(encoding="utf-8")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["default_workflow"] == "diagnosis-first-v1"
    assert registry["aliases"]["legacy"] == "legacy-v1"
    assert "workflows/registry.json" in skill
    assert "--legacy" in skill
    assert "--legacy-v1" in skill
    assert "diagnosis-first-v1" in skill



def test_workflow_metadata_marks_accepted_and_legacy_status():
    current = json.loads((ROOT / "workflows" / "diagnosis_first_v1" / "workflow.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "workflows" / "legacy_v1" / "workflow.json").read_text(encoding="utf-8"))
    assert current["status"] == "accepted"
    assert legacy["status"] == "legacy"
    assert (ROOT / "scripts" / "devel_workflow.py").is_file()

def test_workflow_owned_and_shared_prompts_are_separated():
    assert SHARED_PROMPTS <= {path.name for path in SHARED_PROMPT_DIR.glob("*.md")}
    assert LEGACY_PROMPTS <= {path.name for path in LEGACY_PROMPT_DIR.glob("*.md")}
    assert CURRENT_PROMPTS <= {path.name for path in CURRENT_PROMPT_DIR.glob("*.md")}
    assert CURRENT_RULE_PROMPTS <= {path.name for path in CURRENT_RULE_DIR.glob("*.md")}
    for name in LEGACY_PROMPTS | CURRENT_PROMPTS:
        assert not (SHARED_PROMPT_DIR / name).exists()


def test_every_prompt_referenced_by_authoritative_workflow_specs_exists():
    pattern = re.compile(
        r"(?:prompts/workflow|workflows/(?:legacy_v1|diagnosis_first_v1)/prompts(?:/rule_views)?)/[A-Za-z0-9_.-]+\.md"
    )
    for skill_path in (LEGACY_SKILL, CURRENT_SKILL):
        references = set(pattern.findall(skill_path.read_text(encoding="utf-8")))
        assert references
        for reference in references:
            assert (ROOT / reference).is_file(), reference


def test_shared_reporting_contract_is_single_source():
    analyse = (LEGACY_PROMPT_DIR / "analyse_report.md").read_text(encoding="utf-8")
    policy = (SHARED_PROMPT_DIR / "reporting_rule_policy.md").read_text(encoding="utf-8")
    citations = (SHARED_PROMPT_DIR / "citation_rules.md").read_text(encoding="utf-8")
    formatting = (SHARED_PROMPT_DIR / "format_report.md").read_text(encoding="utf-8")
    assert "Follow `prompts/workflow/reporting_rule_policy.md` exactly" in analyse
    assert "exactly one classification token: `REPORT:` or `OMIT:`" in analyse
    assert "if the answer's clinical conclusion would begin `No ...` or `Not applicable ...`" in policy
    assert "## Rule-draft citation contract" in citations
    assert "Every sentence-ending full stop" in citations
    assert "sole source of report content" in formatting


def test_current_skill_uses_state_driven_shared_clis():
    skill = CURRENT_SKILL.read_text(encoding="utf-8")
    assert "setup_workflow.py --workflow diagnosis-first-v1" in skill
    assert "run_case.py diagnosis --work-dir <work-dir>" in skill
    assert "run_case.py downstream --work-dir <work-dir>" in skill
    assert "workflow_runtime.py cmc --work-dir <work-dir>" in skill
    assert "workflow_runtime.py remainder-rules --work-dir <work-dir>" in skill
    assert "workflow_runtime.py assemble --work-dir <work-dir>" in skill
    assert "prototype" not in skill.lower()


def test_legacy_skill_uses_same_state_driven_case_clis():
    skill = LEGACY_SKILL.read_text(encoding="utf-8")
    assert "setup_workflow.py --workflow legacy-v1" in skill
    assert "run_case.py diagnosis --work-dir <work-dir>" in skill
    assert "run_case.py downstream --work-dir <work-dir>" in skill
    assert "case_major_categories.py" not in skill
    assert "create_work_dir.py" not in skill
    assert "resolve_demo.py" not in skill


def test_release_manifest_contains_new_runtime_and_no_phase1_shims():
    manifest = RELEASE_MANIFEST.read_text(encoding="utf-8").splitlines()
    for required in (
        "workflows/registry.json",
        "workflows/common.py",
        "workflows/legacy_v1/*",
        "workflows/diagnosis_first_v1/*",
        "scripts/setup_workflow.py",
        "scripts/workflow_registry.py",
        "scripts/workflow_runtime.py",
        "scripts/retrieval_core.py",
    ):
        assert required in manifest
    assert "0.2.2_prototype_skill.md" not in manifest
    assert "scripts/prototype_workflow.py" not in manifest
    assert "scripts/create_work_dir.py" not in manifest
    assert "scripts/case_major_categories.py" not in manifest
    assert "scripts/resolve_demo.py" not in manifest


def test_obsolete_phase1_files_are_removed():
    for path in (
        ROOT / "0.2.2_prototype_skill.md",
        ROOT / "scripts" / "prototype_workflow.py",
        ROOT / "scripts" / "create_work_dir.py",
        ROOT / "scripts" / "case_major_categories.py",
        ROOT / "scripts" / "resolve_demo.py",
        ROOT / "workflows" / "prototype",
        ROOT / "workflows" / "legacy",
    ):
        assert not path.exists(), path


def test_structure_case_uses_active_workflow_semantics_without_hardcoded_old_paths():
    text = (SHARED_PROMPT_DIR / "structure_case.md").read_text(encoding="utf-8")
    assert "active workflow specification selected by root `SKILL.md`" in text
    assert "workflows/prototype" not in text
    assert "workflows/legacy/" not in text
