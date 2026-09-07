"""Regression contracts for workflow-agnostic profiles and deferred UI credentials."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SERVER = ROOT / "ui" / "workflow_server.py"
RUN_CREDENTIALS = ROOT / "ui" / "assets" / "run-credentials.js"
PIPELINE_REGISTRY = ROOT / "workflows" / "proforma_v1" / "pipeline_registry.py"


def test_ui_separates_profile_validity_from_credential_readiness() -> None:
    text = WORKFLOW_SERVER.read_text(encoding="utf-8")
    assert 'credential_required' in text
    assert 'credential_errors' in text
    assert 'base.config_check = _ui_config_check' in text
    assert '"/api/run-credential"' in text
    assert 'run_credential_status' in text


def test_setup_credential_bypass_is_scoped_to_setup_child_environment() -> None:
    text = WORKFLOW_SERVER.read_text(encoding="utf-8")
    assert '_SETUP_CREDENTIAL = threading.local()' in text
    assert '__NEL_UI_SETUP_ONLY__' in text
    assert '_SETUP_CREDENTIAL.env_name = ""' in text
    assert 'SECRETS[' not in text[text.index('def _start_setup'):text.index('def run_credential_status')]


def test_start_button_prompts_then_resumes_after_key_entry() -> None:
    text = RUN_CREDENTIALS.read_text(encoding="utf-8")
    assert "#runBtn" in text
    assert "event.stopImmediatePropagation()" in text
    assert "openKeyDialog" in text
    assert "Session key updated." in text
    assert "redispatchRun()" in text
    assert "runCredentialStatus" in text


def test_profile_role_defaults_are_global_and_lazy() -> None:
    text = PIPELINE_REGISTRY.read_text(encoding="utf-8")
    assert "ROLE_DEFAULTS" in text
    assert "def _default_role_row" in text
    assert "def with_role_defaults" in text
    assert "row=rows.get(role)" in text
    assert "_first_model_selector" in text
