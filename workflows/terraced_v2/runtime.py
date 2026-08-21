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


def _strip_full_code_fence(text: str) -> tuple[str, bool]:
    """Remove one enclosing Markdown code fence without touching inner content."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text, False
    lines = stripped.splitlines()
    if len(lines) < 2 or not lines[-1].strip().startswith("```"):
        return text, False
    return "\n".join(lines[1:-1]).strip() + "\n", True


def _remove_json_trailing_commas(text: str) -> tuple[str, bool]:
    """Remove commas immediately before ]/} while preserving quoted strings."""
    chars: list[str] = []
    in_string = False
    escaped = False
    changed = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            chars.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            chars.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] in "]}":
                changed = True
                i += 1
                continue
        chars.append(ch)
        i += 1
    return "".join(chars), changed


def normalize_model_text(text: str, *, format_name: str = "TEXT") -> tuple[str, list[str]]:
    """Canonically repair syntax-only defects before deterministic validation.

    Repairs here must be semantics-preserving.  Artifact-specific normalizers may
    apply additional equally safe transformations before their validators run.
    """
    repairs: list[str] = []
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
        repairs.append("removed UTF-8 BOM")
    text, unfenced = _strip_full_code_fence(text)
    if unfenced:
        repairs.append("removed enclosing Markdown code fence")
    if format_name.upper() == "JSON":
        text, commas = _remove_json_trailing_commas(text)
        if commas:
            repairs.append("removed trailing comma(s) before closing JSON bracket/brace")
    return text, repairs


def _read_text_with_syntax_repairs(path: Path, *, format_name: str) -> tuple[str, list[str]]:
    """Apply only syntax-preserving repairs that do not infer clinical content."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"{format_name} — Problem: cannot read {path}: {exc}. Required fix: restore the requested model artifact at this path."
        ) from exc
    text, repairs = normalize_model_text(raw, format_name=format_name)
    if text != raw:
        path.write_text(text, encoding="utf-8")
    return text, repairs


def load_pipeline() -> dict:
    try:
        doc = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"workflow.yaml — Problem: cannot read {WORKFLOW_PATH}: {exc}. Required fix: restore the canonical workflow.yaml file."
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValueError(
            f"workflow.yaml — Problem: YAML parser error{where}: {problem}. Required fix: correct the YAML syntax without changing the intended pipeline."
        ) from exc
    if not isinstance(doc, dict):
        raise ValueError(
            f"workflow.yaml — Problem: expected one YAML mapping, received {type(doc).__name__}. Required fix: restore the complete workflow mapping."
        )
    issues: list[str] = []
    if doc.get("schema_version") != 1:
        issues.append(
            f"schema_version — Problem: expected 1, received {doc.get('schema_version')!r}. Required fix: set schema_version: 1."
        )
    if doc.get("workflow_id") != "terraced-v2":
        issues.append(
            f"workflow_id — Problem: expected 'terraced-v2', received {doc.get('workflow_id')!r}. Required fix: set workflow_id: terraced-v2."
        )
    stages = doc.get("pipeline")
    if not isinstance(stages, list):
        issues.append(
            f"pipeline — Problem: expected a non-empty list, received {stages!r}. Required fix: restore the ordered pipeline stage list."
        )
        stages = []
    elif not stages:
        issues.append("pipeline — Problem: list is empty. Required fix: restore at least one configured pipeline stage.")
    ids: list[str] = []
    for i, row in enumerate(stages, 1):
        location = f"pipeline[{i}]"
        if not isinstance(row, dict):
            issues.append(
                f"{location} — Problem: expected an object, received {row!r}. Required fix: return a stage object containing string id and module fields."
            )
            continue
        stage_id = row.get("id")
        module = row.get("module")
        if not isinstance(stage_id, str) or not stage_id.strip():
            issues.append(
                f"{location}.id — Problem: expected a non-empty string, received {stage_id!r}. Required fix: supply a unique stage ID string."
            )
        if not isinstance(module, str) or not module.strip():
            issues.append(
                f"{location}.module — Problem: expected a non-empty string, received {module!r}. Required fix: supply the configured Python module name."
            )
        if isinstance(stage_id, str) and stage_id in ids:
            issues.append(
                f"{location}.id — Problem: duplicate pipeline stage ID {stage_id!r}. Required fix: keep each stage ID unique."
            )
        if isinstance(stage_id, str):
            ids.append(stage_id)
    _raise_issues("workflow.yaml", issues)
    return doc


def load_questions() -> dict:
    try:
        doc = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"questions.yaml — Problem: cannot read {QUESTIONS_PATH}: {exc}. Required fix: restore the canonical questions.yaml file."
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValueError(
            f"questions.yaml — Problem: YAML parser error{where}: {problem}. Required fix: correct the YAML syntax without changing the intended question order."
        ) from exc
    if not isinstance(doc, dict):
        raise ValueError(
            f"questions.yaml — Problem: expected one YAML mapping, received {type(doc).__name__}. Required fix: restore the complete questions configuration mapping."
        )
    issues: list[str] = []
    if doc.get("schema_version") != 1:
        issues.append(
            f"schema_version — Problem: expected 1, received {doc.get('schema_version')!r}. Required fix: set schema_version: 1."
        )
    domains = doc.get("domains")
    profiles = doc.get("execution_profiles")
    if not isinstance(domains, dict) or not domains:
        issues.append(
            f"domains — Problem: expected a non-empty mapping, received {domains!r}. Required fix: restore each configured clinical domain and its questions."
        )
        domains = {}
    if not isinstance(profiles, dict) or not profiles:
        issues.append(
            f"execution_profiles — Problem: expected a non-empty mapping, received {profiles!r}. Required fix: restore the configured terrace execution profiles."
        )
        profiles = {}
    domain_ids: dict[str, list[str]] = {}
    for domain, data in domains.items():
        rows = (data or {}).get("questions") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            issues.append(
                f"domains.{domain}.questions — Problem: expected a non-empty list, received {rows!r}. Required fix: restore the canonical ordered question list for this domain."
            )
            domain_ids[domain] = []
            continue
        ids: list[str] = []
        for index, row in enumerate(rows, 1):
            location = f"domains.{domain}.questions[{index}]"
            if not isinstance(row, dict):
                issues.append(
                    f"{location} — Problem: expected an object, received {row!r}. Required fix: return a question object with non-empty id and question strings."
                )
                continue
            qid = row.get("id")
            question = row.get("question")
            if not isinstance(qid, str) or not qid.strip():
                issues.append(
                    f"{location}.id — Problem: expected a non-empty string, received {qid!r}. Required fix: supply the canonical unique question ID."
                )
            if not isinstance(question, str) or not question.strip():
                issues.append(
                    f"{location}.question — Problem: expected non-empty question text, received {question!r}. Required fix: restore the question text."
                )
            if isinstance(qid, str) and qid in ids:
                issues.append(
                    f"{location}.id — Problem: duplicate question ID {qid!r}. Required fix: keep each question ID unique within the domain."
                )
            if isinstance(qid, str):
                ids.append(qid)
        domain_ids[domain] = ids
    for profile_id, profile in profiles.items():
        groups = (profile or {}).get("groups") if isinstance(profile, dict) else None
        if not isinstance(groups, dict):
            issues.append(
                f"execution_profiles.{profile_id}.groups — Problem: expected a domain-to-groups mapping, received {groups!r}. Required fix: restore groups for every configured domain."
            )
            continue
        for domain, ids in domain_ids.items():
            domain_groups = groups.get(domain)
            if not isinstance(domain_groups, list) or not domain_groups:
                issues.append(
                    f"execution_profiles.{profile_id}.groups.{domain} — Problem: expected a non-empty list of question groups, received {domain_groups!r}. Required fix: group every canonical question exactly once in canonical order."
                )
                continue
            malformed_groups = [index for index, group in enumerate(domain_groups, 1) if not isinstance(group, list) or not group]
            if malformed_groups:
                issues.append(
                    f"execution_profiles.{profile_id}.groups.{domain} — Problem: empty or non-list group(s) at position(s) {malformed_groups!r}. Required fix: make every group a non-empty list of question IDs."
                )
                continue
            flattened = [qid for group in domain_groups for qid in group]
            if flattened != ids:
                issues.append(
                    f"execution_profiles.{profile_id}.groups.{domain} — Problem: groups do not cover questions once in canonical order; expected {ids!r}, found {flattened!r}. Required fix: regroup without reordering, omitting, or duplicating question IDs."
                )
    default = doc.get("default_execution_profile")
    if default not in profiles:
        issues.append(
            f"default_execution_profile — Problem: {default!r} is not a registered profile. Required fix: choose one of {sorted(profiles)!r}."
        )
    _raise_issues("questions.yaml", issues)
    return doc


def execution_groups(domain: str, profile: str) -> list[list[str]]:
    config = load_questions()
    try:
        return config["execution_profiles"][profile]["groups"][domain]
    except KeyError as exc:
        raise ValueError(
            f"Terrace routing — Problem: unknown execution profile/domain {profile}/{domain}. "
            "Required fix: use a profile/domain pair declared in questions.yaml."
        ) from exc


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
            raise ValueError(
                f"Validation setup — Problem: {mode} has no validation case ID. Required fix: rerun setup with --case-id <ID>."
            )
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
            raise ValueError(
                f"Validation setup — Problem: {path} already exists with different case content. "
                "Required fix: use a new work directory or restore the exact selected validation case text."
            )
        path.write_text(payload, encoding="utf-8")


def read_json(path: Path) -> dict:
    text, _repairs = _read_text_with_syntax_repairs(path, format_name="JSON")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON — Problem: parser error in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}. "
            "Required fix: return one complete syntactically valid JSON object only, with no Markdown fence, commentary, or unsupported JSON syntax."
        ) from exc
    if not isinstance(doc, dict):
        raise ValueError(
            f"Top level — Problem: expected one JSON object in {path}, received {type(doc).__name__}. "
            "Required fix: return the complete requested JSON object only."
        )
    return doc


def validate_case_json(path: Path) -> str:
    doc = read_json(path)
    required = {"provisional_cmcs", "provisional_disease", "genes", "detected_variants_summary", "case_facts"}
    issues = []
    missing = sorted(required - set(doc))
    unexpected = sorted(set(doc) - required)
    if missing:
        issues.append(
            f"Top level — Problem: missing field(s): {', '.join(missing)}. "
            "Required fix: add every missing field and return the complete case.json object."
        )
    if unexpected:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected)}. "
            f"Required fix: remove them; allowed fields are {sorted(required)!r}."
        )

    cmcs = doc.get("provisional_cmcs")
    if not isinstance(cmcs, list):
        issues.append(
            f"provisional_cmcs — Problem: expected a non-empty list, received {cmcs!r}. "
            "Required fix: return one or more exact allowed provisional CMC strings."
        )
    elif not cmcs:
        issues.append(
            "provisional_cmcs — Problem: list is empty. Required fix: supply at least one exact allowed provisional CMC string."
        )
    else:
        seen = set()
        for i, cmc in enumerate(cmcs):
            if not isinstance(cmc, str) or cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                issues.append(
                    f"provisional_cmcs[{i}] — Problem: {cmc!r} is not an exact allowed CMC. "
                    "Required fix: replace it with one exact allowed provisional CMC supplied in the prompt."
                )
            if isinstance(cmc, str) and cmc in seen:
                issues.append(
                    f"provisional_cmcs[{i}] — Problem: duplicate CMC {cmc!r}. Required fix: keep each CMC once."
                )
            if isinstance(cmc, str):
                seen.add(cmc)

    genes = doc.get("genes")
    if not isinstance(genes, list):
        issues.append(
            f"genes — Problem: expected a list, received {genes!r}. Required fix: return a JSON list; [] is valid when no genes are present."
        )
    else:
        seen = set()
        for i, gene in enumerate(genes):
            if not isinstance(gene, str) or not gene.strip() or gene != gene.upper():
                issues.append(
                    f"genes[{i}] — Problem: expected a non-empty uppercase gene symbol, received {gene!r}. "
                    "Required fix: use the canonical uppercase gene symbol only."
                )
            if isinstance(gene, str) and gene in seen:
                issues.append(
                    f"genes[{i}] — Problem: duplicate gene {gene!r}. Required fix: list each gene once."
                )
            if isinstance(gene, str):
                seen.add(gene)

    for key in ("provisional_disease", "detected_variants_summary"):
        value = doc.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                f"{key} — Problem: expected a non-empty string, received {value!r}. Required fix: supply a source-faithful non-empty string."
            )

    facts = doc.get("case_facts")
    if not isinstance(facts, list):
        issues.append(
            f"case_facts — Problem: expected a list, received {facts!r}. Required fix: return a JSON list of fact objects."
        )
    else:
        ids = set()
        for i, row in enumerate(facts):
            location = f"case_facts[{i}]"
            required_row = {"fact_id", "kind", "value"}
            if not isinstance(row, dict):
                issues.append(
                    f"{location} — Problem: expected an object, received {row!r}. Required fix: return an object containing exactly fact_id, kind and value."
                )
                continue
            missing_row = sorted(required_row - set(row))
            unexpected_row = sorted(set(row) - required_row)
            if missing_row:
                issues.append(
                    f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s)."
                )
            if unexpected_row:
                issues.append(
                    f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. "
                    "Required fix: remove them; only fact_id, kind and value are allowed."
                )
            for key in ("fact_id", "kind", "value"):
                value = row.get(key)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        f"{location}.{key} — Problem: expected a non-empty string, received {value!r}. Required fix: supply a non-empty string."
                    )
            fact_id = row.get("fact_id")
            if isinstance(fact_id, str) and fact_id in ids:
                issues.append(
                    f"{location}.fact_id — Problem: duplicate ID {fact_id!r}. Required fix: give every case fact a unique fact_id."
                )
            if isinstance(fact_id, str):
                ids.add(fact_id)
    _raise_issues("case.json", issues)
    return "case.json validated"


def parse_yaml_mapping(path: Path) -> dict:
    text, _repairs = _read_text_with_syntax_repairs(path, format_name="YAML")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValueError(
            f"YAML — Problem: parser error in {path}{where}: {problem}. Required fix: return one complete syntactically "
            "valid YAML mapping only, with no Markdown fence or commentary."
        ) from exc
    if not isinstance(doc, dict):
        raise ValueError(
            f"Top level — Problem: expected one YAML mapping in {path}, received {type(doc).__name__}. "
            "Required fix: return the complete requested YAML object only."
        )
    return doc


def validate_diagnosis_state(path: Path, *, final: bool = False, final_config: dict | None = None, reviewed: dict | None = None) -> str:
    doc = parse_yaml_mapping(path)
    if final:
        validate_diagnosis_final(doc, reviewed or {}, final_config or {})
        return "diagnosis final state validated"
    required = {"provisional_cmcs", "diagnoses", "facts", "uncertainties"}
    issues = []
    missing = sorted(required - set(doc))
    unexpected = sorted(set(doc) - required)
    if missing:
        issues.append(
            f"Top level — Problem: missing field(s): {', '.join(missing)}. Required fix: add every missing field."
        )
    if unexpected:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected)}. "
            "Required fix: remove them; only provisional_cmcs, diagnoses, facts and uncertainties are allowed."
        )

    cmcs = doc.get("provisional_cmcs")
    if not isinstance(cmcs, list):
        issues.append(
            f"provisional_cmcs — Problem: expected a non-empty list, received {cmcs!r}. "
            "Required fix: return one or more exact allowed provisional CMC strings."
        )
    elif not cmcs:
        issues.append(
            "provisional_cmcs — Problem: list is empty. Required fix: supply at least one exact allowed provisional CMC string."
        )
    else:
        seen = set()
        for i, cmc in enumerate(cmcs):
            if not isinstance(cmc, str) or cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                issues.append(
                    f"provisional_cmcs[{i}] — Problem: {cmc!r} is not an allowed CMC. "
                    "Required fix: replace it with an exact allowed provisional CMC supplied in the prompt."
                )
            if isinstance(cmc, str) and cmc in seen:
                issues.append(
                    f"provisional_cmcs[{i}] — Problem: duplicate CMC {cmc!r}. Required fix: keep each CMC once."
                )
            if isinstance(cmc, str):
                seen.add(cmc)

    diagnoses = doc.get("diagnoses")
    if not isinstance(diagnoses, list):
        issues.append(
            f"diagnoses — Problem: expected a non-empty list, received {diagnoses!r}. Required fix: return at least one paired WHO5/ICC diagnosis row."
        )
        diagnoses = []
    elif not diagnoses:
        issues.append(
            "diagnoses — Problem: list is empty. Required fix: return at least one paired WHO5/ICC diagnosis row."
        )
    statuses = {"established", "indeterminate", "not_established", "not_applicable"}
    for i, row in enumerate(diagnoses):
        loc = f"diagnoses[{i}]"
        required_row = {"schema_disease", "WHO5", "ICC", "materially_different"}
        if not isinstance(row, dict):
            issues.append(
                f"{loc} — Problem: expected an object, received {row!r}. Required fix: return exactly schema_disease, WHO5, ICC and materially_different."
            )
            continue
        missing_row = sorted(required_row - set(row))
        unexpected_row = sorted(set(row) - required_row)
        if missing_row:
            issues.append(f"{loc} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s).")
        if unexpected_row:
            issues.append(
                f"{loc} — Problem: unexpected field(s): {', '.join(unexpected_row)}. Required fix: remove them; return exactly schema_disease, WHO5, ICC and materially_different."
            )
        schema_disease = row.get("schema_disease")
        if not isinstance(schema_disease, str) or schema_disease not in vocab.CASE_DISEASE_SET or schema_disease == "MDS/AML":
            issues.append(
                f"{loc}.schema_disease — Problem: {schema_disease!r} is not an allowed WHO5 routing value. "
                "Required fix: use one exact allowed WHO5 schema_disease supplied in the prompt; ICC-only MDS/AML cannot control routing."
            )
        if not isinstance(row.get("materially_different"), bool):
            issues.append(
                f"{loc}.materially_different — Problem: expected a boolean, received {row.get('materially_different')!r}. Required fix: use true or false."
            )
        for classifier in ("WHO5", "ICC"):
            outcome = row.get(classifier)
            if not isinstance(outcome, dict):
                issues.append(
                    f"{loc}.{classifier} — Problem: expected an object containing exactly status and diagnosis, received {outcome!r}. "
                    "Required fix: return both configured fields only."
                )
                continue
            missing_outcome = sorted({"status", "diagnosis"} - set(outcome))
            unexpected_outcome = sorted(set(outcome) - {"status", "diagnosis"})
            if missing_outcome:
                issues.append(
                    f"{loc}.{classifier} — Problem: missing field(s): {', '.join(missing_outcome)}. Required fix: add status and diagnosis as needed."
                )
            if unexpected_outcome:
                issues.append(
                    f"{loc}.{classifier} — Problem: unexpected field(s): {', '.join(unexpected_outcome)}. Required fix: remove them; only status and diagnosis are allowed."
                )
            status = outcome.get("status")
            diagnosis = outcome.get("diagnosis")
            if status not in statuses:
                issues.append(
                    f"{loc}.{classifier}.status — Problem: {status!r} is invalid. Required fix: use one of {sorted(statuses)!r}."
                )
            if diagnosis is not None and (not isinstance(diagnosis, str) or not diagnosis.strip()):
                issues.append(
                    f"{loc}.{classifier}.diagnosis — Problem: expected null or a non-empty string, received {diagnosis!r}. "
                    "Required fix: supply the candidate/assigned diagnosis or null when none applies."
                )
            if status == "established" and diagnosis is None:
                issues.append(
                    f"{loc}.{classifier}.diagnosis — Problem: status is established but diagnosis is null. Required fix: supply the established diagnostic wording."
                )

    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        rows = doc.get(field)
        if not isinstance(rows, list):
            issues.append(
                f"{field} — Problem: expected a list, received {rows!r}. Required fix: return a YAML list; [] is valid."
            )
            continue
        for i, row in enumerate(rows):
            location = f"{field}[{i}]"
            required_row = {text_key, "reason"}
            if not isinstance(row, dict):
                issues.append(
                    f"{location} — Problem: expected an object, received {row!r}. Required fix: return both {text_key} and reason."
                )
                continue
            missing_row = sorted(required_row - set(row))
            unexpected_row = sorted(set(row) - required_row)
            if missing_row:
                issues.append(f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s).")
            if unexpected_row:
                issues.append(
                    f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. Required fix: remove them; only {text_key} and reason are allowed."
                )
            for key in (text_key, "reason"):
                value = row.get(key)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        f"{location}.{key} — Problem: blank or not a string. Required fix: supply a non-empty string."
                    )
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
    issues = []
    missing = sorted(required - set(doc))
    unexpected = sorted(set(doc) - required)
    if missing:
        issues.append(
            f"Final output — Problem: missing field(s): {', '.join(missing)}. Required fix: add every configured final field."
        )
    if unexpected:
        issues.append(
            f"Final output — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; configured fields are {sorted(required)!r}."
        )
    for key in (config.get("invariants") or {}).get("preserve_fields") or []:
        if doc.get(key) != reviewed.get(key):
            issues.append(
                f"Final output.{key} — Problem: the protected pre-final value was changed or omitted. "
                f"Required fix: copy {key} exactly from the supplied pre-final state."
            )
    fact_ids = {row["fact_id"] for row in reviewed.get("facts") or [] if isinstance(row, dict) and "fact_id" in row}
    uncertainty_ids = {row["uncertainty_id"] for row in reviewed.get("uncertainties") or [] if isinstance(row, dict) and "uncertainty_id" in row}
    all_ids = fact_ids | uncertainty_ids
    facts = doc.get("supporting_facts")
    if not isinstance(facts, list):
        issues.append(
            f"Final output.supporting_facts — Problem: expected a list, received {facts!r}. Required fix: return a YAML list."
        )
        facts = []
    for i, row in enumerate(facts):
        location = f"Final output.supporting_facts[{i}]"
        required_row = {"fact", "reason", "source_fact_ids"}
        if not isinstance(row, dict):
            issues.append(
                f"{location} — Problem: expected an object, received {row!r}. Required fix: return exactly fact, reason and source_fact_ids."
            )
            continue
        missing_row = sorted(required_row - set(row))
        unexpected_row = sorted(set(row) - required_row)
        if missing_row:
            issues.append(f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s).")
        if unexpected_row:
            issues.append(
                f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. Required fix: remove them; only fact, reason and source_fact_ids are allowed."
            )
        ids = row.get("source_fact_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or x not in fact_ids for x in ids):
            issues.append(
                f"{location}.source_fact_ids — Problem: invalid source IDs {ids!r}. Required fix: use one or more supplied PRE-FINAL-F IDs only."
            )
    uncertainties = doc.get("uncertainties")
    if not isinstance(uncertainties, list):
        issues.append(
            f"Final output.uncertainties — Problem: expected a list, received {uncertainties!r}. Required fix: return a YAML list; [] is valid only when no uncertainty remains."
        )
        uncertainties = []
    seen = set()
    for i, row in enumerate(uncertainties):
        location = f"Final output.uncertainties[{i}]"
        required_row = {"uncertainty", "reason", "source_ids"}
        if not isinstance(row, dict):
            issues.append(
                f"{location} — Problem: expected an object, received {row!r}. Required fix: return exactly uncertainty, reason and source_ids."
            )
            continue
        missing_row = sorted(required_row - set(row))
        unexpected_row = sorted(set(row) - required_row)
        if missing_row:
            issues.append(f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s).")
        if unexpected_row:
            issues.append(
                f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. Required fix: remove them; only uncertainty, reason and source_ids are allowed."
            )
        ids = row.get("source_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or x not in all_ids for x in ids):
            issues.append(
                f"{location}.source_ids — Problem: invalid source IDs {ids!r}. Required fix: use one or more supplied PRE-FINAL-F/PRE-FINAL-U IDs only."
            )
            continue
        seen.update(x for x in ids if x in uncertainty_ids)
    missing_uncertainty_sources = sorted(uncertainty_ids - seen)
    if (config.get("invariants") or {}).get("require_all_prior_uncertainties") and missing_uncertainty_sources:
        issues.append(
            "Final output.uncertainties — Problem: dropped pre-final uncertainty source(s): "
            + ", ".join(missing_uncertainty_sources)
            + ". Required fix: preserve every supplied PRE-FINAL-U source in at least one final uncertainty row."
        )
    if (config.get("invariants") or {}).get("prohibit_new_numeric_tokens"):
        before = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(reviewed, ensure_ascii=False)))
        after = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", json.dumps(doc, ensure_ascii=False)))
        extra = sorted(after - before)
        if extra:
            issues.append(
                "Final output — Problem: introduced new numeric token(s): "
                + ", ".join(extra)
                + ". Required fix: remove new numeric content and use only numeric tokens already present in the protected pre-final state."
            )
    _raise_issues("diagnosis final synthesis", issues)


def validate_domain_state(path: Path) -> str:
    doc = parse_yaml_mapping(path)
    required = {"facts", "uncertainties", "upstream_issues"}
    issues = []
    missing = sorted(required - set(doc))
    unexpected = sorted(set(doc) - required)
    if missing:
        issues.append(f"Top level — Problem: missing field(s): {', '.join(missing)}. Required fix: add every missing field.")
    if unexpected:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; only facts, uncertainties and upstream_issues are allowed."
        )
    specs = (("facts", "fact"), ("uncertainties", "uncertainty"), ("upstream_issues", "issue"))
    for field, text_key in specs:
        rows = doc.get(field)
        if not isinstance(rows, list):
            issues.append(
                f"{field} — Problem: expected a list, received {rows!r}. Required fix: return a YAML list; [] is valid."
            )
            continue
        for i, row in enumerate(rows):
            location = f"{field}[{i}]"
            required_row = {text_key, "reason"}
            if not isinstance(row, dict):
                issues.append(
                    f"{location} — Problem: expected an object, received {row!r}. Required fix: return exactly {text_key} and reason."
                )
                continue
            missing_row = sorted(required_row - set(row))
            unexpected_row = sorted(set(row) - required_row)
            if missing_row:
                issues.append(f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s).")
            if unexpected_row:
                issues.append(
                    f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. Required fix: remove them; only {text_key} and reason are allowed."
                )
            for key in (text_key, "reason"):
                value = row.get(key)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        f"{location}.{key} — Problem: blank or not a string. Required fix: supply a non-empty string."
                    )
            text_value = row.get(text_key)
            if field != "upstream_issues" and isinstance(text_value, str) and text_value.strip() and not text_value.rstrip().endswith("."):
                issues.append(
                    f"{location}.{text_key} — Problem: report-ready proposition does not end with a full stop. Required fix: end the complete proposition with '.'."
                )
    _raise_issues("downstream terrace state", issues)
    return "downstream terrace state validated"


def validate_domain_alignment(path: Path, state_path: Path, permitted_tags: set[str]) -> str:
    aligned = parse_yaml_mapping(path)
    state = parse_yaml_mapping(state_path)
    required = {"facts", "uncertainties"}
    issues = []
    missing = sorted(required - set(aligned))
    unexpected = sorted(set(aligned) - required)
    if missing:
        issues.append(f"Top level — Problem: missing field(s): {', '.join(missing)}. Required fix: add every missing field.")
    if unexpected:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; only facts and uncertainties are allowed."
        )
    tag_re = re.compile(r"(?:\[card:([0-9a-f]{12})\])+")
    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        source = state.get(field) or []
        rows = aligned.get(field)
        if not isinstance(rows, list):
            issues.append(
                f"{field} — Problem: expected {len(source)} rows, received {rows!r}. Required fix: return every source row once in the original order."
            )
            continue
        if len(rows) != len(source):
            issues.append(
                f"{field} — Problem: expected {len(source)} rows, received {len(rows)}. Required fix: return every source row once in the original order."
            )
        for i, (row, expected) in enumerate(zip(rows, source)):
            location = f"{field}[{i}]"
            required_row = {text_key, "reason", "citation"}
            if not isinstance(row, dict):
                issues.append(
                    f"{location} — Problem: expected an object, received {row!r}. Required fix: return exactly {text_key}, reason and citation."
                )
                continue
            missing_row = sorted(required_row - set(row))
            unexpected_row = sorted(set(row) - required_row)
            if missing_row:
                issues.append(f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add the missing field(s).")
            if unexpected_row:
                issues.append(
                    f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. Required fix: remove them; only {text_key}, reason and citation are allowed."
                )
            if row.get(text_key) != expected.get(text_key):
                issues.append(
                    f"{location}.{text_key} — Problem: clinical text changed. Required fix: copy the supplied {text_key} character-for-character."
                )
            if row.get("reason") != expected.get("reason"):
                issues.append(
                    f"{location}.reason — Problem: clinical reason changed. Required fix: copy the supplied reason character-for-character."
                )
            citation = row.get("citation")
            if citation is None:
                continue
            if not isinstance(citation, str) or tag_re.fullmatch(citation) is None:
                issues.append(
                    f"{location}.citation — Problem: invalid citation syntax {citation!r}. Required fix: use null or adjacent exact 12-hex runtime card tags such as [card:0123456789ab][card:abcdef012345]."
                )
                continue
            tags = re.findall(r"\[card:([0-9a-f]{12})\]", citation)
            unknown = sorted(set(tags) - permitted_tags)
            if unknown:
                issues.append(
                    f"{location}.citation — Problem: unpermitted tag(s): {', '.join(unknown)}. Required fix: use only supplied runtime card tags or null."
                )
            if len(tags) != len(set(tags)):
                issues.append(
                    f"{location}.citation — Problem: repeated card tag. Required fix: include each permitted tag once."
                )
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
