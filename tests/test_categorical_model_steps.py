"""Stage-1 coverage for the categorical-v1 script-driven model steps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import write_workflow_state  # noqa: E402
from workflows.categorical_v1 import model_client, model_registry, model_steps, step  # noqa: E402


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_shipped_registry_is_valid_and_defaults_to_self():
    registry = model_registry.load_registry()
    assert registry["default_profile"] == "self"
    for role in registry["roles"]:
        assert model_registry.resolve(role, "self").is_self


def test_delegating_profile_resolves_all_roles():
    registry = model_registry.load_registry()
    for role in registry["roles"]:
        binding = model_registry.resolve(role, "local-llm", None, registry)
        assert not binding.is_self
        assert binding.model
        assert binding.base_url.startswith("http")


def test_profile_resolution_order(tmp_path, monkeypatch):
    registry = model_registry.load_registry()
    state = {"schema_version": 1, "workflow_id": "categorical-v1", "mode": "ngs-report"}
    (tmp_path / "workflow.json").write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.delenv(model_registry.PROFILE_ENV, raising=False)
    assert model_registry.resolve_profile(None, tmp_path, registry) == "self"

    monkeypatch.setenv(model_registry.PROFILE_ENV, "local-llm")
    assert model_registry.resolve_profile(None, tmp_path, registry) == "local-llm"

    state["model_profile"] = "self"
    (tmp_path / "workflow.json").write_text(json.dumps(state), encoding="utf-8")
    assert model_registry.resolve_profile(None, tmp_path, registry) == "self"

    assert model_registry.resolve_profile("--local-llm", tmp_path, registry) == "local-llm"


def test_unknown_profile_lists_registered_profiles():
    with pytest.raises(ValueError) as excinfo:
        model_registry.resolve_profile("nope")
    assert "local-llm" in str(excinfo.value)
    assert "self" in str(excinfo.value)


def test_base_url_env_override_wins(monkeypatch):
    monkeypatch.setenv("NEL_LLM_BASE_URL", "http://192.168.1.10:1234/v1")
    binding = model_registry.resolve("judgment", "local-llm")
    assert binding.base_url == "http://192.168.1.10:1234/v1"


# ---------------------------------------------------------------------------
# Step table
# ---------------------------------------------------------------------------


def test_order_is_unique_and_category_steps_follow_canonical_order():
    assert len(model_steps.ORDER) == len(set(model_steps.ORDER))
    from workflows.categorical_v1 import report_yaml

    assert tuple(model_steps.CATEGORY_STEP_IDS.values()) == report_yaml.SUMMARY_SECTIONS
    assert model_steps.CATEGORY_STEP_IDS["6b1"] == "diagnosis"
    assert model_steps.CATEGORY_STEP_IDS["6b5"] == "germline"


def test_every_declared_prompt_file_exists():
    for step_id in model_steps.MODEL_STEP_IDS:
        spec = model_steps.get_step(step_id)
        for prompt in model_steps.prompt_sequence(spec):
            assert prompt.is_file(), f"{step_id} declares missing prompt {prompt}"


def test_step_1a_is_gated_out_of_validation_modes():
    assert "1a" not in model_steps.steps_for_mode("nel-validate")
    assert "1a" not in model_steps.steps_for_mode("nel-validate-function")
    assert "1a" in model_steps.steps_for_mode("ngs-report")


def test_unknown_step_lists_canonical_order():
    with pytest.raises(ValueError) as excinfo:
        model_steps.get_step("6b9")
    assert "6b1" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Bundles
# ---------------------------------------------------------------------------


def _manifest_text(cmc_changed: bool, statuses: dict[str, str]) -> str:
    """Render a complete category manifest; the runtime requires all five sections."""
    from workflows.categorical_v1 import report_yaml

    lines = [
        "schema_version: 1",
        f"cmc_changed: {'true' if cmc_changed else 'false'}",
        "refined_cmc: aml",
        "categories:",
    ]
    for category in report_yaml.SUMMARY_SECTIONS:
        status = statuses.get(category, "omitted_no_reportable_rules")
        lines.append(f"  {category}:")
        lines.append(f"    status: {status}")
        lines.append("    reason: test fixture")
    return "\n".join(lines) + "\n"


def _work_dir(tmp_path: Path, mode: str = "ngs-report", profile: str = "self") -> Path:
    work = tmp_path / "work"
    work.mkdir()
    write_workflow_state(work, "categorical-v1", mode, model_profile=profile)
    return work


def test_bundle_contains_declared_inputs_and_nothing_else(tmp_path):
    work = _work_dir(tmp_path)
    (work / "case.md").write_text("PATIENT CASE TEXT\n", encoding="utf-8")
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    (work / "diagnostic_evidence.json").write_text('{"private": true}\n', encoding="utf-8")

    spec = model_steps.get_step("1b")
    bundle = step.build_bundle(spec, work)

    assert '<input path="case.md">' in bundle
    assert '<input path="case-major-categories.json">' in bundle
    assert "diagnostic_evidence.json" not in bundle
    assert "PATIENT CASE TEXT" in bundle
    assert "case-input.json" in bundle


def test_bundle_fails_loudly_on_missing_input(tmp_path):
    work = _work_dir(tmp_path)
    (work / "case.md").write_text("case\n", encoding="utf-8")
    spec = model_steps.get_step("1b")
    with pytest.raises(step.StepFailure) as excinfo:
        step.build_bundle(spec, work)
    assert "case-major-categories.json" in str(excinfo.value)


def test_conditional_category_inputs_follow_the_cmc_branch(tmp_path):
    work = _work_dir(tmp_path)
    for name in (
        "case.md",
        "case-input.json",
        "report-draft.yaml",
        "report-draft-remainder.yaml",
        "report-summary-dx.yaml",
    ):
        (work / name).write_text("placeholder\n", encoding="utf-8")

    manifest_path = work / "report-summary-manifest.yaml"

    def write_manifest(cmc_changed: bool, status: str) -> None:
        manifest_path.write_text(_manifest_text(cmc_changed, {"prognosis": status}), encoding="utf-8")

    write_manifest(False, "pending_model_draft")
    permitted = [path.name for path in model_steps._inputs_category(work)]
    assert "report-summary-dx.yaml" in permitted

    write_manifest(True, "pending_model_draft")
    permitted = [path.name for path in model_steps._inputs_category(work)]
    assert "report-summary-dx.yaml" not in permitted


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_self_binding_hands_off_with_exit_10(tmp_path, capsys):
    work = _work_dir(tmp_path)
    (work / "case.md").write_text("case\n", encoding="utf-8")
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")

    code = step.main(["1b", "--work-dir", str(work)])
    assert code == step.EXIT_HANDOFF
    out = capsys.readouterr().out
    assert "HANDOFF" in out
    assert (work / ".model-steps" / "1b" / "prompt.md").is_file()


def test_not_required_category_exits_20(tmp_path, capsys):
    work = _work_dir(tmp_path)
    (work / "report-summary-manifest.yaml").write_text(
        _manifest_text(False, {"mrd": "omitted_no_reportable_rules"}), encoding="utf-8"
    )
    code = step.main(["6b4", "--work-dir", str(work)])
    assert code == step.EXIT_NOT_REQUIRED
    assert "NOT_REQUIRED" in capsys.readouterr().out


def test_complete_runs_validator_only(tmp_path, capsys):
    work = _work_dir(tmp_path)
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    (work / "case-input.json").write_text(
        json.dumps(
            {
                "case_major_category": "aml",
                "provisional_disease": "AML",
                "genes": ["NPM1"],
                "case_facts": [{"fact_id": "f1", "text": "blasts 40%"}],
            }
        ),
        encoding="utf-8",
    )
    assert step.main(["1b", "--work-dir", str(work), "--complete"]) == step.EXIT_OK
    assert "CMC1=aml" in capsys.readouterr().out


def test_complete_fails_with_exit_1_on_invalid_output(tmp_path):
    work = _work_dir(tmp_path)
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    (work / "case-input.json").write_text(
        json.dumps({"case_major_category": "not-a-category", "provisional_disease": "x", "genes": [], "case_facts": [{}]}),
        encoding="utf-8",
    )
    assert step.main(["1b", "--work-dir", str(work), "--complete"]) == step.EXIT_FAILURE


def test_step_1a_refused_in_validation_mode(tmp_path):
    work = _work_dir(tmp_path, mode="nel-validate")
    (work / "case-source.md").write_text("case\n", encoding="utf-8")
    assert step.main(["1a", "--work-dir", str(work)]) == step.EXIT_FAILURE


def test_driver_refuses_a_foreign_work_directory(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    write_workflow_state(work, "diagnosis-first-v1", "ngs-report")
    assert step.main(["1b", "--work-dir", str(work)]) == step.EXIT_FAILURE


# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------


def test_strip_code_fence_removes_one_wrapper():
    assert model_client.strip_code_fence("```yaml\nkey: value\n```").strip() == "key: value"
    assert model_client.strip_code_fence("key: value\n").strip() == "key: value"
    nested = "```\nouter\n```inner```\n```"
    assert "outer" in model_client.strip_code_fence(nested)


def test_complete_refuses_a_self_binding():
    binding = model_registry.resolve("judgment", "self")
    with pytest.raises(model_client.SelfExecution):
        model_client.complete(binding, "system", "user")


# ---------------------------------------------------------------------------
# Repair loop
# ---------------------------------------------------------------------------


def test_repair_bundle_carries_previous_output_and_error(tmp_path):
    work = _work_dir(tmp_path)
    (work / "case.md").write_text("case\n", encoding="utf-8")
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    spec = model_steps.get_step("1b")

    bundle = step.build_bundle(
        spec,
        work,
        validator_error="report-draft-dx.yaml is invalid YAML: mapping values are not allowed here",
        previous_output='{"case_major_category": "wrong"}',
    )

    assert "<previous-attempt" in bundle
    assert "<document-to-complete" not in bundle
    assert "mapping values are not allowed" in bundle
    assert "must be wrapped in double quotes" in bundle  # targeted YAML hint
    assert "complete corrected content" in bundle
    assert "(revision)" in bundle


def test_error_hint_is_specific_to_the_failure():
    yaml_hint = step._error_hint("report-draft-dx.yaml is invalid YAML: mapping values")
    assert "double quotes" in yaml_hint
    limit_hint = step._error_hint("diagnosis exceeds the 70 word limit")
    assert "clinically distinct fact" in limit_hint
    assert step._error_hint("some unrelated failure") == ""


def test_failed_complete_records_error_and_next_handoff_is_a_revision(tmp_path, capsys):
    work = _work_dir(tmp_path)
    (work / "case.md").write_text("case\n", encoding="utf-8")
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    (work / "case-input.json").write_text(
        json.dumps(
            {
                "case_major_category": "not-a-category",
                "provisional_disease": "AML",
                "genes": [],
                "case_facts": [{"fact_id": "f1"}],
            }
        ),
        encoding="utf-8",
    )

    assert step.main(["1b", "--work-dir", str(work), "--complete"]) == step.EXIT_FAILURE
    assert step._read_last_error(work, "1b") is not None

    assert step.main(["1b", "--work-dir", str(work)]) == step.EXIT_HANDOFF
    out = capsys.readouterr().out
    assert "MODE=revision" in out

    bundle = (work / ".model-steps" / "1b" / "prompt.md").read_text(encoding="utf-8")
    assert "<previous-attempt" in bundle
    assert "not-a-category" in bundle


def test_successful_complete_clears_the_pending_error(tmp_path):
    work = _work_dir(tmp_path)
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    step._record_last_error(work, "1b", "stale error")
    (work / "case-input.json").write_text(
        json.dumps(
            {
                "case_major_category": "aml",
                "provisional_disease": "AML",
                "genes": ["NPM1"],
                "case_facts": [{"fact_id": "f1"}],
            }
        ),
        encoding="utf-8",
    )
    assert step.main(["1b", "--work-dir", str(work), "--complete"]) == step.EXIT_OK
    assert step._read_last_error(work, "1b") is None


# ---------------------------------------------------------------------------
# Settings and truncation handling
# ---------------------------------------------------------------------------


def test_settings_default_when_file_absent(tmp_path):
    settings = step.load_settings(tmp_path / "missing.json")
    assert settings["max_attempts"]["default"] == 3


def test_settings_per_step_override(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"schema_version": 1, "max_attempts": {"default": 3, "3a": 6}}),
        encoding="utf-8",
    )
    settings = step.load_settings(path)
    assert step._max_attempts_for("3a", settings, None) == 6
    assert step._max_attempts_for("1b", settings, None) == 3
    assert step._max_attempts_for("3a", settings, 1) == 1  # CLI override wins


def test_truncated_completion_carries_partial_content_and_cap():
    exc = model_client.TruncatedCompletion("partial text so far", max_tokens=512)
    assert exc.content == "partial text so far"
    assert exc.max_tokens == 512
    assert "finish_reason=length" in str(exc)


def test_delegated_retry_grows_max_tokens_on_truncation(tmp_path, monkeypatch):
    work = _work_dir(tmp_path, profile="local-llm")
    (work / "case.md").write_text("case\n", encoding="utf-8")
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")

    calls: list[int] = []

    def fake_complete(binding, system, user):
        calls.append(binding.max_tokens)
        if len(calls) == 1:
            raise model_client.TruncatedCompletion('{"case_major_category": "aml"', binding.max_tokens)
        return json.dumps(
            {
                "case_major_category": "aml",
                "provisional_disease": "AML",
                "genes": ["NPM1"],
                "case_facts": [{"fact_id": "f1", "text": "blasts 40%"}],
            }
        )

    monkeypatch.setattr(model_client, "complete", fake_complete)
    code = step.main(["1b", "--work-dir", str(work), "--profile", "local-llm"])
    assert code == step.EXIT_OK
    assert len(calls) == 2
    assert calls[1] > calls[0]  # max_tokens grew between attempts


def test_delegated_retry_fails_cleanly_at_the_ceiling(tmp_path, monkeypatch, capsys):
    work = _work_dir(tmp_path, profile="local-llm")
    (work / "case.md").write_text("case\n", encoding="utf-8")
    (work / "case-major-categories.json").write_text('{"case_major_categories": ["aml"]}\n', encoding="utf-8")
    (work / "settings.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "max_attempts": {"default": 3},
                "max_tokens_growth_on_truncation": 1.0,  # cannot grow
                "max_tokens_ceiling": 100,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(step.SETTINGS_ENV, str(work / "settings.json"))

    def always_truncates(binding, system, user):
        raise model_client.TruncatedCompletion("partial", binding.max_tokens)

    monkeypatch.setattr(model_client, "complete", always_truncates)
    code = step.main(["1b", "--work-dir", str(work), "--profile", "local-llm"])
    assert code == step.EXIT_FAILURE
    assert "cannot be grown further" in capsys.readouterr().err
