from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from validation.scripts import package_marking as contract
from workflows.proforma_v1 import automatic_marking, layout, model_observability, step as staged


def _prep(tmp_path: Path):
    return {
        "status": "pending",
        "suite": "nel-validate-test",
        "case": "1",
        "report_sha256": "a" * 64,
        "call_id": "validation-marking-aaaaaaaa-01",
        "prompt": "mark this report",
        "output": tmp_path / "marking.md",
    }


def test_self_marking_handoff_is_recorded_in_model_observability(monkeypatch, tmp_path):
    layout.ensure_dirs(tmp_path)
    prep = _prep(tmp_path)
    contract.set_automatic_marking_pending(
        tmp_path, prep["suite"], prep["case"], prep["report_sha256"], prep["call_id"], 1
    )
    monkeypatch.setattr(staged, "_profile", lambda *_args: SimpleNamespace(is_self=True, model="self"))
    monkeypatch.setattr(staged, "_refresh_model_operation_index", lambda *_args: None)
    with pytest.raises(staged.Handoff):
        automatic_marking._self_handoff(tmp_path, prep, binding=SimpleNamespace(is_self=True, model="self"))
    root = layout.model_step_dir(tmp_path, prep["call_id"], existing=True)
    meta = json.loads((root / "attempts" / "01" / "call.json").read_text(encoding="utf-8"))
    assert meta["logical_operation"] == "validation.marking"
    assert meta["role"] == "marking"
    assert meta["status"] == "running"
    index = model_observability.build_model_operation_index(tmp_path)
    operation = next(row for row in index["operations"] if row["id"] == "validation.marking")
    assert operation["calls"][0]["role"] == "marking"
    assert operation["calls"][0]["attempts"][0]["status"] == "running"


def test_self_invalid_marking_preserves_attempt_one_and_hands_off_attempt_two(monkeypatch, tmp_path):
    layout.ensure_dirs(tmp_path)
    prep = _prep(tmp_path)
    contract.set_automatic_marking_pending(
        tmp_path, prep["suite"], prep["case"], prep["report_sha256"], prep["call_id"], 1
    )
    monkeypatch.setattr(staged, "_profile", lambda *_args: SimpleNamespace(is_self=True, model="self"))
    monkeypatch.setattr(staged, "_refresh_model_operation_index", lambda *_args: None)
    monkeypatch.setattr(staged, "_retry", lambda _name: 2)
    with pytest.raises(staged.Handoff):
        automatic_marking._self_handoff(tmp_path, prep, binding=SimpleNamespace(is_self=True, model="self"))
    Path(prep["output"]).write_text("bad marking", encoding="utf-8")
    monkeypatch.setattr(
        contract,
        "complete_automatic_marking",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(contract.MarkingValidationError("bad")),
    )
    with pytest.raises(staged.Handoff):
        automatic_marking._self_handoff(tmp_path, prep, binding=SimpleNamespace(is_self=True, model="self"))
    root = layout.model_step_dir(tmp_path, prep["call_id"], existing=True)
    first = json.loads((root / "attempts" / "01" / "call.json").read_text(encoding="utf-8"))
    second = json.loads((root / "attempts" / "02" / "call.json").read_text(encoding="utf-8"))
    assert first["status"] == "rejected"
    assert second["status"] == "running"
    assert not Path(prep["output"]).exists()


def test_provider_execution_uses_marking_role_and_validation_contract(monkeypatch, tmp_path):
    prep = _prep(tmp_path)
    binding = SimpleNamespace(is_self=False)
    monkeypatch.setattr(automatic_marking, "_state", lambda _work: (prep["suite"], prep["case"]))
    monkeypatch.setattr(contract, "prepare_automatic_marking", lambda *_args: dict(prep))
    monkeypatch.setattr(staged, "_profile", lambda *_args: binding)
    seen = {}
    def fake_call(work, passed_prep, **kwargs):
        seen.update({"work": work, "prep": passed_prep, **kwargs})
        Path(passed_prep["output"]).write_text("accepted", encoding="utf-8")
    monkeypatch.setattr(automatic_marking, "_run_provider_marking", fake_call)
    monkeypatch.setattr(
        contract,
        "complete_automatic_marking",
        lambda *_args, **_kwargs: {"status": "complete"},
    )
    result = automatic_marking.run(tmp_path, profile="openrouter")
    assert result["status"] == "complete"
    assert seen["binding"] is binding
    assert seen["profile"] == "openrouter"
    assert seen["prep"]["call_id"] == prep["call_id"]
    assert callable(seen["validator"])


def test_provider_marking_preserves_wrapped_markdown_and_final_json_fence(monkeypatch, tmp_path):
    layout.ensure_dirs(tmp_path)
    prep = _prep(tmp_path)
    raw = """```markdown
## Case 1

### R1 — Diagnosis and classification
**Category:** fully correct
```

```json
{
  \"criterion_results\": {
    \"R1C1\": {\"met\": true, \"failure_mode\": null}
  }
}
```
"""
    seen = {}
    monkeypatch.setattr(staged, "_profile", lambda *_args: SimpleNamespace(is_self=False, model="syntax"))
    monkeypatch.setattr(staged, "_retry", lambda _name: 2)
    monkeypatch.setattr(staged, "_task_io", lambda *args, **kwargs: object())
    def fake_run(request, _io):
        seen["prepared"] = request.prepare(raw)
        Path(prep["output"]).write_text(seen["prepared"], encoding="utf-8")
        return seen["prepared"]
    monkeypatch.setattr(automatic_marking.validated_model_task, "run", fake_run)
    result = automatic_marking._run_provider_marking(
        tmp_path, prep, binding=SimpleNamespace(is_self=False, model="marking"),
        profile="openrouter", validator=lambda _text: "valid",
    )
    assert result == raw
    assert seen["prepared"] == raw
    assert seen["prepared"].rstrip().endswith("```")
    assert "```json" in seen["prepared"]


def test_self_pending_handoff_replay_does_not_overwrite_attempt_metadata(monkeypatch, tmp_path):
    layout.ensure_dirs(tmp_path)
    prep = _prep(tmp_path)
    contract.set_automatic_marking_pending(
        tmp_path, prep["suite"], prep["case"], prep["report_sha256"], prep["call_id"], 1
    )
    monkeypatch.setattr(staged, "_profile", lambda *_args: SimpleNamespace(is_self=True, model="self"))
    monkeypatch.setattr(staged, "_refresh_model_operation_index", lambda *_args: None)
    with pytest.raises(staged.Handoff):
        automatic_marking._self_handoff(tmp_path, prep, binding=SimpleNamespace(is_self=True, model="self"))
    root = layout.model_step_dir(tmp_path, prep["call_id"], existing=True)
    call_path = root / "attempts" / "01" / "call.json"
    before = call_path.read_text(encoding="utf-8")
    with pytest.raises(staged.Handoff):
        automatic_marking._self_handoff(tmp_path, prep, binding=SimpleNamespace(is_self=True, model="self"))
    assert call_path.read_text(encoding="utf-8") == before


def test_complete_marking_does_not_invoke_model_again(monkeypatch, tmp_path):
    monkeypatch.setattr(automatic_marking, "_state", lambda _work: ("nel-validate-test", "1"))
    monkeypatch.setattr(
        contract,
        "prepare_automatic_marking",
        lambda *_args: {"status": "complete", "suite": "nel-validate-test", "case": "1"},
    )
    monkeypatch.setattr(staged, "_profile", lambda *_args: (_ for _ in ()).throw(AssertionError("model binding should not be touched")))
    assert automatic_marking.run(tmp_path, profile="openrouter")["status"] == "complete"


def test_binding_failure_records_marking_failed(monkeypatch, tmp_path):
    prep = _prep(tmp_path)
    monkeypatch.setattr(automatic_marking, "_state", lambda _work: (prep["suite"], prep["case"]))
    monkeypatch.setattr(contract, "prepare_automatic_marking", lambda *_args: dict(prep))
    monkeypatch.setattr(staged, "_profile", lambda *_args: (_ for _ in ()).throw(ValueError("missing marking role")))
    with pytest.raises(ValueError, match="missing marking role"):
        automatic_marking.run(tmp_path, profile="old-profile")
    status = contract.read_marking_status(tmp_path)
    assert status["status"] == "failed"
    assert "missing marking role" in status["error"]
