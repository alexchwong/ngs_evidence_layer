from pathlib import Path
import tempfile
import zipfile

from validation.scripts.package_marking import package_marking_bundle, render_marking_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_render_marking_prompt_embeds_case_and_criteria_without_evidence_input():
    rendered = render_marking_prompt("nel-validate", "1A")
    assert "{{CASE_IDENTIFIER}}" not in rendered
    assert "{{CASE_SPECIFIC_MARKING_CRITERIA}}" not in rendered
    assert "**Validation case:** 1A" in rendered
    assert "### Case-specific marking criteria" in rendered
    assert "`evidence.md` —" not in rendered


def test_package_contains_only_external_marking_inputs_and_uses_canonical_name():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        report = tmp / "report-final.md"
        report.write_text("# Report\n\nCandidate report.\n", encoding="utf-8")
        output = package_marking_bundle("nel-validate", "1A", report)
        assert output.name == "nel-validation-1A.zip"
        with zipfile.ZipFile(output) as zf:
            assert zf.namelist() == ["marking-prompt.md", "validation-case.md", "report-final.md"]
            prompt = zf.read("marking-prompt.md").decode("utf-8")
            case = zf.read("validation-case.md").decode("utf-8")
            packaged_report = zf.read("report-final.md").decode("utf-8")
        assert "**Validation case:** 1A" in prompt
        assert case.strip()
        assert packaged_report == report.read_text(encoding="utf-8")


def test_functional_and_brief_modes_select_their_registered_sources():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        report = tmp / "report-final.md"
        report.write_text("# Report\n", encoding="utf-8")
        functional = package_marking_bundle("nel-validate-function", "1H", report)
        brief = package_marking_bundle("nel-validate-brief", "8", report)
        with zipfile.ZipFile(functional) as zf:
            assert "CEBPA" in zf.read("validation-case.md").decode("utf-8")
            assert "single mutation is explicitly an in-frame bZIP mutation" in zf.read("marking-prompt.md").decode("utf-8")
        with zipfile.ZipFile(brief) as zf:
            case = zf.read("validation-case.md").decode("utf-8")
            prompt = zf.read("marking-prompt.md").decode("utf-8")
            assert "BCR::ABL1" in case
            assert "ANKRD26" in case
            assert "suspected/possible germline ANKRD26 predisposition" in prompt


def test_package_fails_closed_without_completed_report():
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report-final.md"
        try:
            package_marking_bundle("nel-validate", "1A", report)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing report should prevent marking package creation")
