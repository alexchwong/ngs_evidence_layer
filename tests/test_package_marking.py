from pathlib import Path
import tempfile
import zipfile

from validation.package_marking import package_marking_bundle, render_marking_prompt


ROOT = Path(__file__).resolve().parents[1]


def test_render_marking_prompt_embeds_case_and_criteria_without_evidence_input():
    rendered = render_marking_prompt("1A")
    assert "{{CASE_IDENTIFIER}}" not in rendered
    assert "{{CASE_SPECIFIC_MARKING_CRITERIA}}" not in rendered
    assert "**Validation case:** 1A" in rendered
    assert "### Case-specific marking criteria" in rendered
    assert "`evidence.md` —" not in rendered
    assert "Use `evidence.md`" not in rendered


def test_package_contains_only_external_marking_inputs():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        report = tmp / "report-final.md"
        report.write_text("# Report\n\nCandidate report.\n", encoding="utf-8")
        output = tmp / "validation.zip"

        package_marking_bundle("1A", report, output)

        with zipfile.ZipFile(output) as zf:
            assert zf.namelist() == [
                "marking-prompt.md",
                "validation-case.md",
                "report-final.md",
            ]
            prompt = zf.read("marking-prompt.md").decode("utf-8")
            case = zf.read("validation-case.md").decode("utf-8")
            packaged_report = zf.read("report-final.md").decode("utf-8")

        assert "**Validation case:** 1A" in prompt
        assert case.strip()
        assert packaged_report == report.read_text(encoding="utf-8")
        assert "evidence.md" not in zipfile.ZipFile(output).namelist()


def test_skill_validation_step_packages_instead_of_marks():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    step7 = skill.split("## Step 7 — Post-report delivery and validation", 1)[1]
    step7 = step7.split("## Final delivery contract", 1)[0]
    marking = step7.split("For `nel-validate`", 1)[1]

    assert "python validation/package_marking.py <validation-case>" in marking
    assert "validation-mark.md" not in marking
    assert "marking-criteria.md" not in marking
    assert "containing exactly" in marking
    assert "`marking-prompt.md`" in marking
    assert "`validation-case.md`" in marking
    assert "`report-final.md`" in marking
    assert "must not be included in the **marking** ZIP" in marking
    assert "do **not** start another model session" in marking


def test_functional_package_uses_selected_case_file_and_excludes_manifest():
    case_file = ROOT / "validation" / "case_functional.md"
    manifest_file = ROOT / "validation" / "case_functional_manifest.md"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        report = tmp / "report-final.md"
        report.write_text("# Report\n\nCandidate functional report.\n", encoding="utf-8")
        output = tmp / "nel-validation-function-1H.zip"

        package_marking_bundle("1H", report, output, case_file=case_file)

        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            prompt = zf.read("marking-prompt.md").decode("utf-8")
            case = zf.read("validation-case.md").decode("utf-8")

        assert names == ["marking-prompt.md", "validation-case.md", "report-final.md"]
        assert "CEBPA" in case
        assert "Lys313dup" in case
        assert "single mutation is explicitly an in-frame bZIP mutation" in prompt
        assert manifest_file.name not in names


def test_skill_declares_functional_validation_as_parallel_and_manifest_hidden():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "`nel-validate-function <case-id>`" in skill
    assert "--file validation/case_functional.md" in skill
    assert "--case-file validation/case_functional.md" in skill
    assert "nel-validation-function-<validation-case>.zip" in skill
    assert "case_functional_manifest.md` is never a runtime model input" in skill


def test_brief_package_uses_selected_case_file():
    case_file = ROOT / "validation" / "validation_brief.md"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        report = tmp / "report-final.md"
        report.write_text("# Report\n\nCandidate brief report.\n", encoding="utf-8")
        output = tmp / "nel-validation-brief-8.zip"

        package_marking_bundle("8", report, output, case_file=case_file)

        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            prompt = zf.read("marking-prompt.md").decode("utf-8")
            case = zf.read("validation-case.md").decode("utf-8")

        assert names == ["marking-prompt.md", "validation-case.md", "report-final.md"]
        assert "BCR::ABL1" in case
        assert "ANKRD26" in case
        assert "suspected/possible germline ANKRD26 predisposition" in prompt
