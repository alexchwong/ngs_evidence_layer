from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
ROOT_SKILL = ROOT / "SKILL.md"
REGISTRY = ROOT / "workflows" / "registry.json"
LEGACY_SKILL = ROOT / "workflows" / "legacy_v1" / "SKILL.md"
CURRENT_SKILL = ROOT / "workflows" / "diagnosis_first_v1" / "SKILL.md"
CATEGORICAL_SKILL = ROOT / "workflows" / "categorical_v1" / "SKILL.md"
SHARED_PROMPT_DIR = ROOT / "prompts" / "workflow"
LEGACY_PROMPT_DIR = ROOT / "workflows" / "legacy_v1" / "prompts"
CURRENT_PROMPT_DIR = ROOT / "workflows" / "diagnosis_first_v1" / "prompts"
CATEGORICAL_PROMPT_DIR = ROOT / "workflows" / "categorical_v1" / "prompts"
CURRENT_RULE_DIR = CURRENT_PROMPT_DIR / "rule_views"
RELEASE_MANIFEST = ROOT / "release" / "skill.txt"

SHARED_PROMPTS = {"capture_case.md", "structure_case.md"}
LEGACY_PROMPTS = {
    "adjudicate_diagnosis.md",
    "revise_diagnosis.md",
    "analyse_report.md",
    "reporting_rule_policy.md",
    "citation_rules.md",
    "format_report.md",
}
CURRENT_PROMPTS = {
    "analyse_diagnosis.md",
    "analyse_remainder.md",
    "agreed_reporting_rules.md",
    "reporting_rule_policy.md",
    "citation_rules.md",
    "format_report.md",
}
CURRENT_RULE_PROMPTS = {"diagnosis_context.md", "diagnosis_rule_view.md", "remainder_rule_view.md", "full_rule_view.md"}


def test_root_skill_exposes_only_terraced_v6_product_facade():
    skill = ROOT_SKILL.read_text(encoding="utf-8")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["default_workflow"] == "terraced-v6"
    assert "python nel.py setup" in skill
    assert "python nel.py run" in skill
    assert "python nel.py runs" in skill
    assert "terraced-v6" in skill
    assert "--legacy" not in skill
    assert "--diagnosis-first" not in skill
    assert "->project" in skill  # explicitly prohibited, not exposed as a supported path
    assert "workflow-internal CLIs" in skill
    assert "python3 -m venv .env" not in skill
    assert ".env/bin/python -m pip install -r requirements.txt" not in skill



def test_workflow_metadata_marks_accepted_and_legacy_status():
    categorical = json.loads((ROOT / "workflows" / "categorical_v1" / "workflow.json").read_text(encoding="utf-8"))
    current = json.loads((ROOT / "workflows" / "diagnosis_first_v1" / "workflow.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "workflows" / "legacy_v1" / "workflow.json").read_text(encoding="utf-8"))
    assert categorical["status"] == "accepted"
    assert current["status"] == "accepted"
    assert legacy["status"] == "legacy"
    assert (ROOT / "scripts" / "devel_workflow.py").is_file()

def test_workflow_owned_and_shared_prompts_are_separated():
    assert {path.name for path in SHARED_PROMPT_DIR.glob("*.md")} == SHARED_PROMPTS
    assert LEGACY_PROMPTS <= {path.name for path in LEGACY_PROMPT_DIR.glob("*.md")}
    assert CURRENT_PROMPTS <= {path.name for path in CURRENT_PROMPT_DIR.glob("*.md")}
    assert CURRENT_RULE_PROMPTS <= {path.name for path in CURRENT_RULE_DIR.glob("*.md")}
    assert (ROOT / "validation" / "mark_validation_report.md").is_file()
    assert (ROOT / "output" / "corpus" / "prompts" / "modify_blacklist.md").is_file()
    for name in {"reporting_rule_policy.md", "citation_rules.md", "format_report.md", "mark_validation_report.md", "modify_blacklist.md"}:
        assert not (SHARED_PROMPT_DIR / name).exists()


def test_every_prompt_referenced_by_authoritative_workflow_specs_exists():
    pattern = re.compile(
        r"(?:prompts/workflow|validation|workflows/(?:legacy_v1|diagnosis_first_v1|categorical_v1)/prompts(?:/(?:rule_views|formatting))?)/[A-Za-z0-9_.-]+\.md"
    )
    for skill_path in (LEGACY_SKILL, CURRENT_SKILL, CATEGORICAL_SKILL):
        references = set(pattern.findall(skill_path.read_text(encoding="utf-8")))
        assert references
        for reference in references:
            assert (ROOT / reference).is_file(), reference


def test_each_workflow_owns_its_reporting_contract():
    legacy_analyse = (LEGACY_PROMPT_DIR / "analyse_report.md").read_text(encoding="utf-8")
    legacy_policy = (LEGACY_PROMPT_DIR / "reporting_rule_policy.md").read_text(encoding="utf-8")
    legacy_citations = (LEGACY_PROMPT_DIR / "citation_rules.md").read_text(encoding="utf-8")
    legacy_formatting = (LEGACY_PROMPT_DIR / "format_report.md").read_text(encoding="utf-8")
    current_policy = (CURRENT_PROMPT_DIR / "reporting_rule_policy.md").read_text(encoding="utf-8")
    current_rules = (CURRENT_PROMPT_DIR / "agreed_reporting_rules.md").read_text(encoding="utf-8")

    assert "Follow `workflows/legacy_v1/prompts/reporting_rule_policy.md` exactly" in legacy_analyse
    assert "workflows/legacy_v1/prompts/citation_rules.md" in legacy_analyse
    assert "exactly one classification token: `REPORT:` or `OMIT:`" in legacy_analyse
    assert "if the answer's clinical conclusion would begin `No ...` or `Not applicable ...`" in legacy_policy
    assert "## Rule-draft citation contract" in legacy_citations
    assert "Every sentence-ending full stop" in legacy_citations
    assert "sole source of report content" in legacy_formatting
    assert "Routine negative findings may be used internally" in current_policy
    assert "exceptional patient-level result that should independently appear" in current_policy
    assert "Rephrasing a routine negative as a clinical effect does not make it reportable" in current_policy
    assert "Treat every disease, treatment, treatment-line, genotype, co-mutation" in current_policy
    assert "multiparameter prognostic score cannot be calculated" in current_policy
    assert "Does a panel-negative result produce an exceptional patient-level prognostic conclusion" in current_rules
    assert "Apply this rule only when a TP53 mutation has been detected" in current_rules
    assert "Assign the complete risk category only when the required inputs are available" in current_rules
    assert "Which panel-negative genes are relevant" not in current_rules

    legacy_rules = (ROOT / "rules" / "agreed_reporting_rules.md").read_text(encoding="utf-8")
    assert "Routine negative findings may be used internally" not in legacy_policy
    assert "Which panel-negative genes are relevant to the selected prognostic framework?" in legacy_rules
    assert "If limited required information is missing, give a conditional category" in legacy_rules


def test_current_skill_uses_state_driven_shared_clis():
    skill = CURRENT_SKILL.read_text(encoding="utf-8")
    assert "setup_workflow.py --workflow diagnosis-first-v1" in skill
    assert "run_case.py diagnosis --work-dir <work-dir>" in skill
    assert "run_case.py downstream --work-dir <work-dir>" in skill
    assert "workflow_runtime.py cmc --work-dir <work-dir>" in skill
    assert "workflow_runtime.py remainder-rules --work-dir <work-dir>" in skill
    assert "workflow_runtime.py assemble --work-dir <work-dir>" in skill
    assert "workflow_runtime.py validate-remainder --work-dir <work-dir>" in skill
    assert "workflow_runtime.py render --work-dir <work-dir>" in skill
    assert "report-draft-dx.yaml" in skill
    assert "report-summary.yaml" in skill
    assert "At Step 0 only" in skill
    assert "python3 -m venv .env" in skill
    assert ".env/bin/python -m pip install -r requirements.txt" in skill
    assert "PyYAML>=6.0" in skill
    assert "prototype" not in skill.lower()



def test_categorical_skill_uses_isolated_summary_steps_and_limits():
    skill = CATEGORICAL_SKILL.read_text(encoding="utf-8")
    assert "setup_workflow.py --workflow categorical-v1" in skill
    assert "prepare-dx-summary --work-dir <work-dir>" in skill
    assert "validate-dx-summary --work-dir <work-dir>" in skill
    assert "prepare-categories --work-dir <work-dir>" in skill
    assert "assemble-summary --work-dir <work-dir>" in skill
    assert "report-summary-manifest.yaml" in skill
    assert "maximum 70 words" in skill.lower()
    assert "maximum 50 words" in skill.lower()
    assert "no model call is permitted" in skill
    assert "only when CMC is unchanged" in skill

def test_legacy_skill_uses_same_state_driven_case_clis():
    skill = LEGACY_SKILL.read_text(encoding="utf-8")
    assert "setup_workflow.py --workflow legacy-v1" in skill
    assert "run_case.py diagnosis --work-dir <work-dir>" in skill
    assert "run_case.py downstream --work-dir <work-dir>" in skill
    assert "case_major_categories.py" not in skill
    assert "create_work_dir.py" not in skill
    assert "resolve_demo.py" not in skill
    assert "python3 -m venv .env" not in skill
    assert "pip install -r requirements.txt" not in skill


def test_release_manifest_contains_root_product_and_available_workflows():
    manifest = RELEASE_MANIFEST.read_text(encoding="utf-8").splitlines()
    for required in (
        "README.md",
        "SKILL.md",
        "NEWS.md",
        "nel.py",
        "config/settings.json.template",
        "config/pipelines/*.yaml",
        "config/ngs-panel-scope.md",
        "docs/corpus.md",
        "docs/validation.md",
        "workflows/registry.json",
        "workflows/common.py",
        "workflows/terraced_v6/*.py",
        "workflows/terraced_v6/settings.json.template",
        "workflows/terraced_v6/pipelines/*.yaml",
        "workflows/terraced_v6/prompts/*.md",
        "workflows/terraced_v6/schemas/*.json",
        "workflows/terraced_v6/stages/*.yaml",
        ":(glob)workflows/proforma_v1/*.py",
        "workflows/proforma_v1/workflow.json",
        "workflows/proforma_v1/SKILL.md",
        "workflows/proforma_v1/settings.json.template",
        ":(glob)workflows/proforma_v1/pipelines/*.yaml",
        ":(glob)workflows/proforma_v1/prompts/*.md",
        ":(glob)workflows/proforma_v1/prompts/evidence/*.md",
        ":(glob)workflows/proforma_v1/schemas/*.json",
        ":(glob)workflows/proforma_v1/stages/*.yaml",
        ":(glob)workflows/proforma_v1/workflow/*.yaml",
        ":(glob)workflows/proforma_v1/engine/*.py",
        ":(glob)workflows/proforma_v1/executors/*.py",
        "scripts/setup_workflow.py",
        "scripts/workflow_registry.py",
        "scripts/core/*.py",
        "validation/mark_validation_report.md",
    ):
        assert required in manifest
    assert not any(
        line.startswith("workflows/")
        and line.split("/", 2)[1]
        not in {"terraced_v6", "proforma_v1", "__init__.py", "common.py", "registry.json"}
        for line in manifest
    )
    for obsolete in (
        "workflows/legacy_v1/*",
        "workflows/diagnosis_first_v1/*",
        "workflows/categorical_v1/*",
        "workflows/terraced_v1/*",
        "workflows/terraced_v2/*",
        "workflows/terraced_v3/*",
        "workflows/terraced_v4/*",
        "workflows/terraced_v5/*",
        "scripts/workflow_runtime.py",
    ):
        assert obsolete not in manifest



def test_obsolete_phase1_files_are_removed():
    for path in (
        ROOT / "0.2.2_prototype_skill.md",
        ROOT / "scripts" / "prototype_workflow.py",
        ROOT / "scripts" / "create_work_dir.py",
        ROOT / "scripts" / "case_major_categories.py",
        ROOT / "scripts" / "resolve_demo.py",
        ROOT / "scripts" / "retrieval_core.py",
        ROOT / "scripts" / "card_tags.py",
        ROOT / "scripts" / "append_integrated_diagnosis.py",
        ROOT / "scripts" / "validate_adjudication.py",
        ROOT / "workflows" / "prototype",
        ROOT / "workflows" / "legacy",
    ):
        assert not path.exists(), path


def test_structure_case_uses_active_workflow_semantics_without_hardcoded_old_paths():
    text = (SHARED_PROMPT_DIR / "structure_case.md").read_text(encoding="utf-8")
    assert "active workflow specification selected by root `SKILL.md`" in text
    assert "workflows/prototype" not in text
    assert "workflows/legacy/" not in text
