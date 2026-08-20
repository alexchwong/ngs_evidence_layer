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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
QUESTIONS_PATH = HERE / "questions.yaml"
TERRACE_PROMPT = HERE / "prompts" / "terrace.md"
DX7_PROMPT = HERE / "prompts" / "dx7.md"
FIXTURES = HERE / "fixtures"
SYSTEM = (
    "You are executing an experimental bounded diagnosis-terrace step for a clinical NGS workflow. "
    "Use only the supplied case, state, and evidence. Do not use outside literature. "
    "Return exactly the requested YAML artifact and do not expose chain-of-thought."
)


def _load_questions() -> dict:
    doc = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError("invalid diagnosis_lab questions.yaml")
    return doc


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
        raise ValueError(f"model returned invalid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("model output must be one YAML mapping")
    return doc


def _validate_state(doc: dict, group_ids: list[str]) -> None:
    required = {"provisional_cmcs", "diagnoses", "icc_diagnoses", "facts", "uncertainties"}
    if set(doc) != required:
        raise ValueError(f"state keys must be exactly {sorted(required)}; got {sorted(doc)}")
    if not isinstance(doc["provisional_cmcs"], list) or not doc["provisional_cmcs"]:
        raise ValueError("provisional_cmcs must be a non-empty list")
    for cmc in doc["provisional_cmcs"]:
        if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
            raise ValueError(f"invalid provisional CMC: {cmc!r}")
    if not isinstance(doc["diagnoses"], list):
        raise ValueError("diagnoses must be a list")
    if any(qid in {"DX4", "DX5", "DX6"} for qid in group_ids) and not doc["diagnoses"]:
        raise ValueError("DX4 onward requires an explicit WHO5 outcome")
    for row in doc["diagnoses"]:
        if not isinstance(row, dict) or set(row) != {"schema_disease", "narrow_diagnosis"}:
            raise ValueError("each diagnosis must contain exactly schema_disease and narrow_diagnosis")
        if row["schema_disease"] not in vocab.CASE_DISEASE_SET:
            raise ValueError(f"invalid schema_disease {row['schema_disease']!r}")
        if row["schema_disease"] == "MDS/AML":
            raise ValueError("ICC-only MDS/AML cannot be used as the WHO5 schema_disease")
        if not isinstance(row["narrow_diagnosis"], str) or not row["narrow_diagnosis"].strip():
            raise ValueError("narrow_diagnosis must be non-empty")
    if not isinstance(doc["icc_diagnoses"], list) or not all(isinstance(x, str) and x.strip() for x in doc["icc_diagnoses"]):
        raise ValueError("icc_diagnoses must be a list of non-empty strings")
    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        if not isinstance(doc[field], list):
            raise ValueError(f"{field} must be a list")
        for row in doc[field]:
            if not isinstance(row, dict) or set(row) != {text_key, "reason"}:
                raise ValueError(f"each {field} row must contain exactly {text_key} and reason")
            if not all(isinstance(row[k], str) and row[k].strip() for k in row):
                raise ValueError(f"{field} entries must contain non-empty strings")


def _validate_transition(previous: dict | None, current: dict, group_ids: list[str]) -> None:
    if previous is None:
        return
    if group_ids == ["DX6"]:
        if not current["diagnoses"]:
            raise ValueError("DX6 may not erase the WHO5 diagnosis state")
        if previous["icc_diagnoses"] and not current["icc_diagnoses"]:
            raise ValueError("DX6 may not silently erase a material ICC comparator")
    if group_ids == ["DX7"]:
        raise AssertionError("DX7 uses its own validator")


def _dx6_with_ids(dx6: dict) -> dict:
    return {
        "provisional_cmcs": dx6["provisional_cmcs"],
        "diagnoses": dx6["diagnoses"],
        "icc_diagnoses": dx6["icc_diagnoses"],
        "facts": [dict(row, fact_id=f"DX6-F{i}") for i, row in enumerate(dx6["facts"], 1)],
        "uncertainties": [dict(row, uncertainty_id=f"DX6-U{i}") for i, row in enumerate(dx6["uncertainties"], 1)],
    }


def _validate_dx7(doc: dict, dx6: dict) -> None:
    required = {"provisional_cmcs", "diagnoses", "icc_diagnoses", "supporting_facts", "uncertainties"}
    if set(doc) != required:
        raise ValueError(f"DX7 keys must be exactly {sorted(required)}; got {sorted(doc)}")
    for key in ("provisional_cmcs", "diagnoses", "icc_diagnoses"):
        if doc[key] != dx6[key]:
            raise ValueError(f"DX7 must preserve {key} exactly from DX6")
    fact_ids = {row["fact_id"] for row in dx6["facts"]}
    uncertainty_ids = {row["uncertainty_id"] for row in dx6["uncertainties"]}
    all_ids = fact_ids | uncertainty_ids
    if not isinstance(doc["supporting_facts"], list):
        raise ValueError("DX7 supporting_facts must be a list")
    for row in doc["supporting_facts"]:
        if not isinstance(row, dict) or set(row) != {"fact", "reason", "source_fact_ids"}:
            raise ValueError("each DX7 supporting fact requires fact, reason, source_fact_ids")
        ids = row["source_fact_ids"]
        if not isinstance(ids, list) or not ids or any(x not in fact_ids for x in ids):
            raise ValueError(f"DX7 supporting fact has invalid source_fact_ids: {ids!r}")
    if not isinstance(doc["uncertainties"], list):
        raise ValueError("DX7 uncertainties must be a list")
    seen_uncertainty_sources = set()
    for row in doc["uncertainties"]:
        if not isinstance(row, dict) or set(row) != {"uncertainty", "reason", "source_ids"}:
            raise ValueError("each DX7 uncertainty requires uncertainty, reason, source_ids")
        ids = row["source_ids"]
        if not isinstance(ids, list) or not ids or any(x not in all_ids for x in ids):
            raise ValueError(f"DX7 uncertainty has invalid source_ids: {ids!r}")
        seen_uncertainty_sources.update(x for x in ids if x in uncertainty_ids)
    # Deletion-resistant uncertainty invariant: each explicit DX6 uncertainty must survive mapping.
    missing = sorted(uncertainty_ids - seen_uncertainty_sources)
    if missing:
        raise ValueError(f"DX7 silently dropped material DX6 uncertainty source(s): {', '.join(missing)}")
    # Conservative lexical guard for technical numbers: a DX7 fact cannot introduce a new numeric token.
    dx6_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(dx6, ensure_ascii=False)))
    dx7_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(doc, ensure_ascii=False)))
    extra = sorted(dx7_numbers - dx6_numbers)
    if extra:
        raise ValueError(f"DX7 introduced numeric token(s) absent from DX6: {', '.join(extra)}")


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
    is_dx7: bool,
) -> None:
    """Persist a human-auditable view plus the exact API payload for one model call."""
    metadata = {
        "call_index": index,
        "question_ids": group_ids,
        "question_group": _group_label(group_ids),
        "is_dx7_synthesis": is_dx7,
        "case_notes_supplied": True,
        "evidence_cards_supplied": not is_dx7,
        "prior_terrace_transcript_supplied": bool(transcript) and not is_dx7,
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
        f"- Diagnosis/germline evidence cards supplied: {'no' if is_dx7 else 'yes'}",
        f"- Prior terrace transcript supplied: {'yes' if (transcript and not is_dx7) else 'no'}",
        f"- Previous validated state supplied: {'yes' if previous_state is not None else 'no'}",
        "- Exact payload sent to the API: `INPUT_messages.json`",
        "- Raw model response: `OUTPUT_raw.txt`",
        "- Accepted validated state: `OUTPUT_state.yaml`",
        "- Validation result: `OUTPUT_validation.json`",
        "",
    ]
    if is_dx7:
        overview.extend(
            [
                "DX7 is deliberately card-free. It receives the original case notes and the protected DX6 state,",
                "but it receives neither diagnosis cards nor the earlier DX1-DX5 transcript.",
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
    elif is_dx7:
        _write_yaml(call_dir / "INPUT_previous_state.yaml", _dx6_with_ids(previous_state))
    else:
        _write_yaml(call_dir / "INPUT_previous_state.yaml", previous_state)

    (call_dir / "INPUT_prior_transcript.json").write_text(
        json.dumps([] if is_dx7 else transcript, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not is_dx7:
        (call_dir / "INPUT_evidence_cards.json").write_text(
            json.dumps(cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def _write_validation(call_dir: Path, *, passed: bool, validator: str, error: str | None = None) -> None:
    payload = {"passed": passed, "validator": validator}
    if error is not None:
        payload["error"] = error
    (call_dir / "OUTPUT_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_one(args, example: int) -> Path:
    qcfg = _load_questions()
    profile = qcfg["execution_profiles"].get(args.profile)
    if not profile:
        raise ValueError(f"unknown profile {args.profile!r}")
    groups = profile["groups"]
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
        is_dx7 = group_ids == ["DX7"]
        questions_text = _questions_message(qcfg, group_ids)
        if is_dx7:
            if previous_state is None:
                raise ValueError("DX7 requires a DX6 state")
            dx6 = _dx6_with_ids(previous_state)
            messages = [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": DX7_PROMPT.read_text(encoding="utf-8")
                    + "\n\n# Original case notes\n"
                    + fixture["case_notes"].rstrip()
                    + "\n\n# Protected DX6 state with source IDs\n```yaml\n"
                    + yaml.safe_dump(dx6, sort_keys=False, allow_unicode=True, width=100).rstrip()
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
            is_dx7=is_dx7,
        )

        if args.dry_run:
            (call_dir / "OUTPUT_not_run.txt").write_text(
                "Dry-run: no model was called. Later model-call inputs are state-dependent and therefore were not fabricated.\n",
                encoding="utf-8",
            )
            completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "dry-run"})
            break

        try:
            raw = complete(provider, messages)
        except Exception as exc:
            (call_dir / "OUTPUT_api_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
            completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "api_error"})
            raise

        (call_dir / "OUTPUT_raw.txt").write_text(raw, encoding="utf-8")
        try:
            doc = _parse_yaml(raw)
            if is_dx7:
                _validate_dx7(doc, _dx6_with_ids(previous_state))
                validator = "dx7_fidelity_validator"
            else:
                _validate_state(doc, group_ids)
                _validate_transition(previous_state, doc, group_ids)
                validator = "diagnosis_state_and_transition_validator"
        except Exception as exc:
            _write_validation(call_dir, passed=False, validator="diagnosis_lab", error=str(exc))
            completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "validation_failed"})
            raise

        rendered = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
        (call_dir / "OUTPUT_state.yaml").write_text(rendered, encoding="utf-8")
        _write_validation(call_dir, passed=True, validator=validator)
        completed_calls.append({"call_index": index, "question_ids": group_ids, "status": "accepted"})
        final_doc = doc

        if not is_dx7:
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
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="write the exact first API payload without calling a model")
    args = parser.parse_args()

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
