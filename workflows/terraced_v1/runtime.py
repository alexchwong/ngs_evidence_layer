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
    except OSError as exc:
        raise ValueError(
            f"invalid JSON {path}: could not read the model artifact ({exc}). "
            "Required fix: return the complete JSON artifact again."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON {path}: parser error at line {exc.lineno}, column {exc.colno}: {exc.msg}. "
            "Required fix: return one complete syntactically valid JSON object only, with no Markdown fence or commentary."
        ) from exc


def _raise_issues(context: str, issues: list[str]) -> None:
    if issues:
        rendered = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, start=1))
        raise ValueError(f"{context} failed validation with {len(issues)} issue(s):\n{rendered}")


def validate_case_input(work: Path) -> str:
    doc = _load_json(Path(work) / "case-input.json")
    expected = {"provisional_cmcs", "provisional_disease", "genes", "case_facts"}
    issues = []
    if not isinstance(doc, dict):
        _raise_issues(
            "case-input.json",
            [
                "Top level — Problem: expected one JSON object. "
                f"Received {type(doc).__name__}. Required fix: return one object containing exactly "
                "provisional_cmcs, provisional_disease, genes and case_facts."
            ],
        )
    missing = sorted(expected - set(doc))
    unexpected = sorted(set(doc) - expected)
    if missing:
        issues.append(
            "Top level — Problem: missing required field(s): " + ", ".join(missing) + ". "
            "Required fix: add every missing field."
        )
    if unexpected:
        issues.append(
            "Top level — Problem: unexpected field(s): " + ", ".join(unexpected) + ". "
            "Required fix: remove these fields; only provisional_cmcs, provisional_disease, genes and case_facts are allowed."
        )

    if "genes" in doc:
        genes = doc["genes"]
        if not isinstance(genes, list):
            issues.append(
                f"genes — Problem: expected a list, received {type(genes).__name__}. "
                "Required fix: return a list of unique non-empty uppercase gene symbols."
            )
        else:
            seen_genes = set()
            for index, gene in enumerate(genes):
                if not isinstance(gene, str) or not gene.strip() or gene != gene.upper():
                    issues.append(
                        f"genes[{index}] — Problem: {gene!r} is not a non-empty uppercase gene symbol. "
                        "Required fix: replace it with the exact uppercase reported gene symbol."
                    )
                if isinstance(gene, str):
                    if gene in seen_genes:
                        issues.append(
                            f"genes[{index}] — Problem: duplicate gene {gene!r}. Required fix: keep each reported gene once."
                        )
                    else:
                        seen_genes.add(gene)

    if "provisional_cmcs" in doc:
        cmcs = doc["provisional_cmcs"]
        if not isinstance(cmcs, list):
            issues.append(
                f"provisional_cmcs — Problem: expected a non-empty list, received {type(cmcs).__name__}. "
                "Required fix: return one or more exact allowed CMC strings."
            )
        elif not cmcs:
            issues.append(
                "provisional_cmcs — Problem: list is empty. Required fix: supply at least one exact allowed CMC string."
            )
        else:
            seen = set()
            for index, cmc in enumerate(cmcs):
                if not isinstance(cmc, str):
                    issues.append(
                        f"provisional_cmcs[{index}] — Problem: expected an allowed CMC string, received {cmc!r}. "
                        "Required fix: replace it with an exact value from case-major-categories.json."
                    )
                    continue
                if cmc in seen:
                    issues.append(
                        f"provisional_cmcs[{index}] — Problem: duplicate CMC {cmc!r}. Required fix: keep each CMC once."
                    )
                else:
                    seen.add(cmc)
                if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                    issues.append(
                        f"provisional_cmcs[{index}] — Problem: {cmc!r} is not an allowed CMC. "
                        "Required fix: replace it with an exact value from case-major-categories.json."
                    )

    if "provisional_disease" in doc:
        disease = doc["provisional_disease"]
        if not isinstance(disease, str) or not disease.strip():
            issues.append(
                "provisional_disease — Problem: value is blank or not a string. "
                "Required fix: preserve the supplied clinicopathological diagnostic wording as a non-empty string."
            )

    if "case_facts" in doc:
        facts = doc["case_facts"]
        if not isinstance(facts, list):
            issues.append(
                f"case_facts — Problem: expected a non-empty list, received {type(facts).__name__}. "
                "Required fix: return the material patient facts as a list of objects."
            )
        elif not facts:
            issues.append(
                "case_facts — Problem: list is empty. Required fix: include the material patient-level facts from the case."
            )
        else:
            ids = []
            for index, fact in enumerate(facts):
                if not isinstance(fact, dict):
                    issues.append(
                        f"case_facts[{index}] — Problem: expected an object, received {fact!r}. "
                        "Required fix: return a fact object containing a non-empty fact_id."
                    )
                    continue
                fact_id = fact.get("fact_id")
                if not isinstance(fact_id, str) or not fact_id.strip():
                    issues.append(
                        f"case_facts[{index}].fact_id — Problem: missing or blank. "
                        "Required fix: supply a unique non-empty string fact_id."
                    )
                elif fact_id in ids:
                    issues.append(
                        f"case_facts[{index}].fact_id — Problem: duplicate value {fact_id!r}. "
                        "Required fix: give every case fact a unique fact_id."
                    )
                else:
                    ids.append(fact_id)
    _raise_issues("case-input.json", issues)
    return "case-input.json validated"


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"invalid YAML {path}: could not read the model artifact ({exc}). "
            "Required fix: return the complete YAML artifact again."
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValueError(
            f"invalid YAML {path}: parser error{where}: {problem}. "
            "Required fix: return one complete syntactically valid YAML artifact only, with no Markdown fence or commentary."
        ) from exc


def _fact_rows(rows, *, aligned: bool, context: str) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError(
            f"{context} facts failed validation with 1 issue(s):\n"
            f"1. {context} facts — Problem: expected a YAML list, received {type(rows).__name__}. "
            "Required fix: return a YAML list of fact/reason rows" + (" with citation fields." if aligned else ".")
        )
    expected = {"fact", "reason", "citation"} if aligned else {"fact", "reason"}
    issues = []
    for index, row in enumerate(rows, start=1):
        location = f"{context} fact {index}"
        if not isinstance(row, dict):
            issues.append(
                f"{location} — Problem: expected an object, received {row!r}. Required fix: return an object containing exactly "
                + ", ".join(sorted(expected)) + "."
            )
            continue
        missing = sorted(expected - set(row))
        unexpected = sorted(set(row) - expected)
        if missing:
            issues.append(
                f"{location} — Problem: missing field(s): {', '.join(missing)}. Required fix: add the missing field(s)."
            )
        if unexpected:
            issues.append(
                f"{location} — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; allowed fields are "
                + ", ".join(sorted(expected)) + "."
            )
        fact = row.get("fact")
        reason = row.get("reason")
        if "fact" in row and (not isinstance(fact, str) or not fact.strip()):
            issues.append(f"{location}.fact — Problem: blank or not a string. Required fix: supply the complete non-empty fact text.")
        if "reason" in row and (not isinstance(reason, str) or not reason.strip()):
            issues.append(f"{location}.reason — Problem: blank or not a string. Required fix: supply the complete non-empty reason text.")
        if isinstance(fact, str) and CARD_RE.search(fact):
            issues.append(f"{location}.fact — Problem: embeds a runtime card tag. Required fix: remove card tags from fact text.")
        if isinstance(reason, str) and CARD_RE.search(reason):
            issues.append(f"{location}.reason — Problem: embeds a runtime card tag. Required fix: remove card tags from reason text.")
        if aligned and "citation" in row:
            citation = row.get("citation")
            if citation is not None and (not isinstance(citation, str) or CITATION_RE.fullmatch(citation) is None):
                issues.append(
                    f"{location}.citation — Problem: {citation!r} is not null or adjacent runtime card tags. "
                    "Required fix: use null or only adjacent tags such as [card:abcdef][card:123456]."
                )
    _raise_issues(f"{context} facts", issues)
    return rows


def _validate_diagnosis_doc(doc, *, aligned: bool, final: bool) -> dict:
    expected = {"provisional_cmcs", "diagnoses", "facts"}
    issues = []
    if not isinstance(doc, dict):
        _raise_issues(
            "diagnosis state",
            [
                "Top level — Problem: expected a YAML object. "
                f"Received {type(doc).__name__}. Required fix: return one object containing exactly provisional_cmcs, diagnoses and facts."
            ],
        )
    missing = sorted(expected - set(doc))
    unexpected = sorted(set(doc) - expected)
    if missing:
        issues.append(f"Top level — Problem: missing field(s): {', '.join(missing)}. Required fix: add every missing field.")
    if unexpected:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected)}. "
            "Required fix: remove them; only provisional_cmcs, diagnoses and facts are allowed."
        )

    if "provisional_cmcs" in doc:
        cmcs = doc["provisional_cmcs"]
        if not isinstance(cmcs, list):
            issues.append(
                f"provisional_cmcs — Problem: expected a non-empty list, received {type(cmcs).__name__}. "
                "Required fix: return one or more exact allowed CMC strings."
            )
        elif not cmcs:
            issues.append("provisional_cmcs — Problem: list is empty. Required fix: supply at least one exact allowed CMC string.")
        else:
            seen = set()
            for index, cmc in enumerate(cmcs):
                if not isinstance(cmc, str):
                    issues.append(
                        f"provisional_cmcs[{index}] — Problem: expected an allowed CMC string, received {cmc!r}. "
                        "Required fix: replace it with an exact allowed CMC value."
                    )
                    continue
                if cmc in seen:
                    issues.append(f"provisional_cmcs[{index}] — Problem: duplicate CMC {cmc!r}. Required fix: keep each CMC once.")
                else:
                    seen.add(cmc)
                if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                    issues.append(
                        f"provisional_cmcs[{index}] — Problem: {cmc!r} is not an allowed CMC. "
                        "Required fix: replace it with an exact allowed CMC value."
                    )

    if "diagnoses" in doc:
        diagnoses = doc["diagnoses"]
        if not isinstance(diagnoses, list):
            issues.append(
                f"diagnoses — Problem: expected a list, received {type(diagnoses).__name__}. "
                "Required fix: return a list of WHO5 routing diagnoses."
            )
        else:
            if final and not diagnoses:
                issues.append("diagnoses — Problem: final diagnostic terrace accepted no diagnosis. Required fix: include at least one WHO5 diagnosis.")
            for index, row in enumerate(diagnoses):
                location = f"diagnoses[{index}]"
                if not isinstance(row, dict):
                    issues.append(
                        f"{location} — Problem: expected an object, received {row!r}. "
                        "Required fix: return an object containing exactly schema_disease and narrow_diagnosis."
                    )
                    continue
                row_expected = {"schema_disease", "narrow_diagnosis"}
                missing_row = sorted(row_expected - set(row))
                unexpected_row = sorted(set(row) - row_expected)
                if missing_row:
                    issues.append(f"{location} — Problem: missing field(s): {', '.join(missing_row)}. Required fix: add them.")
                if unexpected_row:
                    issues.append(
                        f"{location} — Problem: unexpected field(s): {', '.join(unexpected_row)}. "
                        "Required fix: remove them; only schema_disease and narrow_diagnosis are allowed."
                    )
                if "schema_disease" in row:
                    disease = row["schema_disease"]
                    if not isinstance(disease, str):
                        issues.append(
                            f"{location}.schema_disease — Problem: expected a canonical disease string, received {disease!r}. "
                            "Required fix: use one exact value from allowed-schema-diseases.json."
                        )
                    elif disease in WHO5_EXCLUDED_SCHEMA_DISEASES:
                        issues.append(
                            f"{location}.schema_disease — Problem: {disease!r} is ICC-only and cannot be the accepted WHO5 routing diagnosis. "
                            "Required fix: use the corresponding WHO5 diagnosis/routing value from allowed-schema-diseases.json."
                        )
                    elif disease not in vocab.CASE_DISEASE_SET:
                        issues.append(
                            f"{location}.schema_disease — Problem: {disease!r} is not canonical. "
                            "Required fix: use one exact value from allowed-schema-diseases.json."
                        )
                if "narrow_diagnosis" in row and (
                    not isinstance(row["narrow_diagnosis"], str) or not row["narrow_diagnosis"].strip()
                ):
                    issues.append(
                        f"{location}.narrow_diagnosis — Problem: blank or not a string. "
                        "Required fix: supply non-empty WHO5 diagnostic wording."
                    )

    if "facts" in doc:
        try:
            _fact_rows(doc["facts"], aligned=aligned, context="diagnosis")
        except ValueError as exc:
            lines = str(exc).splitlines()
            nested = lines[1:] if len(lines) > 1 else lines
            issues.extend(re.sub(r"^\d+\.\s+", "", line) for line in nested)
    _raise_issues("diagnosis state", issues)
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
    expected = {"pass", "issues"}
    issues = []
    if not isinstance(doc, dict):
        _raise_issues(
            "semantic review",
            [
                "Top level — Problem: expected one JSON object. "
                f"Received {type(doc).__name__}. Required fix: return exactly pass and issues."
            ],
        )
    missing = sorted(expected - set(doc))
    unexpected = sorted(set(doc) - expected)
    if missing:
        issues.append(f"Top level — Problem: missing field(s): {', '.join(missing)}. Required fix: add every missing field.")
    if unexpected:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; only pass and issues are allowed."
        )
    valid_pass = isinstance(doc.get("pass"), bool) if "pass" in doc else False
    if "pass" in doc and not valid_pass:
        issues.append(
            f"pass — Problem: expected true or false, received {doc.get('pass')!r}. Required fix: use a JSON boolean."
        )
    valid_issue_list = isinstance(doc.get("issues"), list) if "issues" in doc else False
    valid_issue_strings = False
    if "issues" in doc and not valid_issue_list:
        issues.append(
            f"issues — Problem: expected a list, received {type(doc.get('issues')).__name__}. "
            "Required fix: return a JSON list of concise actionable issue strings."
        )
    elif valid_issue_list:
        valid_issue_strings = True
        for index, value in enumerate(doc["issues"]):
            if not isinstance(value, str) or not value.strip():
                valid_issue_strings = False
                issues.append(
                    f"issues[{index}] — Problem: issue is blank or not a string ({value!r}). "
                    "Required fix: provide a non-empty actionable description of the semantic defect."
                )
    if valid_pass and valid_issue_list and valid_issue_strings:
        if doc["pass"] and doc["issues"]:
            issues.append("pass/issues — Problem: pass is true but issues is non-empty. Required fix: when pass is true, return issues: [].")
        if not doc["pass"] and not doc["issues"]:
            issues.append(
                "pass/issues — Problem: pass is false but no issue is identified. "
                "Required fix: include at least one non-empty actionable semantic defect in issues."
            )
    _raise_issues("semantic review", issues)
    return doc["pass"], doc["issues"]


def known_tags_from_evidence(path: Path) -> set[str]:
    text = Path(path).read_text(encoding="utf-8")
    return set(CARD_RE.findall(text))


def validate_alignment(source_path: Path, aligned_path: Path, domain: str, evidence_path: Path) -> str:
    source = _load_yaml(Path(source_path))
    aligned = _load_yaml(Path(aligned_path))
    # Source is previously accepted workflow state. The model-owned aligned artifact must first be structurally usable.
    validate_category_answer(source_path, domain, final=True, aligned=False)
    validate_category_answer(aligned_path, domain, final=True, aligned=True)
    issues = []
    if domain == "diagnosis":
        if source["provisional_cmcs"] != aligned["provisional_cmcs"]:
            issues.append(
                "provisional_cmcs — Problem: evidence alignment changed diagnostic routing state. "
                "Required fix: copy provisional_cmcs character-for-character from the supplied final diagnosis answer."
            )
        if source["diagnoses"] != aligned["diagnoses"]:
            issues.append(
                "diagnoses — Problem: evidence alignment changed accepted diagnoses. "
                "Required fix: copy diagnoses character-for-character from the supplied final diagnosis answer."
            )
        source_rows, aligned_rows = source["facts"], aligned["facts"]
    else:
        source_rows, aligned_rows = source, aligned
    if len(source_rows) != len(aligned_rows):
        issues.append(
            f"facts — Problem: evidence alignment changed fact count from {len(source_rows)} to {len(aligned_rows)}. "
            "Required fix: return exactly the same fact rows in the same order and add only citation."
        )
    known = known_tags_from_evidence(evidence_path)
    for index, (before, after) in enumerate(zip(source_rows, aligned_rows), start=1):
        if before["fact"] != after["fact"]:
            issues.append(
                f"fact {index}.fact — Problem: evidence alignment changed the accepted fact text. "
                "Required fix: restore the supplied fact character-for-character."
            )
        if before["reason"] != after["reason"]:
            issues.append(
                f"fact {index}.reason — Problem: evidence alignment changed the accepted reason text. "
                "Required fix: restore the supplied reason character-for-character."
            )
        citation = after["citation"]
        if citation:
            unknown = sorted(set(CARD_RE.findall(citation)) - known)
            if unknown:
                issues.append(
                    f"fact {index}.citation — Problem: cites runtime tag(s) not present in permitted evidence: {', '.join(unknown)}. "
                    "Required fix: remove those tags and use only exact tags from the supplied evidence, or null when unsupported."
                )
    _raise_issues("evidence alignment", issues)
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
