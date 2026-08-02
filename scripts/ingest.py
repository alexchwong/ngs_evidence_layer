#!/usr/bin/env python3
"""Bounded orchestration for portable ingestion phases and corpus incorporation.

Usage:
  ingest.py pre-phase1|pre-phase2|pre-phase3 [--input-root input/<corpus>]
  ingest.py validate-phase1|validate-phase2|validate-phase3 --response FILE
  ingest.py pre-phase2-rework --id INPUT_ID
  ingest.py validate-phase2-rework --id INPUT_ID --response FILE
  ingest.py incorporate --after-phase 2|3 [--input-root input/<corpus>]

Read INGEST.md before using this command. Pre-phase jobs prepare and verify
model-authored artefacts; they do not perform model extraction themselves.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import next_paper  # noqa: E402
import validate_cards  # noqa: E402

PACKAGE_SCHEMA = ROOT / "schema" / "ingestion_package_schema.json"
PHASE_NUMBERS = (1, 2, 3)


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path, document):
    atomic_write(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def validate_schema(document, schema_path, label):
    schema = read_json(schema_path, "schema")
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        messages = []
        for error in errors:
            location = "/".join(str(part) for part in error.absolute_path) or "<root>"
            messages.append(f"{label} schema: {location}: {error.message}")
        raise ValueError("\n".join(messages))


def validate_census_document(census):
    """Validate one census document and return it unchanged."""
    validate_schema(census, ROOT / "schema" / "census_schema.json", "census")
    entry_ids = [entry["entry_id"] for entry in census["entries"]]
    genes = [entry["gene"] for entry in census["entries"]]
    if len(entry_ids) != len(set(entry_ids)):
        raise ValueError("census contains duplicate entry_id values")
    if len(genes) != len(set(genes)):
        raise ValueError("census contains duplicate gene entries")
    return census


def portable_paths(args, paths, phase_number):
    """Paths for one portable model handoff and its accepted stable artefact."""
    return next_paper.phase_handoff_paths(paths, phase_number, args.exchange_root)


def portable_phase(args, paths):
    for number in PHASE_NUMBERS:
        if not portable_paths(args, paths, number)["accepted"].is_file():
            return number
    return None


def select_portable(args, required_phase=None):
    input_root = next_paper.resolve_input_root(args.input_root, args.input_dir)
    records = next_paper.load_index(input_root / "index" / "papers.jsonl")
    if args.requested_id and not any(record["id"] == args.requested_id for record in records):
        raise ValueError(f"input id not found: {args.requested_id}")
    for record in records:
        if args.requested_id and record["id"] != args.requested_id:
            continue
        paths = next_paper.portable_paths_for(record, input_root, args.output_root)
        if not paths["markdown"].is_file():
            raise ValueError(f"indexed Markdown not found: {paths['markdown']}")
        phase_number = portable_phase(args, paths)
        if required_phase is None or phase_number == required_phase:
            return input_root, record, paths, phase_number
        if args.requested_id:
            raise ValueError(
                f"{record['id']} is due for Phase {phase_number or 'complete'}, "
                f"not Phase {required_phase}"
            )
    return input_root, None, None, None


def package_as_build_views(package):
    """Create private schema-v2 documents consumed by validators and the builder."""
    cards = {
        key: package[key]
        for key in (
            "publication_key", "citation", "publication_type", "extraction_date",
            "extraction_model", "genes_covered", "diseases_covered", "census_entries", "cards",
        )
    }
    cards["schema_version"] = "2.0"
    quotes = {
        "schema_version": "2.0",
        "publication_key": package["publication_key"],
        "extraction_date": package["extraction_date"],
        "extraction_model": package["extraction_model"],
        "quotes": package["quotes"],
    }
    return cards, quotes


def validate_package(
    document, census_path, source_path, expected_audited, phase2=None,
    allow_failed_audit=False,
):
    validate_schema(document, PACKAGE_SCHEMA, "ingestion package")
    if document["audited"] is not expected_audited:
        raise ValueError(f"package audited must be {str(expected_audited).lower()}")
    cards, quotes = package_as_build_views(document)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        cards_path = temporary / "cards.json"
        quotes_path = temporary / "quotes.json"
        atomic_write_json(cards_path, cards)
        atomic_write_json(quotes_path, quotes)
        _cards, errors, warnings, report = validate_cards.validate(
            cards_path, quotes_path, census_path, source_path
        )
    if errors:
        raise ValueError("package validation failed:\n" + "\n".join(errors))

    if expected_audited:
        immutable = dict(document)
        immutable["audited"] = False
        immutable["audit"] = None
        if immutable != phase2:
            raise ValueError("Phase 3 changed extraction content; only audited and audit may change")
        audit = document["audit"]
        if audit["audit_model"] == document["extraction_model"]:
            raise ValueError("audit model must differ from extraction model")
        if audit["extraction_model_reviewed"] != document["extraction_model"]:
            raise ValueError("extraction_model_reviewed does not match extraction_model")
        expected = [card["card_id"] for card in document["cards"]]
        results = audit["results"]
        seen = [result["card_id"] for result in results]
        if len(seen) != len(set(seen)):
            raise ValueError("audit contains duplicate card verdicts")
        unknown = sorted(set(seen) - set(expected))
        missing = sorted(set(expected) - set(seen))
        if unknown:
            raise ValueError(f"audit has verdicts for unknown cards: {', '.join(unknown)}")
        if missing:
            raise ValueError(f"audit lacks verdicts for cards: {', '.join(missing)}")
        failed = [result["card_id"] for result in results if result["verdict"] == "fail"]
        if failed and not allow_failed_audit:
            raise ValueError(f"failed cards block acceptance: {', '.join(failed)}")
    return warnings, report


def select_rework_publication(args):
    """Select one explicit publication even though Phase 2 is already accepted."""
    if not args.requested_id:
        raise ValueError("--id is required for Phase 2 rework")
    input_root = next_paper.resolve_input_root(args.input_root, args.input_dir)
    records = next_paper.load_index(input_root / "index" / "papers.jsonl")
    for record in records:
        if record["id"] != args.requested_id:
            continue
        paths = next_paper.portable_paths_for(record, input_root, args.output_root)
        if not paths["markdown"].is_file():
            raise ValueError(f"indexed Markdown not found: {paths['markdown']}")
        return input_root, record, paths
    raise ValueError(f"input id not found: {args.requested_id}")


def rework_round_paths(args, paths):
    """Return the pending rework round, or allocate the next numbered round."""
    root = Path(args.exchange_root) / "ingest" / "phase2" / "rework" / paths["stem"]
    rounds = sorted(path for path in root.glob("round-*") if path.is_dir())
    if rounds:
        latest = rounds[-1]
        archive = latest / "archive" / f"{paths['stem']}.phase2-rework.json"
        if not archive.exists():
            round_root = latest
        else:
            round_root = root / f"round-{len(rounds) + 1:03d}"
    else:
        round_root = root / "round-001"
    return {
        "root": round_root,
        "source": round_root / "outbox" / paths["markdown"].name,
        "context": round_root / "outbox" / f"{paths['stem']}.phase2-rework-context.md",
        "inbox": round_root / "inbox" / f"{paths['stem']}.phase2-rework.json",
        "archive": round_root / "archive" / f"{paths['stem']}.phase2-rework.json",
        "superseded": round_root / "archive" / f"{paths['stem']}.phase2.superseded.json",
        "failed_audit": round_root / "archive" / f"{paths['stem']}.phase3.failed.json",
    }


def validate_failed_audit_for_rework(args, record, paths):
    """Validate a Phase 3 response as an actionable failure, not as acceptance."""
    phase1_path = portable_paths(args, paths, 1)["accepted"]
    phase2_path = portable_paths(args, paths, 2)["accepted"]
    phase3_path = portable_paths(args, paths, 3)["accepted"]
    failed_response = portable_paths(args, paths, 3)["inbox"]
    if not phase1_path.is_file() or not phase2_path.is_file():
        raise ValueError("accepted Phase 1 and Phase 2 outputs are required for rework")
    if phase3_path.exists():
        raise ValueError("accepted Phase 3 output exists; accepted audits cannot enter rework")
    if not failed_response.is_file():
        raise ValueError(f"failed Phase 3 response is required at {failed_response}")
    phase2 = read_json(phase2_path, "accepted Phase 2 package")
    audit_response = read_json(failed_response, "failed Phase 3 response")
    validate_package(
        audit_response, phase1_path, paths["markdown"], True, phase2,
        allow_failed_audit=True,
    )
    failed = [
        result for result in audit_response["audit"]["results"]
        if result["verdict"] == "fail"
    ]
    if not failed:
        raise ValueError("Phase 3 response has no failed cards; use normal Phase 3 acceptance")
    return phase2, audit_response, failed_response, failed


def validate_phase2_rework_document(args, paths, document, superseded):
    """Apply normal Phase 2 checks plus rework identity invariants."""
    phase1_path = portable_paths(args, paths, 1)["accepted"]
    warnings, report = validate_package(
        document, phase1_path, paths["markdown"], False
    )
    immutable_fields = (
        "schema_version", "publication_key", "citation", "publication_type", "census_entries",
    )
    changed = [field for field in immutable_fields if document[field] != superseded[field]]
    if changed:
        raise ValueError(
            "Phase 2 rework changed immutable publication fields: " + ", ".join(changed)
        )
    return warnings, report


def validate_portable_response(args, phase_number, response_path, record, paths):
    response_path = Path(response_path)
    if phase_number == 1:
        document = read_json(response_path, "Phase 1 response")
        validate_census_document(document)
        if document["source_stem"] != paths["stem"]:
            raise ValueError("census source_stem does not match the selected publication")
        return document, [], None

    phase1_path = portable_paths(args, paths, 1)["accepted"]
    if not phase1_path.is_file():
        raise ValueError("accepted Phase 1 output is required")
    document = read_json(response_path, f"Phase {phase_number} response")
    phase2 = None
    if phase_number == 3:
        phase2_path = portable_paths(args, paths, 2)["accepted"]
        if not phase2_path.is_file():
            raise ValueError("accepted Phase 2 output is required")
        phase2 = read_json(phase2_path, "accepted Phase 2 package")
    warnings, report = validate_package(
        document, phase1_path, paths["markdown"], phase_number == 3, phase2
    )
    return document, warnings, report


def promote_portable(args, phase_number, document, handoff, paths):
    if handoff["archive"].exists():
        raise ValueError(f"archive destination already exists: {handoff['archive']}")
    atomic_write_json(handoff["accepted"], document)
    handoff["archive"].parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(handoff["inbox"]), str(handoff["archive"]))


def context_section(title, path, language="text"):
    content = Path(path).read_text(encoding="utf-8").rstrip()
    return f"## {title}\n\n```{language}\n{content}\n```\n\n"


def skill_phase_instruction(start_marker, end_marker):
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    try:
        start = text.index(start_marker)
        end = text.index(end_marker, start)
    except ValueError as exc:
        raise ValueError(f"SKILL.md lacks bounded instruction {start_marker!r}") from exc
    return text[start:end].strip() + "\n"


def completion_contract(args, phase_number, record, handoff):
    common = (
        "## Output, deterministic validation, and stop condition\n\n"
        f"Return one JSON object only, named `{handoff['inbox'].name}`. Do not wrap it "
        "in Markdown. Save an external chat response unchanged at "
        f"`{handoff['inbox']}`.\n\n"
        "Model-authored JSON does not complete this phase. If you can run repository "
        "commands, validate your draft with:\n\n"
        "```bash\n"
        ". .env/bin/activate\n"
        f"python scripts/ingest.py validate-phase{phase_number} --id {record['id']} "
        f"--response {handoff['inbox']}\n"
        "```\n\n"
        "After placing the response in the inbox, accept it with:\n\n"
        "```bash\n"
        ". .env/bin/activate\n"
        f"python scripts/ingest.py pre-phase{phase_number} --id {record['id']}\n"
        "```\n\n"
        f"Do not report Phase {phase_number} complete unless that command prints "
        f"`PHASE {phase_number} COMPLETE — VALIDATION PASS`. If you cannot execute it, "
        f"return JSON only; the status is `Phase {phase_number} response authored; "
        "deterministic validation pending`. Never begin the next phase.\n\n"
    )
    return common


def render_phase_context(args, phase_number, record, paths, handoff):
    header = (
        f"# Portable ingestion context — Phase {phase_number}\n\n"
        "Use this context and the separately supplied source Markdown only. Process "
        "exactly this publication. Do not use model knowledge to add facts absent from "
        "the source.\n\n"
        f"- Input ID: `{record['id']}`\n"
        f"- Source Markdown: `{paths['markdown'].name}`\n"
        f"- Required response: `{handoff['inbox'].name}`\n\n"
    )
    if phase_number == 1:
        instruction = skill_phase_instruction("# Phase 1 — Census", "# Phase 2 — Carding")
        body = (
            "## Task\n\nWalk the paper once from top to bottom, including intact tables "
            "and footnotes. Record every claimed-about gene and category, geneless "
            "rule-relevant statements, and missing supplementary values.\n\n"
            + "## Complete Phase 1 instruction\n\n" + instruction + "\n"
            + context_section("Reporting rules", ROOT / "rules" / "agreed_reporting_rules.md")
            + context_section("Required census schema", ROOT / "schema" / "census_schema.json", "json")
            + "## Selected index record\n\n```json\n"
            + json.dumps(record, indent=2, ensure_ascii=False) + "\n```\n\n"
        )
    elif phase_number == 2:
        census = portable_paths(args, paths, 1)["accepted"]
        instruction = skill_phase_instruction("# Phase 2 — Carding", "# Phase 3 — Audit")
        body = (
            "## Task\n\nWalk every census gene/category pair. Author supported evidence "
            "cards and exactly one minimal verbatim quote per card. Then perform the "
            "mandatory Phase 2 self-audit over every card using the exact Phase 3 "
            "quote-support and independent-utility questions. Repair every internal "
            "failure and rerun the audit over the entire package until all cards pass "
            "internally. The response must set `audited` to `false` and `audit` to "
            "`null`; internal self-audit is not independent Phase 3 audit.\n\n"
            + "## Complete Phase 2 instruction\n\n" + instruction + "\n"
            + context_section("Reporting rules", ROOT / "rules" / "agreed_reporting_rules.md")
            + context_section("Disease vocabulary", ROOT / "schema" / "disease_vocabulary.json", "json")
            + context_section("Shared Phase 2/3 package schema", PACKAGE_SCHEMA, "json")
            + context_section("Accepted Phase 1 census", census, "json")
        )
    else:
        package = portable_paths(args, paths, 2)["accepted"]
        body = (
            "## Task\n\nAudit two questions per card: is the interpretation supported by "
            "its quote in this source, and is the card independently useful rather than "
            "redundant within the package? Do not improve or rewrite extraction content. "
            "Return the complete package unchanged except set `audited` to `true` and "
            "replace `audit` with complete independent audit metadata and one verdict "
            "per card. Failed cards block acceptance.\n\n"
            + "## Audit instruction\n\n" + portable_audit_instruction() + "\n"
            + context_section("Accepted Phase 2 package", package, "json")
        )
    return header + body + completion_contract(args, phase_number, record, handoff)


def pre_phase(args, phase_number):
    _input_root, record, paths, _phase = select_portable(args, phase_number)
    if record is None:
        print(f"No publication due for Phase {phase_number}. STOP: no files changed.")
        return
    handoff = portable_paths(args, paths, phase_number)
    for area in ("context", "inbox", "archive"):
        handoff[area].parent.mkdir(parents=True, exist_ok=True)
    if handoff["inbox"].is_file():
        document, warnings, report = validate_portable_response(
            args, phase_number, handoff["inbox"], record, paths
        )
        for warning in warnings:
            print(f"warning: {warning}")
        promote_portable(args, phase_number, document, handoff, paths)
        print(f"PHASE {phase_number} COMPLETE — VALIDATION PASS")
        print(f"Accepted output: {handoff['accepted']}")
        if report:
            print(f"Cards:          {report['cards']}")
            print(f"Census ratio:   {report['ratio']}")
        print("STOP: the next phase was not prepared or started.")
        return
    context = render_phase_context(args, phase_number, record, paths, handoff)
    atomic_write(
        handoff["source"], paths["markdown"].read_text(encoding="utf-8")
    )
    atomic_write(handoff["context"], context)
    print(f"READY FOR PHASE {phase_number} MODEL WORK")
    print(f"Upload source:  {handoff['source']}")
    print(f"Upload context: {handoff['context']}")
    print(f"Save response:  {handoff['inbox']}")
    print(f"Phase {phase_number} response authored; deterministic validation pending.")


def validate_phase_response(args, phase_number):
    _input_root, record, paths, _phase = select_portable(args)
    if record is None:
        raise ValueError("no pending portable ingestion publication")
    _document, warnings, report = validate_portable_response(
        args, phase_number, args.response, record, paths
    )
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"PHASE {phase_number} RESPONSE VALID — not yet accepted")
    if report:
        print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")


def render_phase2_rework_context(args, record, paths, handoff, phase2, audit_response):
    """Render a complete corrective Phase 2 handoff from a valid failed audit."""
    instruction = skill_phase_instruction("# Phase 2 — Carding", "# Phase 3 — Audit")
    census = portable_paths(args, paths, 1)["accepted"]
    return (
        "# Portable ingestion context — Phase 2 rework\n\n"
        "Use this context and the separately supplied source Markdown only. Process "
        "exactly this publication. Do not use model knowledge to add facts absent from "
        "the source.\n\n"
        f"- Input ID: `{record['id']}`\n"
        f"- Source Markdown: `{paths['markdown'].name}`\n"
        f"- Required response: `{handoff['inbox'].name}`\n\n"
        "## Task\n\nThe independent Phase 3 audit below found unsupported or redundant "
        "cards. Treat each failed verdict as a defect report, verify it against the source, "
        "and repair the extraction by rewriting, requoting, merging, or deleting cards as "
        "needed. Return the complete corrected package, not a patch or only the failed cards. "
        "Set `audited` to `false` and `audit` to `null`. Preserve publication identity. The "
        "complete corrected package will receive a fresh independent Phase 3 audit.\n\n"
        "Do not blindly follow a suggested correction: the source remains authoritative. "
        "The failed verdicts identify known defects but are not the limit of review. After "
        "repairing them, perform the mandatory Phase 2 self-audit over every card using the "
        "exact Phase 3 quote-support and independent-utility questions. Repair and rerun the "
        "audit over the entire package until all cards pass internally.\n\n"
        "## Complete Phase 2 instruction\n\n" + instruction + "\n"
        + context_section("Reporting rules", ROOT / "rules" / "agreed_reporting_rules.md")
        + context_section("Disease vocabulary", ROOT / "schema" / "disease_vocabulary.json", "json")
        + context_section("Shared Phase 2/3 package schema", PACKAGE_SCHEMA, "json")
        + context_section("Accepted Phase 1 census", census, "json")
        + "## Superseded accepted Phase 2 package\n\n```json\n"
        + json.dumps(phase2, indent=2, ensure_ascii=False) + "\n```\n\n"
        + "## Failed independent Phase 3 audit\n\n```json\n"
        + json.dumps(audit_response, indent=2, ensure_ascii=False) + "\n```\n\n"
        + "## Output, deterministic validation, and stop condition\n\n"
        f"Return one JSON object only, named `{handoff['inbox'].name}`. Do not wrap it "
        "in Markdown. Save an external chat response unchanged at "
        f"`{handoff['inbox']}`.\n\n"
        "Validate the draft with:\n\n```bash\n. .env/bin/activate\n"
        f"python scripts/ingest.py validate-phase2-rework --id {record['id']} "
        f"--response {handoff['inbox']}\n```\n\n"
        "Accept the corrected package with:\n\n```bash\n. .env/bin/activate\n"
        f"python scripts/ingest.py pre-phase2-rework --id {record['id']}\n```\n\n"
        "Do not report rework complete unless that command prints "
        "`PHASE 2 REWORK COMPLETE — VALIDATION PASS`. Never begin Phase 3 automatically.\n"
    )


def validate_phase2_rework_response(args):
    _input_root, record, paths = select_rework_publication(args)
    superseded, _audit, _failed_response, _failed = validate_failed_audit_for_rework(
        args, record, paths
    )
    document = read_json(args.response, "Phase 2 rework response")
    warnings, report = validate_phase2_rework_document(args, paths, document, superseded)
    for warning in warnings:
        print(f"warning: {warning}")
    print("PHASE 2 REWORK RESPONSE VALID — not yet accepted")
    print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")


def invalidate_derived_outputs(args, paths):
    """Remove artefacts derived from the superseded active Phase 2 package."""
    phase3 = portable_paths(args, paths, 3)
    for key in ("context", "source"):
        phase3[key].unlink(missing_ok=True)
    corpus_dir = args.output_root / "corpus"
    if corpus_dir.exists():
        shutil.rmtree(corpus_dir)
    report = args.output_root / "reports" / "build-report.json"
    report.unlink(missing_ok=True)


def pre_phase2_rework(args):
    _input_root, record, paths = select_rework_publication(args)
    superseded, audit_response, failed_response, failed = validate_failed_audit_for_rework(
        args, record, paths
    )
    handoff = rework_round_paths(args, paths)
    for key in ("context", "inbox", "archive"):
        handoff[key].parent.mkdir(parents=True, exist_ok=True)

    if handoff["inbox"].is_file():
        document = read_json(handoff["inbox"], "Phase 2 rework response")
        warnings, report = validate_phase2_rework_document(args, paths, document, superseded)
        for warning in warnings:
            print(f"warning: {warning}")
        for destination in (handoff["archive"], handoff["superseded"], handoff["failed_audit"]):
            if destination.exists():
                raise ValueError(f"rework archive destination already exists: {destination}")
        handoff["archive"].parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(handoff["superseded"], superseded)
        atomic_write_json(portable_paths(args, paths, 2)["accepted"], document)
        shutil.move(str(failed_response), str(handoff["failed_audit"]))
        shutil.move(str(handoff["inbox"]), str(handoff["archive"]))
        invalidate_derived_outputs(args, paths)
        print("PHASE 2 REWORK COMPLETE — VALIDATION PASS")
        print(f"Accepted output: {portable_paths(args, paths, 2)['accepted']}")
        print(f"Failed cards addressed: {len(failed)}")
        print(f"Cards:          {report['cards']}")
        print(f"Census ratio:   {report['ratio']}")
        print("STOP: run a fresh Phase 3 audit; none was started automatically.")
        return

    context = render_phase2_rework_context(
        args, record, paths, handoff, superseded, audit_response
    )
    atomic_write(handoff["source"], paths["markdown"].read_text(encoding="utf-8"))
    atomic_write(handoff["context"], context)
    print("READY FOR PHASE 2 REWORK MODEL WORK")
    print(f"Failed cards:   {len(failed)}")
    print(f"Upload source:  {handoff['source']}")
    print(f"Upload context: {handoff['context']}")
    print(f"Save response:  {handoff['inbox']}")
    print("Phase 2 rework response authored; deterministic validation pending.")


def audit_instruction():
    lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    marker = "## Audit instruction — paste this verbatim into the audit session"
    try:
        start = lines.index(marker) + 1
    except ValueError as exc:
        raise ValueError("SKILL.md lacks the Phase 3 audit instruction") from exc
    quoted = []
    started = False
    for line in lines[start:]:
        if line.startswith(">"):
            started = True
            text = line[1:]
            quoted.append(text[1:] if text.startswith(" ") else text)
        elif started and not line.strip():
            continue
        elif started:
            break
    if not quoted:
        raise ValueError("SKILL.md Phase 3 audit instruction is empty")
    return "\n".join(quoted).strip() + "\n"


def portable_audit_instruction():
    """Return the unified Phase 3 instruction quoted in SKILL.md."""
    return audit_instruction()


def run_build(args, input_root, allow_unaudited=False):
    command = [
        sys.executable,
        str(SCRIPTS / "build_corpus.py"),
        "--input-index", str(input_root / "index" / "papers.jsonl"),
        "--markdown-dir", str(input_root / "markdown"),
        "--phase1-dir", str(args.output_root / "phase1"),
        "--package-dir", str(args.output_root / f"phase{args.after_phase}"),
        "--after-phase", str(args.after_phase),
        "--reports-dir", str(args.output_root / "reports"),
        "--output-dir", str(args.output_root / "corpus"),
        "--allow-incomplete",
    ]
    if allow_unaudited:
        command.append("--allow-unaudited")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip())
    return result.stdout.strip()


def incorporate(args):
    if args.after_phase is None:
        raise ValueError("--after-phase 2 or --after-phase 3 is required")
    input_root = next_paper.resolve_input_root(args.input_root, args.input_dir)
    records = next_paper.load_index(input_root / "index" / "papers.jsonl")
    incorporated = 0
    for record in records:
        if args.requested_id and record["id"] != args.requested_id:
            continue
        paths = next_paper.portable_paths_for(record, input_root, args.output_root)
        package_path = portable_paths(args, paths, args.after_phase)["accepted"]
        if not package_path.is_file():
            continue
        _document, warnings, _report = validate_portable_response(
            args, args.after_phase, package_path, record, paths
        )
        for warning in warnings:
            print(f"warning: {record['id']}: {warning}")
        incorporated += 1
    if not incorporated:
        raise ValueError(f"no accepted Phase {args.after_phase} packages found")
    build_output = run_build(args, input_root, allow_unaudited=args.after_phase == 2)
    corpus = read_json(args.output_root / "corpus" / "nel.corpus.json", "corpus")
    expected_provisional = args.after_phase == 2
    if corpus.get("provisional") is not expected_provisional:
        raise ValueError("corpus provisional status does not match incorporation phase")
    print(build_output)
    print("\nINCORPORATION COMPLETE")
    print(f"Accepted phase:       {args.after_phase}")
    print(f"Packages incorporated:{incorporated:>5}")
    print(f"Provisional corpus:   {str(corpus['provisional']).lower()}")
    print(f"Corpus:               {args.output_root / 'corpus' / 'nel.corpus.json'}")
    print("STOP: no further ingestion phase was started.")


def parser():
    result = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    result.add_argument(
        "job",
        choices=(
            "incorporate",
            "pre-phase1", "pre-phase2", "pre-phase3",
            "validate-phase1", "validate-phase2", "validate-phase3",
            "pre-phase2-rework", "validate-phase2-rework",
        ),
    )
    result.add_argument("--input-root", type=Path)
    result.add_argument("--input-dir", type=Path, default=Path("input"))
    result.add_argument("--output-root", type=Path, default=Path("output"))
    result.add_argument("--exchange-root", type=Path, default=Path("exchange"))
    result.add_argument("--id", dest="requested_id", help="select one indexed input ID")
    result.add_argument("--response", type=Path, help="response file for validate-phaseN")
    result.add_argument("--after-phase", type=int, choices=(2, 3))
    return result


def main():
    args = parser().parse_args()
    try:
        jobs = {
            "incorporate": incorporate,
            "pre-phase1": lambda value: pre_phase(value, 1),
            "pre-phase2": lambda value: pre_phase(value, 2),
            "pre-phase3": lambda value: pre_phase(value, 3),
            "pre-phase2-rework": pre_phase2_rework,
            "validate-phase1": lambda value: validate_phase_response(value, 1),
            "validate-phase2": lambda value: validate_phase_response(value, 2),
            "validate-phase3": lambda value: validate_phase_response(value, 3),
            "validate-phase2-rework": validate_phase2_rework_response,
        }
        if args.job.startswith("validate-") and args.response is None:
            raise ValueError("--response is required for validation jobs")
        jobs[args.job](args)
    except (OSError, ValueError) as exc:
        sys.exit(f"{args.job.upper()} FAILED:\n{exc}")


if __name__ == "__main__":
    main()