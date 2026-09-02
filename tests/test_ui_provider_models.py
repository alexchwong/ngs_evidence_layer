"""Deterministic contract checks for provider/profile browser UI enhancements."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "ui" / "assets" / "provider-models.js"
OPENROUTER = ROOT / "config" / "openrouter_models.json"
WORKFLOW_SERVER = ROOT / "ui" / "workflow_server.py"


def test_openrouter_shortlist_contract() -> None:
    doc = json.loads(OPENROUTER.read_text(encoding="utf-8"))
    rows = doc["models"]
    assert len(rows) == 8
    assert len({row["id"] for row in rows}) == 8
    assert {row["category"] for row in rows} <= {
        "Fast / Cheap",
        "High Quality",
        "Fast & Local-compatible",
    }


def test_provider_ui_contract() -> None:
    text = JS.read_text(encoding="utf-8")
    assert "Provider Class" in text
    assert "/api/config-check" in text
    assert "maybePromptOpenRouterKey" in text
    assert "Other OpenRouter models — alphabetical" in text
    assert "Other…" in text
    assert "body.provider_class" in text


def test_alias_observer_cannot_watch_its_own_dropdown_mutations() -> None:
    text = JS.read_text(encoding="utf-8")
    start = text.index("function watchAliasCards()")
    end = text.index("function updateDatalists", start)
    observer = text[start:end]
    assert "observer.observe(aliases, { childList: true });" in observer
    assert "subtree: true" not in observer


def test_saved_profiles_persist_provider_class_metadata() -> None:
    text = WORKFLOW_SERVER.read_text(encoding="utf-8")
    assert 'pipeline_meta["provider_class"] = provider_class' in text
    assert 'row["provider_class"] = _infer_provider_class' in text


def test_profile_editor_layout_contract() -> None:
    text = JS.read_text(encoding="utf-8")
    assert "nel-profile-toolbar" in text
    assert "toolbar.appendChild(loadButton)" in text
    assert "toolbar.appendChild(saveButton)" not in text
    assert "nel-profile-identity-actions" in text
    assert "actions.appendChild(saveButton)" in text
    assert "Overwrite profile?" in text
    assert "installConnectionSummary" in text
    assert "Local OpenAI-compatible models served by LM Studio." in text
    assert "Hosted models accessed through OpenRouter" in text


def test_openrouter_routing_dropdown_preserves_runtime_contract() -> None:
    text = JS.read_text(encoding="utf-8")
    # The native editor serialises SELECT routing controls as booleans, so the
    # visible provider selector must synchronise to the original text input.
    assert "select.dataset.nelRouteOrderSelect = '1'" in text
    assert "orderInput.hidden = true" in text
    assert "orderInput.value = select.value" in text
    assert "select.dataset.route = 'order'" not in text
    assert "/api/openrouter-providers" in text
    assert "Default / Auto" in text


def test_openrouter_provider_endpoint_parser_is_schema_tolerant() -> None:
    text = WORKFLOW_SERVER.read_text(encoding="utf-8")
    assert 'endpoint.get("provider_tag")' in text
    assert 'endpoint.get("tag")' in text
    assert 'endpoint.get("provider_slug")' in text
    assert 'path == "/api/openrouter-providers"' in text
