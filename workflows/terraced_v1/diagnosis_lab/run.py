#!/usr/bin/env python3
"""Run the isolated experimental diagnosis terrace against examples 1-6.

This tool is deliberately outside the registered workflow. It never writes into
terraced-v1 work directories and does not alter normal workflow configuration.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from scripts import vocab
from scripts.core import corpus
from scripts.core import retrieval as core_retrieval
from workflows.terraced_v1.diagnosis_lab.api_client import complete, config_for
from workflows.terraced_v1.diagnosis_lab import connector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
QUESTIONS_PATH = HERE / "questions.yaml"
TERRACE_PROMPT = HERE / "prompts" / "terrace.md"
REPORT_SYNTHESIS_PROMPT = HERE / "prompts" / "report_synthesis.md"
REPORT_REASONS_PROMPT = HERE / "prompts" / "report_reasons.md"
REPORT_ALIGNMENT_PROMPT = HERE / "prompts" / "report_alignment.md"
FIXTURES = HERE / "fixtures"
SYSTEM = (
    "You are executing an experimental bounded diagnosis-terrace step for a clinical NGS workflow. "
    "Use only the supplied case, state, and evidence. Do not use outside literature. "
    "Return exactly the requested YAML artifact and do not expose chain-of-thought."
)
REPORT_SYSTEM = (
    "You are executing a bounded post-diagnosis reporting step for a clinical NGS workflow. "
    "Use only the inputs supplied for the current pass. Return exactly the requested artifact "
    "without commentary or chain-of-thought."
)


def _load_questions() -> dict:
    doc = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema_version") != 2:
        raise ValueError("invalid diagnosis_lab questions.yaml")
    questions = doc.get("questions")
    profiles = doc.get("execution_profiles")
    if not isinstance(questions, list) or not questions or not isinstance(profiles, dict) or not profiles:
        raise ValueError("questions.yaml requires non-empty questions and execution_profiles")
    ids = []
    final_rows = []
    terrace_ids = []
    for index, row in enumerate(questions, 1):
        if not isinstance(row, dict):
            raise ValueError(f"questions[{index}] must be an object")
        qid = row.get("id")
        kind = row.get("kind")
        if not isinstance(qid, str) or not qid.strip() or qid in ids:
            raise ValueError(f"questions[{index}].id must be a unique non-empty string")
        if kind not in {"terrace", "final"}:
            raise ValueError(f"question {qid!r} kind must be terrace or final")
        if not isinstance(row.get("question"), str) or not row["question"].strip():
            raise ValueError(f"question {qid!r} requires non-empty question text")
        if not isinstance(row.get("guidance"), list) or any(not isinstance(x, str) or not x.strip() for x in row["guidance"]):
            raise ValueError(f"question {qid!r} guidance must be a list of non-empty strings")
        ids.append(qid)
        if kind == "final":
            final_rows.append(row)
        else:
            terrace_ids.append(qid)
    if len(final_rows) != 1:
        raise ValueError("questions.yaml must declare exactly one kind: final question")
    if questions[-1] is not final_rows[0]:
        raise ValueError("the kind: final question must be last in canonical question order")
    final = final_rows[0]
    if not isinstance(final.get("context"), dict) or not isinstance(final.get("output"), dict) or not isinstance(final.get("invariants"), dict):
        raise ValueError("the final question requires context, output and invariants configuration")
    for profile_id, profile in profiles.items():
        groups = profile.get("terrace_groups") if isinstance(profile, dict) else None
        if not isinstance(groups, list) or not groups or any(not isinstance(group, list) or not group for group in groups):
            raise ValueError(f"execution profile {profile_id!r} requires non-empty terrace_groups")
        flattened = [qid for group in groups for qid in group]
        if flattened != terrace_ids:
            raise ValueError(
                f"execution profile {profile_id!r} must cover every terrace question once in canonical order; "
                f"expected {terrace_ids!r}, found {flattened!r}"
            )
    return doc


def _question_plan(config: dict, profile: str) -> list[list[str]]:
    terrace_groups = config["execution_profiles"][profile]["terrace_groups"]
    final_id = next(row["id"] for row in config["questions"] if row["kind"] == "final")
    return [*terrace_groups, [final_id]]


def _fixture(number: int) -> dict:
    path = FIXTURES / f"example-{number:02d}" / "input.json"
    if not path.is_file():
        raise ValueError(f"missing fixture {path}; run fixture_builder.py")
    return json.loads(path.read_text(encoding="utf-8"))


def _render_cards(cards: list[dict]) -> str:
    if not cards:
        return "No diagnosis/germline cards were retrieved for this fixture."
    blocks = []
    for card in cards:
        blocks.append(
            "\n".join(
                [
                    f"### {card.get('card_id')}",
                    f"category: {card.get('category')}",
                    f"genes: {', '.join(card.get('genes') or []) or 'none'}",
                    f"diseases: {', '.join(card.get('diseases') or []) or 'none'}",
                    f"evidence_tier: {card.get('evidence_tier') or 'unspecified'}",
                    f"interpretation: {card.get('interpretation') or ''}",
                    f"source: {card.get('paper_nickname') or ''} ({card.get('publication_year') or ''})",
                ]
            )
        )
    return "\n\n".join(blocks)


def _expanded_cards(fixture: dict, cmcs: list[str]) -> list[dict]:
    """Mirror broad diagnostic retrieval when a terrace adds a new CMC."""
    genes = set(fixture["structured_case"]["genes"])
    corpus_doc, _index, _digest = corpus.load_corpus(corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX)
    cards = corpus.blacklist_cards(corpus.flatten(corpus_doc), corpus.DEFAULT_BLACKLIST)
    hits = []
    for card in cards:
        matched_genes = core_retrieval.match_genes(card, genes)
        matched_cmcs = core_retrieval._matches_case_major_category(card, cmcs)
        if card.get("category") == "diagnosis":
            if not matched_genes and not matched_cmcs:
                continue
        elif card.get("category") == "germline":
            if not matched_genes:
                continue
        else:
            continue
        hits.append(
            {
                "card_id": card.get("card_id"),
                "category": card.get("category"),
                "genes": card.get("genes") or [],
                "diseases": card.get("diseases") or [],
                "evidence_tier": card.get("evidence_tier"),
                "interpretation": card.get("interpretation"),
                "paper_nickname": card.get("paper_nickname"),
                "publication_year": card.get("publication_year"),
                "matched_genes": matched_genes,
                "matched_case_major_categories": matched_cmcs,
            }
        )
    hits.sort(key=lambda row: row["card_id"] or "")
    return hits


def _questions_message(config: dict, ids: list[str]) -> str:
    by_id = {row["id"]: row for row in config["questions"]}
    parts = ["# Current diagnosis terrace group", ""]
    for qid in ids:
        row = by_id[qid]
        parts.extend([f"## {qid}", row["question"], ""])
        parts.extend([f"- {line}" for line in row.get("guidance") or []])
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _base_context(fixture: dict, cards: list[dict]) -> str:
    return "\n\n".join(
        [
            "# Case notes\n" + fixture["case_notes"].rstrip(),
            "# Structured case\n```json\n" + json.dumps(fixture["structured_case"], indent=2, ensure_ascii=False) + "\n```",
            "# NGS assay scope\n" + fixture["ngs_panel_scope"].rstrip(),
            "# Allowed provisional CMC values\n" + json.dumps(fixture["allowed_provisional_cmcs"], ensure_ascii=False),
            "# Allowed WHO5 schema_disease routing values\n" + json.dumps(fixture["allowed_schema_diseases"], ensure_ascii=False),
            "# Diagnosis/germline evidence cards\n" + _render_cards(cards),
        ]
    ) + "\n"


def _parse_yaml(text: str) -> dict:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValueError(
            f"YAML — Problem: parser error{where}: {problem}. Required fix: return one complete syntactically "
            "valid YAML mapping only, with no Markdown fence or commentary."
        ) from exc
    if not isinstance(doc, dict):
        raise ValueError(
            f"Top level — Problem: expected one YAML mapping, received {type(doc).__name__}. "
            "Required fix: return the complete requested YAML object only."
        )
    return doc


def _validate_state(doc: dict, group_ids: list[str]) -> None:
    required = {"provisional_cmcs", "diagnoses", "facts", "uncertainties"}
    issues = []
    if set(doc) != required:
        issues.append(
            f"Top level — Problem: expected fields {sorted(required)}, received {sorted(doc)}. "
            "Required fix: return exactly provisional_cmcs, diagnoses, facts and uncertainties."
        )
    cmcs = doc.get("provisional_cmcs")
    if not isinstance(cmcs, list) or not cmcs:
        issues.append(
            f"provisional_cmcs — Problem: expected a non-empty list, received {cmcs!r}. "
            "Required fix: return one or more exact allowed provisional CMC strings."
        )
    else:
        for index, cmc in enumerate(cmcs):
            if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                issues.append(
                    f"provisional_cmcs[{index}] — Problem: {cmc!r} is not an allowed CMC. "
                    "Required fix: replace it with an exact allowed provisional CMC supplied in the prompt."
                )
    diagnoses = doc.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        issues.append(
            f"diagnoses — Problem: expected a non-empty list, received {diagnoses!r}. "
            "Required fix: return at least one paired WHO5/ICC diagnosis row."
        )
        diagnoses = []
    allowed_statuses = {"established", "indeterminate", "not_established", "not_applicable"}
    for index, row in enumerate(diagnoses):
        location = f"diagnoses[{index}]"
        required_row = {"schema_disease", "WHO5", "ICC", "materially_different"}
        if not isinstance(row, dict) or set(row) != required_row:
            received = sorted(row) if isinstance(row, dict) else type(row).__name__
            issues.append(
                f"{location} — Problem: expected fields {sorted(required_row)}, received {received!r}. "
                "Required fix: return exactly schema_disease, WHO5, ICC and materially_different."
            )
            continue
        if row["schema_disease"] not in vocab.CASE_DISEASE_SET or row["schema_disease"] == "MDS/AML":
            issues.append(
                f"{location}.schema_disease — Problem: {row['schema_disease']!r} is not an allowed WHO5 routing value. "
                "Required fix: use one exact allowed WHO5 schema_disease supplied in the prompt; ICC-only MDS/AML cannot control routing."
            )
        if not isinstance(row["materially_different"], bool):
            issues.append(
                f"{location}.materially_different — Problem: expected a boolean, received {row['materially_different']!r}. "
                "Required fix: use true or false."
            )
        for classifier in ("WHO5", "ICC"):
            outcome = row[classifier]
            if not isinstance(outcome, dict) or set(outcome) != {"status", "diagnosis"}:
                received = sorted(outcome) if isinstance(outcome, dict) else type(outcome).__name__
                issues.append(
                    f"{location}.{classifier} — Problem: expected exactly status and diagnosis, received {received!r}. "
                    "Required fix: return both configured fields only."
                )
                continue
            if outcome["status"] not in allowed_statuses:
                issues.append(
                    f"{location}.{classifier}.status — Problem: {outcome['status']!r} is invalid. "
                    f"Required fix: use one of {sorted(allowed_statuses)!r}."
                )
            diagnosis = outcome["diagnosis"]
            if diagnosis is not None and (not isinstance(diagnosis, str) or not diagnosis.strip()):
                issues.append(
                    f"{location}.{classifier}.diagnosis — Problem: expected null or a non-empty string, received {diagnosis!r}. "
                    "Required fix: supply the candidate/assigned diagnosis or null when none applies."
                )
            if outcome["status"] == "established" and diagnosis is None:
                issues.append(
                    f"{location}.{classifier}.diagnosis — Problem: status is established but diagnosis is null. "
                    "Required fix: supply the established diagnostic wording."
                )
    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        rows = doc.get(field)
        if not isinstance(rows, list):
            issues.append(
                f"{field} — Problem: expected a list, received {rows!r}. Required fix: return a YAML list; [] is valid."
            )
            continue
        for index, row in enumerate(rows):
            location = f"{field}[{index}]"
            if not isinstance(row, dict) or set(row) != {text_key, "reason"}:
                received = sorted(row) if isinstance(row, dict) else type(row).__name__
                issues.append(
                    f"{location} — Problem: expected exactly {text_key} and reason, received {received!r}. "
                    "Required fix: return both non-empty string fields only."
                )
                continue
            for key in (text_key, "reason"):
                if not isinstance(row[key], str) or not row[key].strip():
                    issues.append(
                        f"{location}.{key} — Problem: blank or not a string. Required fix: supply a non-empty string."
                    )
    if issues:
        rendered = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, 1))
        raise ValueError(f"diagnosis terrace state failed validation with {len(issues)} issue(s):\n{rendered}")


def _validate_transition(previous: dict | None, current: dict) -> None:
    if previous is None:
        return


def _reviewed_with_ids(reviewed: dict) -> dict:
    return {
        "provisional_cmcs": reviewed["provisional_cmcs"],
        "diagnoses": reviewed["diagnoses"],
        "facts": [dict(row, fact_id=f"PRE-FINAL-F{i}") for i, row in enumerate(reviewed["facts"], 1)],
        "uncertainties": [dict(row, uncertainty_id=f"PRE-FINAL-U{i}") for i, row in enumerate(reviewed["uncertainties"], 1)],
    }


def _validate_final(doc: dict, reviewed: dict, config: dict) -> None:
    required = set(config["output"]["keys"])
    if set(doc) != required:
        raise ValueError(
            f"Final output — Problem: keys must be exactly {sorted(required)}; received {sorted(doc)}. "
            "Required fix: return the complete final YAML object with only the configured keys."
        )
    issues = []
    for key in config["invariants"].get("preserve_fields") or []:
        if doc[key] != reviewed[key]:
            issues.append(
                f"Final output.{key} — Problem: the protected pre-final value was changed. "
                f"Required fix: copy {key} exactly from the supplied pre-final state."
            )
    fact_ids = {row["fact_id"] for row in reviewed["facts"]}
    uncertainty_ids = {row["uncertainty_id"] for row in reviewed["uncertainties"]}
    all_ids = fact_ids | uncertainty_ids
    if not isinstance(doc["supporting_facts"], list):
        issues.append("Final output.supporting_facts — Problem: expected a list. Required fix: return a YAML list.")
        supporting_facts = []
    else:
        supporting_facts = doc["supporting_facts"]
    for index, row in enumerate(supporting_facts):
        if not isinstance(row, dict) or set(row) != {"fact", "reason", "source_fact_ids"}:
            issues.append(
                f"Final output.supporting_facts[{index}] — Problem: expected exactly fact, reason and source_fact_ids. "
                "Required fix: return all three fields only."
            )
            continue
        ids = row["source_fact_ids"]
        if not isinstance(ids, list) or not ids or any(x not in fact_ids for x in ids):
            issues.append(
                f"Final output.supporting_facts[{index}].source_fact_ids — Problem: invalid IDs {ids!r}. "
                "Required fix: use one or more supplied PRE-FINAL-F IDs."
            )
    if not isinstance(doc["uncertainties"], list):
        issues.append("Final output.uncertainties — Problem: expected a list. Required fix: return a YAML list.")
        uncertainties = []
    else:
        uncertainties = doc["uncertainties"]
    seen_uncertainty_sources = set()
    for index, row in enumerate(uncertainties):
        if not isinstance(row, dict) or set(row) != {"uncertainty", "reason", "source_ids"}:
            issues.append(
                f"Final output.uncertainties[{index}] — Problem: expected exactly uncertainty, reason and source_ids. "
                "Required fix: return all three fields only."
            )
            continue
        ids = row["source_ids"]
        if not isinstance(ids, list) or not ids or any(x not in all_ids for x in ids):
            issues.append(
                f"Final output.uncertainties[{index}].source_ids — Problem: invalid IDs {ids!r}. "
                "Required fix: use one or more supplied PRE-FINAL-F/PRE-FINAL-U IDs."
            )
            continue
        seen_uncertainty_sources.update(x for x in ids if x in uncertainty_ids)
    # Deletion-resistant uncertainty invariant: each explicit pre-final uncertainty must survive mapping.
    missing = sorted(uncertainty_ids - seen_uncertainty_sources)
    if config["invariants"].get("require_all_prior_uncertainties") and missing:
        issues.append(
            f"Final output.uncertainties — Problem: dropped pre-final uncertainty source(s): {', '.join(missing)}. "
            "Required fix: represent every supplied PRE-FINAL-U source in at least one final uncertainty."
        )
    # Conservative lexical guard for technical numbers: final synthesis cannot introduce a new numeric token.
    reviewed_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(reviewed, ensure_ascii=False)))
    final_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(doc, ensure_ascii=False)))
    extra = sorted(final_numbers - reviewed_numbers)
    if config["invariants"].get("prohibit_new_numeric_tokens") and extra:
        issues.append(
            f"Final output — Problem: introduced numeric token(s) absent from the pre-final state: {', '.join(extra)}. "
            "Required fix: remove the new numbers or restore the supplied source-faithful wording."
        )
    if issues:
        rendered = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, 1))
        raise ValueError(f"final synthesis failed validation with {len(issues)} issue(s):\n{rendered}")


def _final_prompt(question: dict) -> str:
    guidance = "\n".join(f"- {line}" for line in question["guidance"])
    keys = question["output"]["keys"]
    schema = {
        "provisional_cmcs": [],
        "diagnoses": [],
        "supporting_facts": [{"fact": "...", "reason": "...", "source_fact_ids": ["PRE-FINAL-F1"]}],
        "uncertainties": [{"uncertainty": "...", "reason": "...", "source_ids": ["PRE-FINAL-U1"]}],
    }
    schema = {key: schema[key] for key in keys}
    return (
        f"# {question['id']} card-free diagnostic synthesis\n\n"
        f"{question['question']}\n\n"
        "This is a representation pass over an already reviewed diagnostic state, not new diagnostic reasoning.\n\n"
        "## Requirements\n"
        f"{guidance}\n\n"
        "Return YAML only with exactly this configured shape:\n\n```yaml\n"
        + yaml.safe_dump(schema, sort_keys=False, allow_unicode=True).rstrip()
        + "\n```\n"
    )


def _group_label(group_ids: list[str]) -> str:
    if len(group_ids) == 1:
        return group_ids[0]
    return f"{group_ids[0]}-{group_ids[-1]}"


def _call_directory(run_dir: Path, index: int, group_ids: list[str]) -> Path:
    path = run_dir / f"call_{index:02d}_{_group_label(group_ids)}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _write_yaml(path: Path, doc: dict | list) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


def _messages_markdown(messages: list[dict[str, str]]) -> str:
    parts = ["# Exact model-call messages", ""]
    for index, message in enumerate(messages, 1):
        role = str(message.get("role") or "unknown").upper()
        parts.extend([f"## Message {index}: {role}", "", str(message.get("content") or ""), ""])
    return "\n".join(parts).rstrip() + "\n"


def _write_call_inputs(
    call_dir: Path,
    *,
    index: int,
    group_ids: list[str],
    messages: list[dict[str, str]],
    questions_text: str,
    fixture: dict,
    cards: list[dict],
    previous_state: dict | None,
    transcript: list[dict[str, str]],
    is_final: bool,
) -> None:
    """Persist a human-auditable view plus the exact API payload for one model call."""
    metadata = {
        "call_index": index,
        "question_ids": group_ids,
        "question_group": _group_label(group_ids),
        "is_final_synthesis": is_final,
        "case_notes_supplied": True,
        "evidence_cards_supplied": not is_final,
        "prior_terrace_transcript_supplied": bool(transcript) and not is_final,
        "previous_state_supplied": previous_state is not None,
        "exact_api_input": "INPUT_messages.json",
        "accepted_output": "OUTPUT_state.yaml",
    }
    (call_dir / "CALL_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    overview = [
        f"# Model call {index:02d}: {_group_label(group_ids)}",
        "",
        f"- Questions: {', '.join(group_ids)}",
        f"- Case notes supplied: yes",
        f"- Diagnosis/germline evidence cards supplied: {'no' if is_final else 'yes'}",
        f"- Prior terrace transcript supplied: {'yes' if (transcript and not is_final) else 'no'}",
        f"- Previous validated state supplied: {'yes' if previous_state is not None else 'no'}",
        "- Exact payload sent to the API: `INPUT_messages.json`",
        "- Raw model response: `OUTPUT_raw.txt`",
        "- Accepted validated state: `OUTPUT_state.yaml`",
        "- Validation result: `OUTPUT_validation.json`",
        "",
    ]
    if is_final:
        overview.extend(
            [
                "The configured final question is deliberately card-free. It receives the original case notes and",
                "the protected pre-final state, but neither diagnosis cards nor the earlier terrace transcript.",
                "",
            ]
        )
    (call_dir / "INPUT_overview.md").write_text("\n".join(overview), encoding="utf-8")
    (call_dir / "INPUT_questions.md").write_text(questions_text, encoding="utf-8")
    (call_dir / "INPUT_case_notes.md").write_text(fixture["case_notes"].rstrip() + "\n", encoding="utf-8")
    (call_dir / "INPUT_messages.json").write_text(
        json.dumps(messages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (call_dir / "INPUT_messages_readable.md").write_text(_messages_markdown(messages), encoding="utf-8")

    if previous_state is None:
        (call_dir / "INPUT_previous_state.yaml").write_text("# none: this is the first model call\n", encoding="utf-8")
    elif is_final:
        _write_yaml(call_dir / "INPUT_previous_state.yaml", _reviewed_with_ids(previous_state))
    else:
        _write_yaml(call_dir / "INPUT_previous_state.yaml", previous_state)

    (call_dir / "INPUT_prior_transcript.json").write_text(
        json.dumps([] if is_final else transcript, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not is_final:
        (call_dir / "INPUT_evidence_cards.json").write_text(
            json.dumps(cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def _write_validation(call_dir: Path, *, passed: bool, validator: str, error: str | None = None) -> None:
    payload = {"passed": passed, "validator": validator}
    if error is not None:
        payload["error"] = error
    (call_dir / "OUTPUT_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _validated_model_call(
    call_dir: Path,
    provider,
    *,
    messages: list[dict[str, str]],
    parse,
    validate,
    validator_name: str,
    attempts: int,
):
    """Call, parse and validate with bounded model-visible deterministic repair feedback."""
    previous = None
    last_error = ""
    for attempt in range(1, attempts + 1):
        call_messages = list(messages)
        if previous is not None:
            call_messages.extend(
                [
                    {"role": "assistant", "content": previous},
                    {
                        "role": "user",
                        "content": (
                            "The previous output failed deterministic structural validation. Fix only the reported "
                            "defect(s) and return the complete artifact again.\n\nValidator feedback:\n" + last_error
                        ),
                    },
                ]
            )
        attempt_dir = call_dir / f"attempt_{attempt:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        messages_json = json.dumps(call_messages, indent=2, ensure_ascii=False) + "\n"
        (attempt_dir / "INPUT_messages.json").write_text(messages_json, encoding="utf-8")
        (attempt_dir / "INPUT_messages_readable.md").write_text(_messages_markdown(call_messages), encoding="utf-8")
        (call_dir / "INPUT_messages.json").write_text(messages_json, encoding="utf-8")
        (call_dir / "INPUT_messages_readable.md").write_text(_messages_markdown(call_messages), encoding="utf-8")
        try:
            raw = complete(provider, call_messages)
        except Exception as exc:
            (attempt_dir / "OUTPUT_api_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
            (call_dir / "OUTPUT_api_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
            raise
        (attempt_dir / "OUTPUT_raw.txt").write_text(raw, encoding="utf-8")
        (call_dir / "OUTPUT_raw.txt").write_text(raw, encoding="utf-8")
        try:
            result = parse(raw)
            validate(result)
        except (ValueError, KeyError, TypeError) as exc:
            last_error = str(exc)
            previous = raw
            _write_validation(attempt_dir, passed=False, validator=validator_name, error=last_error)
            _write_validation(call_dir, passed=False, validator=validator_name, error=last_error)
            continue
        _write_validation(attempt_dir, passed=True, validator=validator_name)
        _write_validation(call_dir, passed=True, validator=validator_name)
        return result
    raise ValueError(
        f"model output failed deterministic validation after {attempts} attempt(s). Final validator feedback: {last_error}"
    )


def _connector_call(
    run_dir: Path,
    provider,
    *,
    index: int,
    label: str,
    messages: list[dict[str, str]],
    output_name: str,
    parse,
    validate,
    attempts: int,
):
    """Execute one auditable post-final connector call."""
    call_dir = run_dir / f"connector_{index:02d}_{label}"
    call_dir.mkdir(parents=True, exist_ok=False)
    (call_dir / "INPUT_messages.json").write_text(
        json.dumps(messages, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (call_dir / "INPUT_messages_readable.md").write_text(_messages_markdown(messages), encoding="utf-8")
    result = _validated_model_call(
        call_dir,
        provider,
        messages=messages,
        parse=parse,
        validate=validate,
        validator_name="diagnosis_report_connector",
        attempts=attempts,
    )
    if isinstance(result, str):
        rendered = result.rstrip() + "\n"
    else:
        rendered = yaml.safe_dump(result, sort_keys=False, allow_unicode=True, width=100)
    (call_dir / output_name).write_text(rendered, encoding="utf-8")
    return result


def _run_report_connector(run_dir: Path, provider, fixture: dict, final_doc: dict, cards: list[dict], *, attempts: int) -> None:
    """Convert the accepted final state into grounded and evidence-aligned diagnosis prose."""
    sources = connector.diagnostic_sources(final_doc)
    source_context = {
        "case_notes": fixture["case_notes"],
        "structured_case": fixture["structured_case"],
        "reviewed_diagnostic_state": sources,
    }
    (run_dir / "REPORT_INPUT_SOURCES.yaml").write_text(
        yaml.safe_dump(source_context, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )
    synthesis_messages = [
        {"role": "system", "content": REPORT_SYSTEM},
        {
            "role": "user",
            "content": REPORT_SYNTHESIS_PROMPT.read_text(encoding="utf-8")
            + "\n\n# Initial case and reviewed diagnostic state\n```yaml\n"
            + yaml.safe_dump(source_context, sort_keys=False, allow_unicode=True, width=100).rstrip()
            + "\n```\n",
        },
    ]
    prose = _connector_call(
        run_dir,
        provider,
        index=1,
        label="synthesis",
        messages=synthesis_messages,
        output_name="OUTPUT_report.md",
        parse=lambda raw: raw.strip(),
        validate=connector.prose_to_facts,
        attempts=attempts,
    )
    prose = prose.rstrip() + "\n"
    (run_dir / "FINAL_REPORT_DRAFT.md").write_text(prose, encoding="utf-8")
    immutable = connector.prose_to_facts(prose)
    (run_dir / "REPORT_IMMUTABLE_FACTS.yaml").write_text(
        yaml.safe_dump(immutable, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )

    case_ids, diagnostic_ids = connector.source_id_sets(fixture["structured_case"], sources)
    grounding_input = {
        "immutable_report_facts": immutable["facts"],
        "initial_case": {
            "case_notes": fixture["case_notes"],
            "structured_case": fixture["structured_case"],
        },
        "reviewed_diagnostic_sources": sources,
    }
    grounding_messages = [
        {"role": "system", "content": REPORT_SYSTEM},
        {
            "role": "user",
            "content": REPORT_REASONS_PROMPT.read_text(encoding="utf-8")
            + "\n\n# Grounding input\n```yaml\n"
            + yaml.safe_dump(grounding_input, sort_keys=False, allow_unicode=True, width=100).rstrip()
            + "\n```\n",
        },
    ]
    grounded = _connector_call(
        run_dir,
        provider,
        index=2,
        label="reasons",
        messages=grounding_messages,
        output_name="OUTPUT_facts.yaml",
        parse=_parse_yaml,
        validate=lambda doc: connector.validate_grounded(
            doc,
            immutable,
            case_source_ids=case_ids,
            diagnostic_source_ids=diagnostic_ids,
        ),
        attempts=attempts,
    )
    (run_dir / "FINAL_FACTS.yaml").write_text(
        yaml.safe_dump(grounded, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )

    tagged_cards, permitted_tags = connector.runtime_cards(cards)
    alignment_input = {"grounded_report": grounded, "permitted_evidence_cards": tagged_cards}
    alignment_messages = [
        {"role": "system", "content": REPORT_SYSTEM},
        {
            "role": "user",
            "content": REPORT_ALIGNMENT_PROMPT.read_text(encoding="utf-8")
            + "\n\n# Alignment input\n```yaml\n"
            + yaml.safe_dump(alignment_input, sort_keys=False, allow_unicode=True, width=100).rstrip()
            + "\n```\n",
        },
    ]
    aligned = _connector_call(
        run_dir,
        provider,
        index=3,
        label="alignment",
        messages=alignment_messages,
        output_name="OUTPUT_aligned.yaml",
        parse=_parse_yaml,
        validate=lambda doc: connector.validate_aligned(doc, grounded, permitted_card_tags=permitted_tags),
        attempts=attempts,
    )
    (run_dir / "FINAL_ALIGNED.yaml").write_text(
        yaml.safe_dump(aligned, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )
    (run_dir / "FINAL_REPORT.md").write_text(connector.render_report(aligned), encoding="utf-8")


def _run_one(args, example: int) -> Path:
    qcfg = _load_questions()
    profile = qcfg["execution_profiles"].get(args.profile)
    if not profile:
        raise ValueError(f"unknown profile {args.profile!r}")
    groups = _question_plan(qcfg, args.profile)
    by_id = {row["id"]: row for row in qcfg["questions"]}
    fixture = _fixture(example)
    provider = None if args.dry_run else config_for(
        args.provider,
        args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(args.output_dir) if args.output_dir else HERE / "runs"
    run_dir = root / f"example-{example:02d}-{args.profile}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "RUN_INPUT_fixture.json").write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    cards = list(fixture["diagnosis_evidence_cards"])
    active_cmcs = list(fixture["structured_case"]["provisional_cmcs"])
    transcript: list[dict[str, str]] = []
    previous_state = None
    final_doc = None
    completed_calls: list[dict] = []

    for index, group_ids in enumerate(groups, 1):
        rows = [by_id[qid] for qid in group_ids]
        kinds = {row["kind"] for row in rows}
        if len(kinds) != 1:
            raise ValueError(f"question group {group_ids!r} mixes terrace and final kinds")
        is_final = "final" in kinds
        final_config = rows[0] if is_final else None
        questions_text = _questions_message(qcfg, group_ids)
        if is_final:
            if previous_state is None:
                raise ValueError("the configured final question requires a validated pre-final terrace state")
            reviewed = _reviewed_with_ids(previous_state)
            messages = [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": _final_prompt(final_config)
                    + "\n\n# Original case notes\n"
                    + fixture["case_notes"].rstrip()
                    + "\n\n# Protected pre-final state with source IDs\n```yaml\n"
                    + yaml.safe_dump(reviewed, sort_keys=False, allow_unicode=True, width=100).rstrip()
                    + "\n```\n\n"
                    + questions_text,
                },
            ]
        else:
            messages = [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": TERRACE_PROMPT.read_text(encoding="utf-8") + "\n\n" + _base_context(fixture, cards),
                },
                *transcript,
                {"role": "user", "content": questions_text},
            ]

        call_dir = _call_directory(run_dir, index, group_ids)
        _write_call_inputs(
            call_dir,
            index=index,
            group_ids=group_ids,
            messages=messages,
            questions_text=questions_text,
            fixture=fixture,
            cards=cards,
            previous_state=previous_state,
            transcript=transcript,
            is_final=is_final,
        )

        if args.dry_run:
            (call_dir / "OUTPUT_not_run.txt").write_text(
                "Dry-run: no model was called. Later model-call inputs are state-dependent and therefore were not fabricated.\n",
                encoding="utf-8",
            )
            completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "dry-run"})
            break

        try:
            if is_final:
                validator = "final_fidelity_validator"
                validate = lambda doc: _validate_final(doc, _reviewed_with_ids(previous_state), final_config)
            else:
                validator = "diagnosis_state_and_transition_validator"
                validate = lambda doc: (_validate_state(doc, group_ids), _validate_transition(previous_state, doc))
            doc = _validated_model_call(
                call_dir,
                provider,
                messages=messages,
                parse=_parse_yaml,
                validate=validate,
                validator_name=validator,
                attempts=args.structural_attempts,
            )
        except Exception as exc:
            completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "validation_failed"})
            raise

        rendered = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
        (call_dir / "OUTPUT_state.yaml").write_text(rendered, encoding="utf-8")
        completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "accepted"})
        final_doc = doc

        if not is_final:
            transcript.extend([{"role": "user", "content": questions_text}, {"role": "assistant", "content": rendered}])
            previous_state = doc
            requested_cmcs = list(doc["provisional_cmcs"])
            if set(requested_cmcs) != set(active_cmcs):
                active_cmcs = requested_cmcs
                cards = _expanded_cards(fixture, active_cmcs)

    if not args.dry_run:
        (run_dir / "FINAL_OUTPUT.yaml").write_text(
            yaml.safe_dump(final_doc, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
        )
        _run_report_connector(run_dir, provider, fixture, final_doc, cards, attempts=args.structural_attempts)
    metadata = {
        "example": example,
        "profile": args.profile,
        "provider": "dry-run" if args.dry_run else provider.provider,
        "model": None if args.dry_run else provider.model,
        "planned_groups": groups,
        "completed_calls": completed_calls,
        "fixture_corpus_digest": fixture.get("corpus_digest"),
        "layout": "one directory per model call; INPUT_* files are model inputs and OUTPUT_* files are model outputs/validation",
    }
    (run_dir / "RUN_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return run_dir

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--example", type=int, choices=range(1, 7), metavar="N")
    target.add_argument("--all-examples", action="store_true")
    parser.add_argument("--profile", choices=["frontier", "balanced", "deliberate"], default="balanced")
    parser.add_argument("--provider", choices=["lmstudio", "openrouter", "openai-compatible"], default="lmstudio")
    parser.add_argument("--model", default="qwen3-coder-next")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--structural-attempts", type=int, default=10)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="write the exact first API payload without calling a model")
    args = parser.parse_args()
    if args.structural_attempts < 1:
        parser.error("--structural-attempts must be at least 1")

    try:
        examples = range(1, 7) if args.all_examples else [args.example]
        for example in examples:
            run_dir = _run_one(args, example)
            print(run_dir)
    except Exception as exc:
        print(f"diagnosis_lab failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
