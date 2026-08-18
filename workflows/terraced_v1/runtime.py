"""Deterministic state, validation, evidence rendering and final rendering for terraced-v1."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
from scripts import vocab  # noqa: E402
from scripts.core import citations as report_citations  # noqa: E402
from workflows.terraced_v1 import rendering, retrieval  # noqa: E402

WORKFLOW_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = WORKFLOW_DIR / "questions.yaml"
QUESTIONS_TEMPLATE_PATH = WORKFLOW_DIR / "questions.yaml.template"
CARD_RE = re.compile(r"\[card:([0-9a-f]{6})\]")
CITATION_RE = re.compile(r"(?:\[card:[0-9a-f]{6}\])+")
DOMAINS = ("diagnosis", "prognosis", "treatment", "mrd", "germline")
WHO5_EXCLUDED_SCHEMA_DISEASES = {"MDS/AML"}


def _validation_case_text(mode: str, case_id: str) -> str:
    repo_text = str(REPO_ROOT)
    inserted = repo_text not in sys.path
    if inserted:
        sys.path.insert(0, repo_text)
    try:
        from validation.cases import retrieve_case
        case_file = "case_functional.md" if mode == "nel-validate-function" else "case_summary.md"
        return retrieve_case(case_id, case_file)
    finally:
        if inserted and sys.path and sys.path[0] == repo_text:
            sys.path.pop(0)


def _write_case_if_absent(work: Path, text: str) -> None:
    path = work / "case.md"
    payload = text.rstrip() + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError(f"{path} exists with different validation case content")
    if not path.exists():
        path.write_text(payload, encoding="utf-8")


def setup_assets(work_dir: Path, *, mode: str, case_id: str | None = None) -> None:
    work = Path(work_dir)
    # Terraced diagnosis may provisionally entertain multiple broad disease families.
    (work / "case-major-categories.json").write_text(
        json.dumps({
            "case_major_categories": list(vocab.CASE_MAJOR_CATEGORIES),
            "instruction": (
                "Select one or more provisional case-major categories representing the supplied starting "
                "clinicopathological disease family or families. These are retrieval scaffolds, not final diagnoses."
            ),
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if mode in {"nel-validate", "nel-validate-function"}:
        if not case_id:
            raise ValueError(f"{mode} requires a validation case ID")
        _write_case_if_absent(work, _validation_case_text(mode, case_id))
    questions_source = QUESTIONS_PATH if QUESTIONS_PATH.is_file() else QUESTIONS_TEMPLATE_PATH
    shutil.copyfile(questions_source, work / "terraced-config.yaml")
    allowed = [d for d in vocab.CASE_DISEASES if d not in WHO5_EXCLUDED_SCHEMA_DISEASES]
    (work / "allowed-schema-diseases.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allowed_schema_diseases": allowed,
                "instruction": (
                    "Use an exact value as schema_disease for final routing. WHO5 is authoritative; "
                    "MDS/AML is excluded because it is an ICC category, not the final WHO5 diagnosis."
                ),
            }, indent=2, ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )


def load_questions(work: Path | None = None) -> dict:
    path = (Path(work) / "terraced-config.yaml") if work is not None else QUESTIONS_PATH
    if work is None and not path.is_file():
        path = QUESTIONS_TEMPLATE_PATH
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid terraced question config {path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError(f"terraced question config has unsupported schema: {path}")
    domains = doc.get("domains")
    profiles = doc.get("execution_profiles")
    if not isinstance(domains, dict) or not isinstance(profiles, dict):
        raise ValueError("terraced question config requires domains and execution_profiles")
    question_ids = {}
    for domain, data in domains.items():
        rows = (data or {}).get("questions")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"domain {domain!r} has no questions")
        ids = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("question"), str):
                raise ValueError(f"domain {domain!r} contains a malformed question")
            ids.append(row["id"])
        if len(ids) != len(set(ids)):
            raise ValueError(f"domain {domain!r} contains duplicate question IDs")
        question_ids[domain] = ids
    for profile_id, profile in profiles.items():
        groups = (profile or {}).get("groups") or {}
        for domain, ids in question_ids.items():
            domain_groups = groups.get(domain)
            if not isinstance(domain_groups, list) or not domain_groups:
                raise ValueError(f"execution profile {profile_id!r} has no groups for {domain}")
            flattened = [qid for group in domain_groups for qid in group]
            if flattened != ids:
                raise ValueError(
                    f"execution profile {profile_id!r}/{domain} must cover questions once in canonical order; "
                    f"expected {ids}, found {flattened}"
                )
    default = doc.get("default_execution_profile")
    if default not in profiles:
        raise ValueError("default_execution_profile is not registered")
    return doc


def execution_groups(work: Path, domain: str, profile: str) -> list[list[str]]:
    config = load_questions(work)
    try:
        return config["execution_profiles"][profile]["groups"][domain]
    except KeyError as exc:
        raise ValueError(f"unknown terrace execution profile/domain: {profile}/{domain}") from exc


def questions_for_group(work: Path, domain: str, ids: list[str]) -> list[dict]:
    config = load_questions(work)
    rows = config["domains"][domain]["questions"]
    by_id = {row["id"]: row for row in rows}
    return [by_id[qid] for qid in ids]


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc


def validate_case_input(work: Path) -> str:
    doc = _load_json(Path(work) / "case-input.json")
    expected = {"provisional_cmcs", "provisional_disease", "genes", "case_facts"}
    if not isinstance(doc, dict) or set(doc) != expected:
        raise ValueError("case-input.json must contain exactly provisional_cmcs, provisional_disease, genes, case_facts")
    genes = doc["genes"]
    if not isinstance(genes, list) or any(not isinstance(g, str) or not g.strip() or g != g.upper() for g in genes):
        raise ValueError("genes must be a list of non-empty uppercase gene symbols")
    if len(genes) != len(set(genes)):
        raise ValueError("genes contains duplicates")
    cmcs = doc["provisional_cmcs"]
    if not isinstance(cmcs, list) or not cmcs:
        raise ValueError("provisional_cmcs must be a non-empty list")
    if len(cmcs) != len(set(cmcs)):
        raise ValueError("provisional_cmcs contains duplicates")
    for cmc in cmcs:
        if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
            raise ValueError(f"invalid provisional CMC {cmc!r}")
    if not isinstance(doc["provisional_disease"], str) or not doc["provisional_disease"].strip():
        raise ValueError("provisional_disease must be non-empty")
    facts = doc["case_facts"]
    if not isinstance(facts, list) or not facts:
        raise ValueError("case_facts must be a non-empty list")
    ids = []
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict) or not isinstance(fact.get("fact_id"), str) or not fact["fact_id"].strip():
            raise ValueError(f"case_facts[{index}] requires non-empty fact_id")
        ids.append(fact["fact_id"])
    if len(ids) != len(set(ids)):
        raise ValueError("case_facts contains duplicate fact_id values")
    return "case-input.json validated"


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid YAML {path}: {exc}") from exc


def _fact_rows(rows, *, aligned: bool, context: str) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{context} facts must be a YAML list")
    expected = {"fact", "reason", "citation"} if aligned else {"fact", "reason"}
    output = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError(f"{context} fact {index + 1} must contain exactly {', '.join(sorted(expected))}")
        if not isinstance(row["fact"], str) or not row["fact"].strip():
            raise ValueError(f"{context} fact {index + 1} has blank fact")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise ValueError(f"{context} fact {index + 1} has blank reason")
        if CARD_RE.search(row["fact"]) or CARD_RE.search(row["reason"]):
            raise ValueError(f"{context} fact {index + 1} embeds card tags in fact/reason")
        if aligned:
            citation = row["citation"]
            if citation is not None and (not isinstance(citation, str) or CITATION_RE.fullmatch(citation) is None):
                raise ValueError(f"{context} fact {index + 1} citation must be null or adjacent runtime card tags")
        output.append(row)
    return output


def _validate_diagnosis_doc(doc, *, aligned: bool, final: bool) -> dict:
    if not isinstance(doc, dict) or set(doc) != {"provisional_cmcs", "diagnoses", "facts"}:
        raise ValueError("diagnosis state must contain exactly provisional_cmcs, diagnoses, facts")
    cmcs = doc["provisional_cmcs"]
    if not isinstance(cmcs, list) or not cmcs or len(cmcs) != len(set(cmcs)):
        raise ValueError("diagnosis provisional_cmcs must be a non-empty unique list")
    for cmc in cmcs:
        if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
            raise ValueError(f"diagnosis contains invalid provisional CMC {cmc!r}")
    diagnoses = doc["diagnoses"]
    if not isinstance(diagnoses, list):
        raise ValueError("diagnoses must be a list")
    if final and not diagnoses:
        raise ValueError("final diagnostic terrace must accept at least one WHO5 diagnosis")
    for index, row in enumerate(diagnoses):
        if not isinstance(row, dict) or set(row) != {"schema_disease", "narrow_diagnosis"}:
            raise ValueError(f"diagnoses[{index}] must contain schema_disease and narrow_diagnosis")
        disease = row["schema_disease"]
        if disease in WHO5_EXCLUDED_SCHEMA_DISEASES:
            raise ValueError("MDS/AML is ICC-only and cannot be the accepted WHO5 routing diagnosis")
        if disease not in vocab.CASE_DISEASE_SET:
            raise ValueError(f"diagnoses[{index}].schema_disease {disease!r} is not canonical")
        if not isinstance(row["narrow_diagnosis"], str) or not row["narrow_diagnosis"].strip():
            raise ValueError(f"diagnoses[{index}].narrow_diagnosis must be non-empty WHO5 wording")
    _fact_rows(doc["facts"], aligned=aligned, context="diagnosis")
    return doc


def validate_category_answer(path: Path, domain: str, *, final: bool = True, aligned: bool = False) -> str:
    doc = _load_yaml(Path(path))
    if domain == "diagnosis":
        _validate_diagnosis_doc(doc, aligned=aligned, final=final)
    else:
        _fact_rows(doc, aligned=aligned, context=domain)
    return f"validated {Path(path).name}"


def validate_review(path: Path) -> tuple[bool, list[str]]:
    doc = _load_json(Path(path))
    if not isinstance(doc, dict) or set(doc) != {"pass", "issues"}:
        raise ValueError("semantic review must contain exactly pass and issues")
    if not isinstance(doc["pass"], bool) or not isinstance(doc["issues"], list) or any(not isinstance(x, str) for x in doc["issues"]):
        raise ValueError("semantic review pass must be boolean and issues must be a string list")
    if doc["pass"] and doc["issues"]:
        raise ValueError("passing semantic review must have no issues")
    if not doc["pass"] and not doc["issues"]:
        raise ValueError("failing semantic review must identify at least one issue")
    return doc["pass"], doc["issues"]


def known_tags_from_evidence(path: Path) -> set[str]:
    text = Path(path).read_text(encoding="utf-8")
    return set(CARD_RE.findall(text))


def validate_alignment(source_path: Path, aligned_path: Path, domain: str, evidence_path: Path) -> str:
    source = _load_yaml(Path(source_path))
    aligned = _load_yaml(Path(aligned_path))
    validate_category_answer(source_path, domain, final=True, aligned=False)
    validate_category_answer(aligned_path, domain, final=True, aligned=True)
    if domain == "diagnosis":
        if source["provisional_cmcs"] != aligned["provisional_cmcs"] or source["diagnoses"] != aligned["diagnoses"]:
            raise ValueError("evidence alignment changed diagnosis routing state")
        source_rows, aligned_rows = source["facts"], aligned["facts"]
    else:
        source_rows, aligned_rows = source, aligned
    if len(source_rows) != len(aligned_rows):
        raise ValueError("evidence alignment changed fact count")
    known = known_tags_from_evidence(evidence_path)
    for index, (before, after) in enumerate(zip(source_rows, aligned_rows), start=1):
        if before["fact"] != after["fact"] or before["reason"] != after["reason"]:
            raise ValueError(f"evidence alignment changed fact/reason at row {index}")
        citation = after["citation"]
        if citation:
            unknown = sorted(set(CARD_RE.findall(citation)) - known)
            if unknown:
                raise ValueError(f"evidence alignment cites unknown tag(s): {', '.join(unknown)}")
    return f"validated {Path(aligned_path).name}"


def render_evidence(work: Path, domain: str) -> Path:
    bundle = Path(work) / f"evidence-{domain}.json"
    output = Path(work) / f"evidence-{domain}.md"
    rendering.render_to_files(bundle, output=output, retrieved_only=True)
    return output


def facts_only(work: Path) -> Path:
    result = {}
    for domain in DOMAINS:
        path = Path(work) / f"category-{domain}.yaml"
        doc = _load_yaml(path)
        rows = doc["facts"] if domain == "diagnosis" else doc
        result[domain] = [{"fact": row["fact"]} for row in rows]
    output = Path(work) / "report-facts.yaml"
    output.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    return output


def accepted_categories_document(work: Path) -> str:
    parts = []
    for domain in DOMAINS:
        path = Path(work) / f"category-{domain}.yaml"
        parts.append(f"## {domain}\n\n{path.read_text(encoding='utf-8').rstrip()}")
    return "\n\n".join(parts) + "\n"


def prepare_combined_evidence(work: Path) -> tuple[Path, Path]:
    bundle = retrieval.combined(work)
    evidence = Path(work) / "evidence.md"
    tags = Path(work) / "card-tags.json"
    rendering.render_to_files(bundle, output=evidence, card_tag_output=tags, retrieved_only=True)
    return evidence, tags


def validate_cited_report(work: Path) -> str:
    report = Path(work) / "report-cited.md"
    text = report.read_text(encoding="utf-8")
    if text.strip() == "UNMATCHED_SUMMARY_SENTENCE":
        raise ValueError("final citation alignment found an unmatched summary sentence; redo summarisation")
    report_citations.validate(
        text,
        (Path(work) / "evidence.md").read_text(encoding="utf-8"),
        (Path(work) / "card-tags.json").read_text(encoding="utf-8"),
        source="terraced report-cited.md",
        require_citation_after_full_stop=True,
    )
    return "report-cited.md validated"


def render_final(work: Path) -> Path:
    validate_cited_report(work)
    rendered = report_citations.render(
        (Path(work) / "report-cited.md").read_text(encoding="utf-8"),
        (Path(work) / "evidence.md").read_text(encoding="utf-8"),
        (Path(work) / "card-tags.json").read_text(encoding="utf-8"),
        require_citation_after_full_stop=True,
    )
    output = Path(work) / "report-final.md"
    report_citations.atomic_write(output, rendered)
    return output


def run(command: str, work_dir: Path) -> list[str]:
    work = Path(work_dir).resolve()
    if command == "validate-case":
        return [validate_case_input(work)]
    if command == "diagnosis-retrieve":
        return [str(retrieval.diagnosis(work)), str(render_evidence(work, "diagnosis"))]
    if command.startswith("retrieve-"):
        domain = command.removeprefix("retrieve-")
        return [str(retrieval.downstream(work, domain)), str(render_evidence(work, domain))]
    if command == "facts-only":
        return [str(facts_only(work))]
    if command == "combined-evidence":
        evidence, tags = prepare_combined_evidence(work)
        return [str(evidence), str(tags)]
    if command == "render-final":
        return [str(render_final(work))]
    raise ValueError(f"unknown terraced runtime command {command!r}")
