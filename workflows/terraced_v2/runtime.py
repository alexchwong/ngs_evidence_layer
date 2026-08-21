"""Deterministic configuration, validation, and setup helpers for terraced-v2."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

from scripts import vocab
from workflows.terraced_v2 import layout

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
WORKFLOW_PATH = HERE / "workflow.yaml"
QUESTIONS_PATH = HERE / "questions.yaml"
WHO5_EXCLUDED_SCHEMA_DISEASES = {"MDS/AML"}
VALIDATION_MODES = {"nel-validate", "nel-validate-function", "nel-validate-brief"}


def _raise_issues(context: str, issues: list[str]) -> None:
    if issues:
        rendered = "\n".join(f"{i}. {issue}" for i, issue in enumerate(issues, 1))
        raise ValueError(f"{context} failed validation with {len(issues)} issue(s):\n{rendered}")


def load_pipeline() -> dict:
    try:
        doc = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid terraced-v2 workflow.yaml: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1 or doc.get("workflow_id") != "terraced-v2":
        raise ValueError("workflow.yaml must declare schema_version: 1 and workflow_id: terraced-v2")
    stages = doc.get("pipeline")
    if not isinstance(stages, list) or not stages:
        raise ValueError("workflow.yaml pipeline must be a non-empty list")
    ids = []
    for i, row in enumerate(stages, 1):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("module"), str):
            raise ValueError(f"workflow.yaml pipeline[{i}] requires string id and module")
        if row["id"] in ids:
            raise ValueError(f"duplicate pipeline stage id {row['id']!r}")
        ids.append(row["id"])
    return doc


def load_questions() -> dict:
    try:
        doc = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid terraced-v2 questions.yaml: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError("questions.yaml must declare schema_version: 1")
    domains = doc.get("domains")
    profiles = doc.get("execution_profiles")
    if not isinstance(domains, dict) or not isinstance(profiles, dict) or not domains or not profiles:
        raise ValueError("questions.yaml requires domains and execution_profiles")
    domain_ids: dict[str, list[str]] = {}
    for domain, data in domains.items():
        rows = (data or {}).get("questions")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"domain {domain!r} has no questions")
        ids = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("question"), str):
                raise ValueError(f"domain {domain!r} contains a malformed question")
            qid = row["id"]
            if qid in ids:
                raise ValueError(f"domain {domain!r} contains duplicate question ID {qid!r}")
            ids.append(qid)
        domain_ids[domain] = ids
    for profile_id, profile in profiles.items():
        groups = (profile or {}).get("groups")
        if not isinstance(groups, dict):
            raise ValueError(f"execution profile {profile_id!r} has no groups")
        for domain, ids in domain_ids.items():
            domain_groups = groups.get(domain)
            if not isinstance(domain_groups, list) or not domain_groups:
                raise ValueError(f"execution profile {profile_id!r} has no groups for {domain}")
            flattened = [qid for group in domain_groups for qid in group]
            if flattened != ids:
                raise ValueError(
                    f"execution profile {profile_id!r}/{domain} must cover questions once in canonical order; "
                    f"expected {ids!r}, found {flattened!r}"
                )
    default = doc.get("default_execution_profile")
    if default not in profiles:
        raise ValueError("default_execution_profile is not registered")
    return doc


def execution_groups(domain: str, profile: str) -> list[list[str]]:
    config = load_questions()
    try:
        return config["execution_profiles"][profile]["groups"][domain]
    except KeyError as exc:
        raise ValueError(f"unknown terrace execution profile/domain: {profile}/{domain}") from exc


def questions_for_group(domain: str, ids: list[str]) -> list[dict]:
    rows = load_questions()["domains"][domain]["questions"]
    by_id = {row["id"]: row for row in rows}
    return [by_id[qid] for qid in ids]


def setup_assets(work_dir: Path, *, mode: str, case_id: str | None = None) -> None:
    work = Path(work_dir)
    layout.ensure_dirs(work)
    for domain in ("diagnosis", "germline", "prognosis", "biomarker", "treatment"):
        (work / domain).mkdir(parents=True, exist_ok=True)

    panel_root = work / "ngs-panel-scope.md"
    panel_out = layout.input(work, "ngs-panel-scope.md", existing=False)
    if panel_root.is_file() and panel_out != panel_root:
        shutil.move(str(panel_root), str(panel_out))

    cmc_root = work / "case-major-categories.json"
    cmc_out = layout.input(work, "case-major-categories.json", existing=False)
    cmc_out.write_text(
        json.dumps(
            {
                "case_major_categories": list(vocab.CASE_MAJOR_CATEGORIES),
                "instruction": (
                    "Select one or more provisional case-major categories representing the supplied starting "
                    "clinicopathological disease family or families. These are retrieval scaffolds, not final diagnoses."
                ),
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    if cmc_root != cmc_out:
        cmc_root.unlink(missing_ok=True)

    allowed = [d for d in vocab.CASE_DISEASES if d not in WHO5_EXCLUDED_SCHEMA_DISEASES]
    layout.input(work, "allowed-schema-diseases.json", existing=False).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allowed_schema_diseases": allowed,
                "instruction": "WHO5 controls schema_disease and downstream routing; ICC is comparator-only.",
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(WORKFLOW_PATH, layout.input(work, "workflow.yaml", existing=False))
    shutil.copyfile(QUESTIONS_PATH, layout.input(work, "questions.yaml", existing=False))

    if mode in VALIDATION_MODES:
        if not case_id:
            raise ValueError(f"{mode} requires a validation case ID")
        repo_text = str(REPO_ROOT)
        inserted = False
        if repo_text not in sys.path:
            sys.path.insert(0, repo_text)
            inserted = True
        try:
            from validation.cases import case_file_for_mode, retrieve_case
            text = retrieve_case(case_id, case_file_for_mode(mode))
        finally:
            if inserted and sys.path and sys.path[0] == repo_text:
                sys.path.pop(0)
        path = layout.input(work, "case.md", existing=False)
        payload = text.rstrip() + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"{path} exists with different validation case content")
        path.write_text(payload, encoding="utf-8")


def read_json(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"expected one JSON object in {path}")
    return doc


def validate_case_json(path: Path) -> str:
    doc = read_json(path)
    required = {"provisional_cmcs", "provisional_disease", "genes", "detected_variants_summary", "case_facts"}
    issues = []
    if set(doc) != required:
        issues.append(f"Top level — expected exactly {sorted(required)}, received {sorted(doc)}")
    cmcs = doc.get("provisional_cmcs")
    if not isinstance(cmcs, list) or not cmcs:
        issues.append("provisional_cmcs — must be a non-empty list")
    else:
        seen = set()
        for i, cmc in enumerate(cmcs):
            if not isinstance(cmc, str) or cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                issues.append(f"provisional_cmcs[{i}] — use an exact allowed CMC")
            if cmc in seen:
                issues.append(f"provisional_cmcs[{i}] — duplicate CMC {cmc!r}")
            seen.add(cmc)
    genes = doc.get("genes")
    if not isinstance(genes, list):
        issues.append("genes — must be a list")
    else:
        seen = set()
        for i, gene in enumerate(genes):
            if not isinstance(gene, str) or not gene.strip() or gene != gene.upper():
                issues.append(f"genes[{i}] — use a non-empty uppercase gene symbol")
            if gene in seen:
                issues.append(f"genes[{i}] — duplicate gene {gene!r}")
            seen.add(gene)
    for key in ("provisional_disease", "detected_variants_summary"):
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            issues.append(f"{key} — must be a non-empty string")
    facts = doc.get("case_facts")
    if not isinstance(facts, list):
        issues.append("case_facts — must be a list")
    else:
        ids = set()
        for i, row in enumerate(facts):
            if not isinstance(row, dict) or set(row) != {"fact_id", "kind", "value"}:
                issues.append(f"case_facts[{i}] — expected exactly fact_id, kind, value")
                continue
            for key in ("fact_id", "kind", "value"):
                if not isinstance(row[key], str) or not row[key].strip():
                    issues.append(f"case_facts[{i}].{key} — must be a non-empty string")
            if row.get("fact_id") in ids:
                issues.append(f"case_facts[{i}].fact_id — duplicate ID {row.get('fact_id')!r}")
            ids.add(row.get("fact_id"))
    _raise_issues("case.json", issues)
    return "case.json validated"


def parse_yaml_mapping(path: Path) -> dict:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid YAML {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"expected one YAML mapping in {path}")
    return doc


def validate_diagnosis_state(path: Path, *, final: bool = False, final_config: dict | None = None, reviewed: dict | None = None) -> str:
    doc = parse_yaml_mapping(path)
    if final:
        validate_diagnosis_final(doc, reviewed or {}, final_config or {})
        return "diagnosis final state validated"
    required = {"provisional_cmcs", "diagnoses", "facts", "uncertainties"}
    issues = []
    if set(doc) != required:
        issues.append(f"Top level — expected exactly {sorted(required)}, received {sorted(doc)}")
    cmcs = doc.get("provisional_cmcs")
    if not isinstance(cmcs, list) or not cmcs:
        issues.append("provisional_cmcs — must be a non-empty list")
    else:
        for i, cmc in enumerate(cmcs):
            if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                issues.append(f"provisional_cmcs[{i}] — {cmc!r} is not an allowed CMC")
    diagnoses = doc.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        issues.append("diagnoses — return at least one paired WHO5/ICC row")
        diagnoses = []
    statuses = {"established", "indeterminate", "not_established", "not_applicable"}
    for i, row in enumerate(diagnoses):
        loc = f"diagnoses[{i}]"
        required_row = {"schema_disease", "WHO5", "ICC", "materially_different"}
        if not isinstance(row, dict) or set(row) != required_row:
            issues.append(f"{loc} — expected exactly {sorted(required_row)}")
            continue
        if row["schema_disease"] not in vocab.CASE_DISEASE_SET or row["schema_disease"] == "MDS/AML":
            issues.append(f"{loc}.schema_disease — use an allowed WHO5 routing disease; MDS/AML is ICC-only")
        if not isinstance(row["materially_different"], bool):
            issues.append(f"{loc}.materially_different — must be boolean")
        for classifier in ("WHO5", "ICC"):
            outcome = row[classifier]
            if not isinstance(outcome, dict) or set(outcome) != {"status", "diagnosis"}:
                issues.append(f"{loc}.{classifier} — expected exactly status and diagnosis")
                continue
            if outcome["status"] not in statuses:
                issues.append(f"{loc}.{classifier}.status — invalid status")
            if outcome["diagnosis"] is not None and (not isinstance(outcome["diagnosis"], str) or not outcome["diagnosis"].strip()):
                issues.append(f"{loc}.{classifier}.diagnosis — use null or a non-empty string")
            if outcome["status"] == "established" and outcome["diagnosis"] is None:
                issues.append(f"{loc}.{classifier}.diagnosis — established status requires diagnosis text")
    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        rows = doc.get(field)
        if not isinstance(rows, list):
            issues.append(f"{field} — must be a list")
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != {text_key, "reason"}:
                issues.append(f"{field}[{i}] — expected exactly {text_key} and reason")
                continue
            if any(not isinstance(row[k], str) or not row[k].strip() for k in (text_key, "reason")):
                issues.append(f"{field}[{i}] — both fields must be non-empty strings")
    _raise_issues("diagnosis terrace state", issues)
    return "diagnosis terrace state validated"


def reviewed_with_ids(reviewed: dict) -> dict:
    return {
        "provisional_cmcs": reviewed["provisional_cmcs"],
        "diagnoses": reviewed["diagnoses"],
        "facts": [dict(row, fact_id=f"PRE-FINAL-F{i}") for i, row in enumerate(reviewed["facts"], 1)],
        "uncertainties": [dict(row, uncertainty_id=f"PRE-FINAL-U{i}") for i, row in enumerate(reviewed["uncertainties"], 1)],
    }


def validate_diagnosis_final(doc: dict, reviewed: dict, config: dict) -> None:
    required = set((config.get("output") or {}).get("keys") or [])
    if set(doc) != required:
        raise ValueError(f"Final output keys must be exactly {sorted(required)}; received {sorted(doc)}")
    issues = []
    for key in (config.get("invariants") or {}).get("preserve_fields") or []:
        if doc.get(key) != reviewed.get(key):
            issues.append(f"Final output.{key} — copy the protected pre-final value exactly")
    fact_ids = {row["fact_id"] for row in reviewed.get("facts") or []}
    uncertainty_ids = {row["uncertainty_id"] for row in reviewed.get("uncertainties") or []}
    all_ids = fact_ids | uncertainty_ids
    facts = doc.get("supporting_facts")
    if not isinstance(facts, list):
        issues.append("supporting_facts — must be a list")
        facts = []
    for i, row in enumerate(facts):
        if not isinstance(row, dict) or set(row) != {"fact", "reason", "source_fact_ids"}:
            issues.append(f"supporting_facts[{i}] — expected exactly fact, reason, source_fact_ids")
            continue
        ids = row["source_fact_ids"]
        if not isinstance(ids, list) or not ids or any(x not in fact_ids for x in ids):
            issues.append(f"supporting_facts[{i}].source_fact_ids — use supplied PRE-FINAL-F IDs only")
    uncertainties = doc.get("uncertainties")
    if not isinstance(uncertainties, list):
        issues.append("uncertainties — must be a list")
        uncertainties = []
    seen = set()
    for i, row in enumerate(uncertainties):
        if not isinstance(row, dict) or set(row) != {"uncertainty", "reason", "source_ids"}:
            issues.append(f"uncertainties[{i}] — expected exactly uncertainty, reason, source_ids")
            continue
        ids = row["source_ids"]
        if not isinstance(ids, list) or not ids or any(x not in all_ids for x in ids):
            issues.append(f"uncertainties[{i}].source_ids — use supplied PRE-FINAL-F/PRE-FINAL-U IDs only")
            continue
        seen.update(x for x in ids if x in uncertainty_ids)
    missing = sorted(uncertainty_ids - seen)
    if (config.get("invariants") or {}).get("require_all_prior_uncertainties") and missing:
        issues.append("uncertainties — dropped pre-final uncertainty source(s): " + ", ".join(missing))
    if (config.get("invariants") or {}).get("prohibit_new_numeric_tokens"):
        before = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(reviewed, ensure_ascii=False)))
        after = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(doc, ensure_ascii=False)))
        extra = sorted(after - before)
        if extra:
            issues.append("Final output introduced new numeric token(s): " + ", ".join(extra))
    _raise_issues("diagnosis final synthesis", issues)


def validate_domain_state(path: Path) -> str:
    doc = parse_yaml_mapping(path)
    required = {"facts", "uncertainties", "upstream_issues"}
    issues = []
    if set(doc) != required:
        issues.append(f"Top level — expected exactly {sorted(required)}, received {sorted(doc)}")
    specs = (("facts", "fact"), ("uncertainties", "uncertainty"), ("upstream_issues", "issue"))
    for field, text_key in specs:
        rows = doc.get(field)
        if not isinstance(rows, list):
            issues.append(f"{field} — must be a list")
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != {text_key, "reason"}:
                issues.append(f"{field}[{i}] — expected exactly {text_key} and reason")
                continue
            for key in (text_key, "reason"):
                if not isinstance(row[key], str) or not row[key].strip():
                    issues.append(f"{field}[{i}].{key} — must be a non-empty string")
            text = row.get(text_key)
            if field != "upstream_issues" and isinstance(text, str) and text.strip() and not text.rstrip().endswith("."):
                issues.append(f"{field}[{i}].{text_key} — report-ready propositions must end with a full stop")
    _raise_issues("downstream terrace state", issues)
    return "downstream terrace state validated"


def validate_domain_alignment(path: Path, state_path: Path, permitted_tags: set[str]) -> str:
    aligned = parse_yaml_mapping(path)
    state = parse_yaml_mapping(state_path)
    required = {"facts", "uncertainties"}
    issues = []
    if set(aligned) != required:
        issues.append(f"Top level — expected exactly {sorted(required)}, received {sorted(aligned)}")
    tag_re = re.compile(r"(?:\[card:([0-9a-f]{12})\])+")
    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        source = state.get(field) or []
        rows = aligned.get(field)
        if not isinstance(rows, list) or len(rows) != len(source):
            issues.append(f"{field} — expected {len(source)} rows in the original order")
            continue
        for i, (row, expected) in enumerate(zip(rows, source)):
            if not isinstance(row, dict) or set(row) != {text_key, "reason", "citation"}:
                issues.append(f"{field}[{i}] — expected exactly {text_key}, reason, citation")
                continue
            if row[text_key] != expected[text_key] or row["reason"] != expected["reason"]:
                issues.append(f"{field}[{i}] — clinical text changed; copy it character-for-character")
            citation = row["citation"]
            if citation is None:
                continue
            if not isinstance(citation, str) or tag_re.fullmatch(citation) is None:
                issues.append(f"{field}[{i}].citation — use null or adjacent 12-hex runtime card tags")
                continue
            tags = re.findall(r"\[card:([0-9a-f]{12})\]", citation)
            unknown = sorted(set(tags) - permitted_tags)
            if unknown:
                issues.append(f"{field}[{i}].citation — unpermitted tag(s): {', '.join(unknown)}")
            if len(tags) != len(set(tags)):
                issues.append(f"{field}[{i}].citation — repeated card tag")
    _raise_issues("domain evidence alignment", issues)
    return "domain evidence alignment validated"


def diagnosis_context(final_doc: dict) -> dict:
    """Expose only settled routing/WHO5/facts. Diagnostic uncertainties never cross this boundary."""
    diagnoses = []
    for row in final_doc.get("diagnoses") or []:
        who = row.get("WHO5") or {}
        if who.get("status") == "established":
            diagnoses.append(
                {
                    "schema_disease": row.get("schema_disease"),
                    "status": who.get("status"),
                    "diagnosis": who.get("diagnosis"),
                }
            )
    return {
        "cmc": list(final_doc.get("provisional_cmcs") or []),
        "who5_diagnosis": diagnoses,
        "facts": [
            {"fact": row.get("fact"), "reason": row.get("reason")}
            for row in final_doc.get("supporting_facts") or []
        ],
    }
