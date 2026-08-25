#!/usr/bin/env python3
"""Run the diagnosis terrace as a complete diagnosis-only terraced-v1 slice.

The head preserves case.md, structures it with terraced-v1, and initializes a
run-global identity for every corpus card.  Each diagnosis terrace then draws
cards deterministically from fixed genes + the last accepted CMC state + the
terrace category.  The tail aligns and renders the Diagnosis section, writes a
final report, and packages validation cases for external marking without
performing marking in-process.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflows.terraced_v1 import layout
from scripts.core import citations, corpus
from scripts.core import retrieval as core_retrieval
from scripts.setup_workflow import setup_workflow
from validation import cases as validation_cases
from validation.package_marking import package_marking_bundle
from workflows.terraced_v1 import rendering as terraced_rendering
from workflows.terraced_v1 import step as terraced_step
from workflows.terraced_v1 import card_identity
from workflows.terraced_v1.diagnosis_lab import connector
from workflows.terraced_v1.diagnosis_lab import run as lab

VALIDATION_MODES = {"nel-validate", "nel-validate-function", "nel-validate-brief"}
MODE_ALIASES = {
    "nel-validation": "nel-validate",
    "nel-validation-function": "nel-validate-function",
    "nel-validation-brief": "nel-validate-brief",
}
MARKING_PREFIX = {
    "nel-validate": "nel-validation",
    "nel-validate-function": "nel-validation-function",
    "nel-validate-brief": "nel-validation-brief",
}


class RunLog:
    def __init__(self, work: Path):
        self.started = time.monotonic()
        self.path = work / "workflow.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def status(self, message: str) -> None:
        elapsed = int(time.monotonic() - self.started)
        line = f"[ {elapsed:04d} ] - {message}"
        print(line)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _safe_slug(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "case"


def _timestamped_work_dir(root: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = root / f"diagnosis-{_safe_slug(label)}-{stamp}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = Path(f"{base}-{suffix}")
        suffix += 1
    return candidate


def _read_json_values(path: Path, *keys: str) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        return [str(x) for x in doc]
    if isinstance(doc, dict):
        for key in keys:
            value = doc.get(key)
            if isinstance(value, list):
                return [str(x) for x in value]
    raise ValueError(f"{path} does not contain an expected string list")


def _head_model_profile(args) -> str:
    """Choose a direct terraced-v1 profile for the production structure-case head.

    The registered terraced default is ``self`` (session handoff), which is not
    suitable inside this single-process diagnosis wrapper.  Match the diagnosis
    provider when it names a registered direct profile; generic endpoints must
    opt into an explicit terraced model profile.
    """
    if args.model_profile:
        return args.model_profile
    if args.provider in {"lmstudio", "openrouter"}:
        return args.provider
    raise ValueError(
        "--model-profile is required with --provider openai-compatible so the terraced-v1 "
        "structure-case head has a registered direct model binding"
    )


def _quiet_call(func, *args, **kwargs):
    """Run a noisy production helper while suppressing its CLI chatter.

    The diagnosis wrapper emits its own concise elapsed-time log and deliberately
    does not replay successful "validated" messages.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return func(*args, **kwargs)
    except Exception:
        # Preserve useful failures while still dropping success-only validation chatter.
        for stream in (stdout.getvalue(), stderr.getvalue()):
            for line in stream.splitlines():
                lowered = line.lower()
                if "validated" in lowered or "validation pass" in lowered:
                    continue
                print(line, file=sys.stderr)
        raise


def _prepare_case(args, work: Path, demo_case) -> None:
    case_path = layout.input(work, "case.md")
    case_path.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "ngs-report":
        if args.case_file is None:
            raise ValueError("--case-file case.md is required for mode ngs-report")
        shutil.copyfile(args.case_file, case_path)
    elif args.mode == "nel-demo":
        if demo_case is None:
            raise ValueError("nel-demo setup did not return a demonstration case")
        shutil.copyfile(Path(demo_case), case_path)
    elif args.mode in VALIDATION_MODES:
        if not case_path.is_file():
            raise ValueError(f"{args.mode} setup did not create {case_path}")
    else:
        raise ValueError(f"unsupported mode {args.mode!r}")
    if not case_path.read_text(encoding="utf-8").strip():
        raise ValueError("case.md is empty")


def _load_corpus_identity(work: Path) -> tuple[list[dict], list[dict], str, dict]:
    corpus_doc, _index, digest = corpus.load_corpus(corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX)
    all_cards = corpus.flatten(corpus_doc)
    manifest = card_identity.build_manifest(all_cards, corpus_sha256=digest)
    identity_path = layout.evidence(work, "card-identity-manifest.json")
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    eligible = corpus.blacklist_cards(all_cards, corpus.DEFAULT_BLACKLIST)
    connector.configure_runtime_card_tags(card_identity.runtime_tag_map(manifest))
    return all_cards, eligible, digest, manifest


def _draw_terrace_cards(
    eligible_cards: list[dict],
    *,
    genes: list[str],
    cmcs: list[str],
    terrace_category: str,
) -> list[dict]:
    """Deterministic terrace draw from fixed genes, evolving CMC and category.

    Only the diagnosis terrace is implemented now. Diagnosis cards are retained
    on gene OR CMC match. Gene-matched germline cards remain visible as
    supplementary diagnostic evidence by product design. Future terraces can
    add their category policy here without changing diagnosis state mechanics.
    """
    if terrace_category != "diagnosis":
        raise ValueError(f"unsupported terrace category {terrace_category!r}")
    gene_set = set(genes)
    hits = []
    for source in eligible_cards:
        matched_genes = core_retrieval.match_genes(source, gene_set)
        matched_cmcs = core_retrieval._matches_case_major_category(source, cmcs)
        category = source.get("category")
        if category == "diagnosis":
            if not matched_genes and not matched_cmcs:
                continue
        elif category == "germline":
            if not matched_genes:
                continue
        else:
            continue
        card = dict(source)
        card["matched_genes"] = matched_genes
        card["matched_case_major_categories"] = matched_cmcs
        hits.append(card)
    hits.sort(key=lambda row: row.get("card_id") or "")
    return hits


def _fixture_from_work(work: Path, *, corpus_digest: str) -> dict:
    # The production terraced-v1 Step-1b schema already matches the diagnosis
    # lab's structured-case contract: fixed genes plus initial provisional CMCs.
    # Preserve it byte-semantically rather than inventing a second translation.
    structured = json.loads(layout.input(work, "case-input.json").read_text(encoding="utf-8"))
    allowed_cmcs = _read_json_values(
        layout.input(work, "case-major-categories.json"),
        "case_major_categories",
        "allowed_case_major_categories",
        "values",
    )
    allowed_schema = _read_json_values(
        layout.input(work, "allowed-schema-diseases.json"),
        "allowed_schema_diseases",
        "schema_diseases",
        "values",
    )
    return {
        "case_notes": layout.input(work, "case.md").read_text(encoding="utf-8"),
        "structured_case": structured,
        "ngs_panel_scope": layout.input(work, "ngs-panel-scope.md").read_text(encoding="utf-8"),
        "allowed_provisional_cmcs": allowed_cmcs,
        "allowed_schema_diseases": allowed_schema,
        "corpus_digest": corpus_digest,
    }

def _draw_audit_row(index: int, group_ids: list[str], cmcs: list[str], cards: list[dict], tag_lookup: dict[str, str]) -> dict:
    return {
        "call_index": index,
        "question_ids": list(group_ids),
        "terrace_category": "diagnosis",
        "provisional_cmcs": list(cmcs),
        "card_count": len(cards),
        "cards": [
            {"card_id": card["card_id"], "card_tag": tag_lookup[card["card_id"]]}
            for card in cards
        ],
    }


def _run_diagnosis(
    args,
    diagnosis_dir: Path,
    fixture: dict,
    eligible_cards: list[dict],
    identity_manifest: dict,
    logger: RunLog,
) -> tuple[dict, list[dict], list[dict]]:
    qcfg = lab._load_questions()
    if args.profile not in qcfg["execution_profiles"]:
        raise ValueError(f"unknown diagnosis execution profile {args.profile!r}")
    groups = lab._question_plan(qcfg, args.profile)
    by_id = {row["id"]: row for row in qcfg["questions"]}
    provider = lab.config_for(
        args.provider,
        args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_s=args.timeout,
    )

    fixed_genes = list(fixture["structured_case"].get("genes") or [])
    active_cmcs = list(fixture["structured_case"].get("provisional_cmcs") or [])
    if not active_cmcs:
        raise ValueError("structured case must contain at least one provisional CMC")
    tag_lookup = card_identity.tag_by_id(identity_manifest)
    seen_cards: dict[str, dict] = {}
    draw_audit = []
    transcript: list[dict[str, str]] = []
    previous_state = None
    final_doc = None

    for index, group_ids in enumerate(groups, 1):
        rows = [by_id[qid] for qid in group_ids]
        kinds = {row["kind"] for row in rows}
        if len(kinds) != 1:
            raise ValueError(f"question group {group_ids!r} mixes terrace and final kinds")
        is_final = "final" in kinds
        final_config = rows[0] if is_final else None
        questions_text = lab._questions_message(qcfg, group_ids)

        if is_final:
            cards: list[dict] = []
            if previous_state is None:
                raise ValueError("the configured final question requires a validated pre-final terrace state")
            reviewed = lab._reviewed_with_ids(previous_state)
            messages = [
                {"role": "system", "content": lab.SYSTEM},
                {
                    "role": "user",
                    "content": lab._final_prompt(final_config)
                    + "\n\n# Original case notes\n"
                    + fixture["case_notes"].rstrip()
                    + "\n\n# Protected pre-final state with source IDs\n```yaml\n"
                    + yaml.safe_dump(reviewed, sort_keys=False, allow_unicode=True, width=100).rstrip()
                    + "\n```\n\n"
                    + questions_text,
                },
            ]
            logger.status(f"Diagnosis final synthesis: answering")
        else:
            # Crucially, this happens at the START of every terrace.  CMC changes
            # accepted by the prior terrace affect this draw, with no same-terrace repeat.
            cards = _draw_terrace_cards(
                eligible_cards,
                genes=fixed_genes,
                cmcs=active_cmcs,
                terrace_category="diagnosis",
            )
            for card in cards:
                seen_cards.setdefault(card["card_id"], card)
            draw_audit.append(_draw_audit_row(index, group_ids, active_cmcs, cards, tag_lookup))
            logger.status(
                f"Diagnosis terrace {index}/{len(groups) - 1}: draw {len(cards)} cards for CMC "
                + " | ".join(active_cmcs)
            )
            messages = [
                {"role": "system", "content": lab.SYSTEM},
                {
                    "role": "user",
                    "content": lab.TERRACE_PROMPT.read_text(encoding="utf-8")
                    + "\n\n"
                    + lab._base_context(fixture, cards),
                },
                *transcript,
                {"role": "user", "content": questions_text},
            ]
            logger.status(f"Diagnosis terrace {index}/{len(groups) - 1}: answering")

        call_dir = lab._call_directory(diagnosis_dir, index, group_ids)
        lab._write_call_inputs(
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
        try:
            if is_final:
                validate = lambda doc: lab._validate_final(doc, lab._reviewed_with_ids(previous_state), final_config)
                validator_name = "final_fidelity_validator"
            else:
                validate = lambda doc: (lab._validate_state(doc, group_ids), lab._validate_transition(previous_state, doc))
                validator_name = "diagnosis_state_and_transition_validator"
            doc = lab._validated_model_call(
                call_dir,
                provider,
                messages=messages,
                parse=lab._parse_yaml,
                validate=validate,
                validator_name=validator_name,
                attempts=args.structural_attempts,
            )
        except Exception:
            logger.status(("Diagnosis final synthesis" if is_final else f"Diagnosis terrace {index}/{len(groups) - 1}") + ": failed")
            raise

        rendered = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
        (call_dir / "OUTPUT_state.yaml").write_text(rendered, encoding="utf-8")
        final_doc = doc
        if is_final:
            logger.status("Diagnosis final synthesis complete")
        else:
            logger.status(f"Diagnosis terrace {index}/{len(groups) - 1} complete")
            transcript.extend(
                [
                    {"role": "user", "content": questions_text},
                    {"role": "assistant", "content": rendered},
                ]
            )
            previous_state = doc
            active_cmcs = list(doc["provisional_cmcs"])

    if final_doc is None:
        raise ValueError("diagnosis workflow produced no final state")
    union_cards = [seen_cards[key] for key in sorted(seen_cards)]
    return final_doc, union_cards, draw_audit


def _render_evidence(
    work: Path,
    *,
    fixture: dict,
    final_doc: dict,
    cards: list[dict],
    identity_manifest: dict,
) -> tuple[Path, Path, list[dict]]:
    evidence_dir = layout.evidence(work, "evidence-diagnosis.md").parent
    evidence_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "workflow_profile": "terraced-v1",
        "terraced_domain": "diagnosis",
        "genes": list(fixture["structured_case"].get("genes") or []),
        "provisional_cmcs": list(final_doc.get("provisional_cmcs") or []),
        "accepted_schema_diseases": [row["schema_disease"] for row in final_doc.get("diagnoses") or []],
        "provenance": {
            "corpus_version": None,
            "corpus_sha256": fixture["corpus_digest"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "diagnostic_context": [],
        "retrieved": cards,
        "runtime_card_tags": card_identity.runtime_tag_map(identity_manifest),
    }
    bundle_path = evidence_dir / "diagnosis-bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    evidence_path = evidence_dir / "evidence-diagnosis.md"
    tag_path = evidence_dir / "card-tags.json"
    render_result = _quiet_call(
        terraced_rendering.render_to_files,
        bundle_path,
        output=evidence_path,
        card_tag_output=tag_path,
        retrieved_only=True,
    )
    # Alignment may cite only cards that survived deterministic evidence-budget
    # rendering, otherwise the final citation renderer could receive a tag with
    # no corresponding Refs mapping. Preserve original rich card objects.
    rendered_ids = {row["card_id"] for row in render_result.get("rendered_cards", [])}
    alignment_cards = [card for card in cards if card.get("card_id") in rendered_ids]
    return evidence_path, tag_path, alignment_cards


def _render_final_report(work: Path, diagnosis_dir: Path, evidence_path: Path, tag_path: Path) -> Path:
    internal = diagnosis_dir / "FINAL_REPORT.md"
    rendered = citations.render(
        internal.read_text(encoding="utf-8"),
        evidence_path.read_text(encoding="utf-8"),
        tag_path.read_text(encoding="utf-8"),
        require_citation_after_full_stop=False,
    )
    output = work / "report-final.md"
    output.write_text(rendered, encoding="utf-8")
    return output


def _package_marking_if_applicable(args, work: Path, report: Path) -> Path | None:
    if args.mode not in VALIDATION_MODES:
        return None
    case_file = validation_cases.VALIDATION_CASE_FILES[args.mode]
    output = work / f"{MARKING_PREFIX[args.mode]}-{args.case_id}.zip"
    package_marking_bundle(
        args.case_id,
        report,
        output,
        case_file=case_file,
    )
    return output


def _package_debug(work: Path) -> Path:
    output = work / "diagnosis-debug.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work.rglob("*")):
            if not path.is_file() or path == output or path.suffix == ".zip":
                continue
            archive.write(path, path.relative_to(work))
    return output


def _run(args) -> tuple[Path, Path, Path | None, Path]:
    args.mode = MODE_ALIASES.get(args.mode, args.mode)
    label = args.mode
    if args.mode == "ngs-report" and args.case_file:
        label += "-" + args.case_file.stem
    elif args.mode == "nel-demo":
        label += f"-{args.example}"
    elif args.case_id:
        label += f"-{args.case_id}"
    root = args.output_dir or (REPO_ROOT / "temp")
    work = _timestamped_work_dir(Path(root), label)

    demo_case = demo_expected = None
    work, demo_case, demo_expected = setup_workflow(
        workflow="terraced-v1",
        mode=args.mode,
        work_dir=work,
        project=True,
        example=args.example,
        case_id=args.case_id,
    )
    logger = RunLog(work)
    logger.status("Setup diagnosis-only terraced workflow")
    _prepare_case(args, work, demo_case)
    if demo_expected:
        expected_path = work / "demo-expected.md"
        shutil.copyfile(Path(demo_expected), expected_path)

    logger.status("Initialize deterministic identity for all corpus cards")
    all_cards, eligible_cards, corpus_digest, identity_manifest = _load_corpus_identity(work)
    logger.status(f"Corpus identity initialized: {len(all_cards)} cards, 12-hex tags")

    logger.status("Structure case: answering")
    _quiet_call(terraced_step.step_1b, work, _head_model_profile(args))
    logger.status("Structure case complete")
    fixture = _fixture_from_work(work, corpus_digest=corpus_digest)
    fixed_genes = list(fixture["structured_case"].get("genes") or [])
    logger.status("Fixed retrieval genes: " + (", ".join(fixed_genes) if fixed_genes else "none"))
    diagnosis_dir = work / "diagnosis"
    diagnosis_dir.mkdir(parents=True, exist_ok=True)

    final_doc, union_cards, draw_audit = _run_diagnosis(
        args,
        diagnosis_dir,
        fixture,
        eligible_cards,
        identity_manifest,
        logger,
    )
    (diagnosis_dir / "FINAL_OUTPUT.yaml").write_text(
        yaml.safe_dump(final_doc, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    evidence_dir = layout.evidence(work, "diagnosis-card-draws.json").parent
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "diagnosis-card-draws.json").write_text(
        json.dumps(draw_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (evidence_dir / "diagnosis-evidence.json").write_text(
        json.dumps(union_cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logger.status("Render diagnosis evidence")
    evidence_path, tag_path, alignment_cards = _render_evidence(
        work,
        fixture=fixture,
        final_doc=final_doc,
        cards=union_cards,
        identity_manifest=identity_manifest,
    )
    logger.status(f"Diagnosis evidence complete: {len(alignment_cards)}/{len(union_cards)} cards renderable")

    logger.status("Diagnosis report connector: answering")
    lab._run_report_connector(
        diagnosis_dir,
        lab.config_for(
            args.provider,
            args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_s=args.timeout,
        ),
        fixture,
        final_doc,
        alignment_cards,
        attempts=args.structural_attempts,
    )
    logger.status("Diagnosis report connector complete")

    logger.status("Render final diagnosis citations")
    report = _render_final_report(work, diagnosis_dir, evidence_path, tag_path)
    logger.status("report-final.md complete")

    marking = _package_marking_if_applicable(args, work, report)
    if marking:
        logger.status("External marking package complete; marking not performed")
    debug = _package_debug(work)
    logger.status("Diagnosis debug package complete")
    return work, report, marking, debug


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            "ngs-report",
            "nel-demo",
            "nel-validate",
            "nel-validate-function",
            "nel-validate-brief",
            "nel-validation",
            "nel-validation-function",
            "nel-validation-brief",
        ],
        default="ngs-report",
    )
    parser.add_argument("--case-file", type=Path, help="authoritative case.md; capture/rewrite is bypassed")
    parser.add_argument("--example", type=int, help="nel-demo example number")
    parser.add_argument("--case-id", help="validation case ID")
    parser.add_argument("--profile", choices=["frontier", "balanced", "deliberate"], default="balanced")
    parser.add_argument(
        "--model-profile",
        help=(
            "terraced-v1 direct model profile used only for the case-structure head; "
            "defaults to lmstudio/openrouter when that diagnosis provider is selected"
        ),
    )
    parser.add_argument("--provider", choices=["lmstudio", "openrouter", "openai-compatible"], default="lmstudio")
    parser.add_argument("--model", default="qwen3-coder-next")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--structural-attempts", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, help="parent directory; run name remains timestamp-based")
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    args.mode = MODE_ALIASES.get(args.mode, args.mode)
    if args.structural_attempts < 1:
        parser.error("--structural-attempts must be at least 1")
    if args.mode == "ngs-report" and args.case_file is None:
        parser.error("ngs-report requires --case-file case.md")
    if args.mode == "nel-demo" and args.example is None:
        parser.error("nel-demo requires --example N")
    if args.mode in VALIDATION_MODES and not args.case_id:
        parser.error(f"{args.mode} requires --case-id ID")
    try:
        work, report, marking, debug = _run(args)
    except Exception as exc:
        print(f"diagnosis workflow failed: {exc}", file=sys.stderr)
        return 1
    print(f"work_dir={work}")
    print(f"report={report}")
    if marking:
        print(f"marking_package={marking}")
    print(f"debug_package={debug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
