#!/usr/bin/env python3
"""Build external-marking bundles and validate automatic post-report marking artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.scripts.bundled_cases import (  # noqa: E402
    is_validation_mode,
    marking_bundle_filename,
    normalise_selector,
    retrieve_case_input,
    retrieve_marking_criteria,
    validation_modes,
)

DEFAULT_PROMPT = ROOT / "validation" / "mark_validation_report.md"
CASE_TOKEN = "{{CASE_IDENTIFIER}}"
CRITERIA_TOKEN = "{{CASE_SPECIFIC_MARKING_CRITERIA}}"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MARKING_MD = "marking.md"
MARKING_JSON = "marking.json"
FUNCTIONAL_JSON = "functional.json"
MARKING_STATUS = "marking-status.json"
DUBLIN_MODE = "nel-validate-dublin"
CRITERION_ID_RE = re.compile(r"\*\*(R[1-5]C[1-9][0-9]*)\.\*\*")
JSON_BLOCK_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
RUBRIC_SECTION_RE = re.compile(
    r"^###\s+R([1-5])\b[^\n]*\n(?P<body>.*?)(?=^###\s+R[1-5]\b|\Z)",
    re.MULTILINE | re.DOTALL,
)
CATEGORY_RE = re.compile(r"^\*\*Category:\*\*\s*(.+?)\s*$", re.MULTILINE)
ALLOWED_CATEGORIES = {
    "fully correct",
    "partially correct",
    "omission error",
    "commission error",
    "hallucination commission error",
    "not applicable",
}
ALLOWED_FAILURE_MODES = {"partial", "omitted", "contradicted"}


class MarkingValidationError(ValueError):
    """Raised when a marking-model response violates the canonical contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_nonempty_report(report_path: Path) -> str:
    report_path = Path(report_path)
    if not report_path.is_file():
        raise FileNotFoundError(
            f"report-final.md is missing: {report_path}. Complete report finalisation before marking."
        )
    report = report_path.read_text(encoding="utf-8")
    if not report.strip():
        raise ValueError(f"report-final.md is empty: {report_path}")
    return report


def report_sha256(report_path: Path) -> str:
    """Return the digest that binds marking artifacts to one exact final report."""
    report_path = Path(report_path)
    _read_nonempty_report(report_path)
    return hashlib.sha256(report_path.read_bytes()).hexdigest()


def render_marking_prompt(mode: str, case_id: str, prompt_path: Path = DEFAULT_PROMPT) -> str:
    if not is_validation_mode(mode):
        raise ValueError(f"external marking bundles are only defined for validation modes, not {mode!r}")
    case_id = normalise_selector(mode, case_id)
    template = Path(prompt_path).read_text(encoding="utf-8")
    criteria = retrieve_marking_criteria(mode, case_id)
    missing = [token for token in (CASE_TOKEN, CRITERIA_TOKEN) if token not in template]
    if missing:
        raise ValueError("marking prompt template is missing required token(s): " + ", ".join(missing))
    return (
        template.replace(CASE_TOKEN, case_id.upper())
        .replace(CRITERIA_TOKEN, criteria.strip())
        .rstrip()
        + "\n"
    )


def render_automatic_marking_prompt(
    mode: str,
    case_id: str,
    report_path: Path,
    prompt_path: Path = DEFAULT_PROMPT,
) -> str:
    """Render evaluator-only model input after a final report exists.

    This is deliberately the only automatic-marking entry gate. The case-specific
    criteria are not retrieved until ``report-final.md`` has been verified as
    present and non-empty.
    """
    report = _read_nonempty_report(report_path)
    case_id = normalise_selector(mode, case_id)
    validation_case = retrieve_case_input(mode, case_id)
    marking_prompt = render_marking_prompt(mode, case_id, prompt_path)
    return (
        marking_prompt.rstrip()
        + "\n\n# Packaged evaluator inputs\n\n"
        + "## validation-case.md\n\n"
        + validation_case.rstrip()
        + "\n\n## report-final.md\n\n"
        + report.rstrip()
        + "\n"
    )


def _expected_criterion_ids(mode: str, case_id: str) -> tuple[str, ...]:
    criteria = retrieve_marking_criteria(mode, case_id)
    ids = tuple(CRITERION_ID_RE.findall(criteria))
    if not ids:
        raise MarkingValidationError(f"{mode} case {case_id}: canonical criteria contain no RxCy identifiers")
    if len(ids) != len(set(ids)):
        raise MarkingValidationError(f"{mode} case {case_id}: canonical criteria contain duplicate RxCy identifiers")
    return ids


def _extract_criterion_results(marking_text: str) -> dict[str, dict[str, Any]]:
    blocks = JSON_BLOCK_RE.findall(marking_text)
    if len(blocks) != 1:
        raise MarkingValidationError(f"expected exactly one fenced JSON object; found {len(blocks)}")
    try:
        payload = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise MarkingValidationError(f"criterion_results JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"criterion_results"}:
        raise MarkingValidationError("marking JSON keys must be exactly criterion_results")
    results = payload["criterion_results"]
    if not isinstance(results, dict):
        raise MarkingValidationError("criterion_results must be a JSON object")
    return results


def _extract_rubrics(marking_text: str, expected_ids: tuple[str, ...]) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    matches = list(RUBRIC_SECTION_RE.finditer(marking_text))
    for match in matches:
        rubric = f"R{match.group(1)}"
        if rubric in sections:
            raise MarkingValidationError(f"duplicate {rubric} rubric section")
        category_matches = CATEGORY_RE.findall(match.group("body"))
        if len(category_matches) != 1:
            raise MarkingValidationError(f"{rubric} must contain exactly one **Category:** field")
        category = category_matches[0].strip().lower()
        if category not in ALLOWED_CATEGORIES:
            raise MarkingValidationError(
                f"{rubric} category must be one of {sorted(ALLOWED_CATEGORIES)}; got {category!r}"
            )
        applicable = any(cid.startswith(rubric + "C") for cid in expected_ids)
        if applicable and category == "not applicable":
            raise MarkingValidationError(f"{rubric} has case-specific criteria and cannot be not applicable")
        if not applicable and category != "not applicable":
            raise MarkingValidationError(f"{rubric} has no case-specific criteria and must be not applicable")
        sections[rubric] = {"category": category}
    expected_rubrics = {f"R{i}" for i in range(1, 6)}
    if set(sections) != expected_rubrics:
        missing = sorted(expected_rubrics - set(sections))
        extra = sorted(set(sections) - expected_rubrics)
        raise MarkingValidationError(f"rubric section mismatch; missing={missing}, extra={extra}")
    return {f"R{i}": sections[f"R{i}"] for i in range(1, 6)}


def validate_marking_output(
    mode: str,
    case_id: str,
    marking_text: str,
    *,
    report_digest: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize one automatic/external marking response."""
    if not is_validation_mode(mode):
        raise MarkingValidationError(f"marking is not applicable to non-validation mode {mode!r}")
    case_id = normalise_selector(mode, case_id)
    if not str(marking_text or "").strip():
        raise MarkingValidationError("marking output is empty")
    expected_ids = _expected_criterion_ids(mode, case_id)
    results = _extract_criterion_results(marking_text)
    expected = set(expected_ids)
    actual = set(results)
    if actual != expected:
        raise MarkingValidationError(
            f"criterion_results mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
        )
    normalized_results: dict[str, dict[str, Any]] = {}
    for criterion_id in expected_ids:
        outcome = results[criterion_id]
        if not isinstance(outcome, dict):
            raise MarkingValidationError(f"{criterion_id}: result must be an object")
        if set(outcome) != {"met", "failure_mode"}:
            raise MarkingValidationError(f"{criterion_id}: result keys must be exactly met and failure_mode")
        met = outcome.get("met")
        failure_mode = outcome.get("failure_mode")
        if not isinstance(met, bool):
            raise MarkingValidationError(f"{criterion_id}: met must be boolean")
        if met and failure_mode is not None:
            raise MarkingValidationError(f"{criterion_id}: met=true requires failure_mode=null")
        if not met and failure_mode not in ALLOWED_FAILURE_MODES:
            raise MarkingValidationError(
                f"{criterion_id}: met=false requires failure_mode in {sorted(ALLOWED_FAILURE_MODES)}"
            )
        normalized_results[criterion_id] = {"met": met, "failure_mode": failure_mode}
    rubrics = _extract_rubrics(marking_text, expected_ids)
    return {
        "schema_version": 1,
        "suite": mode,
        "case": case_id,
        "report_sha256": report_digest,
        "rubrics": rubrics,
        "criterion_results": normalized_results,
    }


def _status_path(work: Path) -> Path:
    return Path(work) / "logs" / MARKING_STATUS


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def read_marking_status(work: Path) -> dict[str, Any]:
    path = _status_path(work)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_marking_status(work: Path, **fields: Any) -> Path:
    payload = {"schema_version": 1, **fields, "updated_at": _utc_now()}
    return _write_json(_status_path(work), payload)


def _functional_is_current(work: Path, report_digest: str) -> bool:
    path = Path(work) / FUNCTIONAL_JSON
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == 1
        and payload.get("report_sha256") == report_digest
        and isinstance(payload.get("functions"), dict)
    )


def inspect_marking(work: Path) -> dict[str, Any]:
    """Return artifact-derived automatic-marking state for one proforma-v1 run.

    Clinical workflow completion is intentionally independent of this sidecar.
    A changed final report makes any previous marking ``stale`` rather than
    incomplete, while a run that has not yet produced a final report is simply
    ``pending``. Criteria are never retrieved before a non-empty final report
    exists.
    """
    work = Path(work).resolve()
    state_path = next(iter(sorted((work / "intermediates").glob("*_run_state/proforma-v1-run.json"))), None)
    if state_path is None:
        return {"applicable": False, "status": "unavailable", "error": "proforma-v1 run state not found"}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return {"applicable": False, "status": "unavailable", "error": str(exc)}
    mode = str(state.get("mode") or "")
    if not is_validation_mode(mode):
        return {"applicable": False, "status": "not_applicable", "suite": mode or None}

    try:
        case_id = normalise_selector(mode, state.get("validation_case"))
    except Exception as exc:
        return {
            "applicable": True,
            "status": "failed",
            "suite": mode,
            "case": state.get("validation_case"),
            "error": str(exc),
        }

    base = {"applicable": True, "suite": mode, "case": case_id}
    report_path = work / "report-final.md"
    if not report_path.is_file():
        return {**base, "status": "pending", "reason": "report_pending"}
    try:
        report = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {**base, "status": "failed", "error": str(exc)}
    if not report.strip():
        return {**base, "status": "pending", "reason": "report_pending"}

    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    status_doc = read_marking_status(work)
    marking_md = work / MARKING_MD
    marking_json = work / MARKING_JSON
    functional_json = work / FUNCTIONAL_JSON
    paths = {
        "marking_markdown": str(marking_md) if marking_md.is_file() else None,
        "marking_json": str(marking_json) if marking_json.is_file() else None,
        "functional_json": str(functional_json) if functional_json.is_file() else None,
    }

    prior_digest = status_doc.get("report_sha256")
    recorded = str(status_doc.get("status") or "")
    if prior_digest == digest and recorded == "failed":
        return {
            **base,
            "status": "failed",
            "report_sha256": digest,
            "call_id": status_doc.get("call_id"),
            "error": status_doc.get("error"),
            "artifacts": paths,
        }

    if marking_is_current(work, mode, case_id, digest):
        if mode == DUBLIN_MODE and not _functional_is_current(work, digest):
            return {
                **base,
                "status": "pending",
                "reason": "functional_translation_pending",
                "report_sha256": digest,
                "call_id": status_doc.get("call_id"),
                "artifacts": paths,
            }
        return {
            **base,
            "status": "complete",
            "report_sha256": digest,
            "call_id": status_doc.get("call_id"),
            "artifacts": paths,
        }

    has_prior = bool(status_doc) or marking_md.is_file() or marking_json.is_file() or functional_json.is_file()
    if has_prior and prior_digest and prior_digest != digest:
        return {
            **base,
            "status": "stale",
            "report_sha256": digest,
            "marked_report_sha256": prior_digest,
            "call_id": status_doc.get("call_id"),
            "artifacts": paths,
        }

    if prior_digest == digest and recorded == "pending":
        return {
            **base,
            "status": "pending",
            "report_sha256": digest,
            "call_id": status_doc.get("call_id"),
            "artifacts": paths,
        }
    if has_prior:
        return {
            **base,
            "status": "stale",
            "report_sha256": digest,
            "marked_report_sha256": prior_digest,
            "call_id": status_doc.get("call_id"),
            "artifacts": paths,
        }
    return {**base, "status": "pending", "report_sha256": digest, "artifacts": paths}


def load_marking_payload(work: Path) -> dict[str, Any] | None:
    """Return normalized marking JSON only when the current report is completely marked."""
    work = Path(work).resolve()
    state = inspect_marking(work)
    if state.get("status") != "complete":
        return None
    path = work / MARKING_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_functional_payload(work: Path) -> dict[str, Any] | None:
    """Return current Dublin functional JSON, or ``None`` for other/incomplete runs."""
    work = Path(work).resolve()
    state = inspect_marking(work)
    if state.get("status") != "complete" or state.get("suite") != DUBLIN_MODE:
        return None
    path = work / FUNCTIONAL_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("report_sha256") != state.get("report_sha256"):
        return None
    return payload


def invalidate_marking_artifacts(work: Path) -> None:
    work = Path(work)
    for name in (MARKING_MD, MARKING_JSON, FUNCTIONAL_JSON):
        (work / name).unlink(missing_ok=True)


def marking_is_current(work: Path, mode: str, case_id: str, report_digest: str | None = None) -> bool:
    """Return True only when persisted marking is valid for the current report bytes."""
    work = Path(work)
    report_path = work / "report-final.md"
    digest = report_digest or report_sha256(report_path)
    md_path = work / MARKING_MD
    json_path = work / MARKING_JSON
    if not md_path.is_file() or not json_path.is_file():
        return False
    try:
        stored = json.loads(json_path.read_text(encoding="utf-8"))
        normalized = validate_marking_output(
            mode,
            case_id,
            md_path.read_text(encoding="utf-8"),
            report_digest=digest,
        )
    except (OSError, json.JSONDecodeError, KeyError, ValueError, MarkingValidationError):
        return False
    return (
        isinstance(stored, dict)
        and stored.get("schema_version") == 1
        and stored.get("suite") == normalized["suite"]
        and stored.get("case") == normalized["case"]
        and stored.get("report_sha256") == digest
        and stored.get("rubrics") == normalized["rubrics"]
        and stored.get("criterion_results") == normalized["criterion_results"]
    )


def next_call_id(work: Path, report_digest: str) -> str:
    """Allocate a fresh logical marking call ID while preserving prior call roots.

    Model-step directories are numbered/sluggified by the workflow layout, so do
    not infer call IDs from directory names. Read authoritative call metadata
    instead. A pending self handoff for the same report reuses its call ID;
    failed/stale work gets a new one.
    """
    work = Path(work)
    status = read_marking_status(work)
    prefix = f"validation-marking-{report_digest[:8]}"
    if (
        status.get("report_sha256") == report_digest
        and status.get("status") == "pending"
        and isinstance(status.get("call_id"), str)
        and status["call_id"].startswith(prefix)
    ):
        return status["call_id"]
    highest = 0
    roots = work / "model_steps"
    if roots.is_dir():
        for call_meta in roots.glob("*/attempts/*/call.json"):
            try:
                doc = json.loads(call_meta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            call_id = str(doc.get("call_id") or "")
            match = re.fullmatch(re.escape(prefix) + r"-(\d+)", call_id)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:02d}"


def prepare_automatic_marking(work: Path, mode: str, case_id: str) -> dict[str, Any]:
    """Prepare one evaluator-only model task after report finalisation.

    This function performs no model execution and imports no workflow executor.
    """
    work = Path(work).resolve()
    if not is_validation_mode(mode):
        return {"status": "not_applicable", "suite": mode}
    case_id = normalise_selector(mode, case_id)
    report_path = work / "report-final.md"
    digest = report_sha256(report_path)
    if marking_is_current(work, mode, case_id, digest):
        if mode == DUBLIN_MODE:
            persist_marking_artifacts(
                work, mode, case_id, (work / MARKING_MD).read_text(encoding="utf-8"), digest
            )
        _write_marking_status(
            work, status="complete", suite=mode, case=case_id,
            report_sha256=digest, call_id=read_marking_status(work).get("call_id"),
        )
        return {"status": "complete", "suite": mode, "case": case_id, "report_sha256": digest}

    previous = read_marking_status(work)
    if previous.get("report_sha256") != digest or previous.get("status") == "failed":
        invalidate_marking_artifacts(work)
    call_id = next_call_id(work, digest)
    prompt = render_automatic_marking_prompt(mode, case_id, report_path)
    _write_marking_status(
        work, status="pending", suite=mode, case=case_id,
        report_sha256=digest, call_id=call_id,
        attempt=int(previous.get("attempt") or 1) if previous.get("call_id") == call_id else 1,
    )
    return {
        "status": "pending", "suite": mode, "case": case_id,
        "report_sha256": digest, "call_id": call_id,
        "prompt": prompt, "output": work / MARKING_MD,
    }


def persist_marking_artifacts(
    work: Path,
    mode: str,
    case_id: str,
    marking_text: str,
    report_digest: str,
) -> dict[str, Any]:
    """Validate and persist one accepted marking response."""
    work = Path(work)
    normalized = validate_marking_output(mode, case_id, marking_text, report_digest=report_digest)
    marking_md = work / MARKING_MD
    marking_md.write_text(marking_text.rstrip() + "\n", encoding="utf-8")
    _write_json(work / MARKING_JSON, normalized)
    functional_path = work / FUNCTIONAL_JSON
    if mode == DUBLIN_MODE:
        from validation.scripts.score_functional_dublin import score_case
        functional = {
            "schema_version": 1,
            **score_case(case_id, marking_text),
            "report_sha256": report_digest,
        }
        _write_json(functional_path, functional)
    else:
        functional_path.unlink(missing_ok=True)
    return normalized


def complete_automatic_marking(
    work: Path,
    mode: str,
    case_id: str,
    marking_text: str,
    report_digest: str,
    call_id: str,
) -> dict[str, Any]:
    normalized = persist_marking_artifacts(work, mode, case_id, marking_text, report_digest)
    _write_marking_status(
        work, status="complete", suite=mode, case=case_id,
        report_sha256=report_digest, call_id=call_id,
    )
    return {"status": "complete", **normalized, "call_id": call_id}


def set_automatic_marking_pending(
    work: Path, mode: str, case_id: str, report_digest: str, call_id: str, attempt: int
) -> None:
    _write_marking_status(
        work, status="pending", suite=mode, case=case_id, report_sha256=report_digest,
        call_id=call_id, attempt=int(attempt),
    )


def fail_automatic_marking(
    work: Path,
    mode: str,
    case_id: str,
    report_digest: str,
    call_id: str,
    error: Exception | str,
) -> None:
    _write_marking_status(
        work, status="failed", suite=mode, case=case_id,
        report_sha256=report_digest, call_id=call_id, error=str(error),
    )


def _writestr(zf: zipfile.ZipFile, name: str, text: str) -> None:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, text.encode("utf-8"))


def package_marking_bundle(
    mode: str,
    case_id: str,
    report_path: Path,
    output_path: Path | None = None,
    prompt_path: Path = DEFAULT_PROMPT,
) -> Path:
    """Package one completed validation report using the canonical suite registry."""
    if not is_validation_mode(mode):
        raise ValueError(f"unsupported validation mode for marking bundle: {mode!r}")
    report_path = Path(report_path)
    report = _read_nonempty_report(report_path)
    case_id = normalise_selector(mode, case_id)

    validation_case = retrieve_case_input(mode, case_id)
    marking_prompt = render_marking_prompt(mode, case_id, prompt_path)
    output = Path(output_path) if output_path is not None else report_path.parent / marking_bundle_filename(mode, case_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as zf:
        _writestr(zf, "marking-prompt.md", marking_prompt)
        _writestr(zf, "validation-case.md", validation_case.rstrip() + "\n")
        _writestr(zf, "report-final.md", report)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="Validation case selector, e.g. 1A")
    parser.add_argument("--mode", required=True, choices=sorted(validation_modes()))
    parser.add_argument("--report", type=Path, required=True, help="Path to report-final.md")
    parser.add_argument("--output", type=Path, help="Optional output ZIP path; canonical name is used by default")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    args = parser.parse_args()
    try:
        print(package_marking_bundle(args.mode, args.case, args.report, args.output, args.prompt).resolve())
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
