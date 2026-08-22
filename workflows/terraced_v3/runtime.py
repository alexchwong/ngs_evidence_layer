"""Deterministic state, validation and report helpers for terraced-v3."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

from scripts import vocab
from scripts.core.validated_model_task import ValidationFailure, ValidationIssue, fail
from workflows.terraced_v3 import layout

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
WHO5_EXCLUDED_SCHEMA_DISEASES = {"MDS/AML"}
VALIDATION_MODES = {"nel-validate", "nel-validate-function", "nel-validate-brief"}
CARD_TAG_RE = re.compile(r"\[card:([0-9a-f]{12})\]")
CARD_TAGS_RE = re.compile(r"(?:\[card:[0-9a-f]{12}\])+")
_BARE_CARD_TAG_RE = re.compile(r"(?:card:)?([0-9a-f]{12})")


def _canonical_card_tag(value):
    """Return canonical runtime card-tag syntax for an unambiguous scalar.

    This is representation-only normalization.  Whether the resulting tag was
    actually supplied to the task remains the responsibility of the existing
    task validator.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    match = CARD_TAG_RE.fullmatch(value)
    if match:
        return value
    match = _BARE_CARD_TAG_RE.fullmatch(value)
    if match:
        return f"[card:{match.group(1)}]"
    return None


def normalize_model_card_tag_syntax(text: str, *, format_name: str = "yaml") -> tuple[str, list[str]]:
    """Canonicalize model card-tag scalars without changing clinical content.

    Accepted representations include bare 12-character runtime hashes and
    ``card:<hash>``.  They are rewritten only in known card-tag fields.  The
    subsequent validator still requires an exact match to a card supplied to
    that task, so an invented/undrawn hash is never accepted by this fixer.
    """
    if format_name == "yaml":
        doc = yaml.safe_load(text)
    elif format_name == "json":
        doc = json.loads(text)
    else:
        return text, []

    repairs: list[str] = []

    def walk(value, path=""):
        if isinstance(value, dict):
            for key, child in list(value.items()):
                child_path = f"{path}.{key}" if path else str(key)
                if key == "card_tag":
                    canonical = _canonical_card_tag(child)
                    if canonical is not None and canonical != child:
                        value[key] = canonical
                        repairs.append(f"normalised bare runtime card hash at {child_path}")
                elif key == "candidate_card_tags" or str(key).endswith("_candidate_card_tags"):
                    if isinstance(child, list):
                        for i, item in enumerate(child):
                            canonical = _canonical_card_tag(item)
                            if canonical is not None and canonical != item:
                                child[i] = canonical
                                repairs.append(f"normalised bare runtime card hash at {child_path}[{i}]")
                else:
                    walk(child, child_path)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(doc)
    if not repairs:
        return text, []
    if format_name == "yaml":
        rendered = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)
    else:
        rendered = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return rendered, repairs
HEADINGS = {
    "**Diagnosis**": "diagnosis",
    "**Prognosis**": "prognosis",
    "**Treatment Implications**": "treatment",
    "**MRD**": "biomarker",
    "**Germline**": "germline",
}
DOMAIN_HEADINGS = {value: key for key, value in HEADINGS.items()}


def setup_assets(work_dir: Path, *, mode: str, case_id: str | None = None) -> None:
    work = Path(work_dir)
    layout.ensure_dirs(work)
    panel_root = work / "ngs-panel-scope.md"
    panel_out = layout.setup(work, "ngs-panel-scope.md", existing=False)
    if panel_root.is_file() and panel_root != panel_out:
        shutil.move(str(panel_root), str(panel_out))

    cmc_root = work / "case-major-categories.json"
    cmc_out = layout.setup(work, "case-major-categories.json", existing=False)
    cmc_out.write_text(
        json.dumps(
            {
                "case_major_categories": list(vocab.CASE_MAJOR_CATEGORIES),
                "instruction": (
                    "bootstrap_cmcs are retrieval scaffolds only. Authoritative CMCs are later derived "
                    "deterministically from validated WHO5 schema diseases."
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
    layout.setup(work, "allowed-schema-diseases.json", existing=False).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allowed_schema_diseases": allowed,
                "instruction": "WHO5 schema disease controls deterministic CMC routing; ICC never routes evidence.",
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
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


def parse_json_mapping(text: str, context: str = "JSON") -> dict:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailure(
            context,
            [ValidationIssue(
                "JSON",
                f"parser error at line {exc.lineno}, column {exc.colno}: {exc.msg}",
                "return one complete syntactically valid JSON object only",
                repair_class="syntax",
            )],
        ) from exc
    if not isinstance(doc, dict):
        raise ValidationFailure(
            context,
            [ValidationIssue("Top level", f"expected an object, received {type(doc).__name__}", "return one JSON object", repair_class="shape")],
        )
    return doc


def parse_yaml_mapping(text: str, context: str = "YAML") -> dict:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValidationFailure(
            context,
            [ValidationIssue("YAML", f"parser error{where}: {problem}", "return one complete syntactically valid YAML mapping only", repair_class="syntax")],
        ) from exc
    if not isinstance(doc, dict):
        raise ValidationFailure(
            context,
            [ValidationIssue("Top level", f"expected a mapping, received {type(doc).__name__}", "return one YAML mapping", repair_class="shape")],
        )
    return doc


def _exact_keys(issues: list[ValidationIssue], doc: dict, expected: set[str], path: str = "Top level") -> None:
    actual = set(doc)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        problem = []
        if missing:
            problem.append("missing " + ", ".join(missing))
        if extra:
            problem.append("unexpected " + ", ".join(extra))
        issues.append(ValidationIssue(path, "; ".join(problem), f"return exactly fields {sorted(expected)}", received=str(sorted(actual)), expected=str(sorted(expected))))


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_candidate_tags(issues: list[ValidationIssue], value, path: str, permitted: set[str]) -> None:
    if not isinstance(value, list):
        issues.append(ValidationIssue(path, f"expected a list, received {type(value).__name__}", "return a YAML list of exact supplied card tags"))
        return
    seen = set()
    for i, tag in enumerate(value):
        loc = f"{path}[{i}]"
        if not isinstance(tag, str) or CARD_TAGS_RE.fullmatch(tag) is None or len(CARD_TAG_RE.findall(tag)) != 1:
            issues.append(ValidationIssue(loc, f"invalid card tag {tag!r}", "use one exact supplied tag such as [card:0123456789ab]"))
            continue
        raw = CARD_TAG_RE.findall(tag)[0]
        if raw not in permitted:
            issues.append(ValidationIssue(loc, f"tag {tag} was not supplied to this task", "use only a supplied card tag or remove it"))
        if raw in seen:
            issues.append(ValidationIssue(loc, f"duplicate tag {tag}", "list each candidate card once"))
        seen.add(raw)


def validate_case_text(text: str) -> str:
    doc = parse_json_mapping(text, "structured case")
    expected = {"provisional_disease", "bootstrap_cmcs", "variants", "detected_variants_summary", "case_facts"}
    issues: list[ValidationIssue] = []
    _exact_keys(issues, doc, expected)
    if not _nonempty(doc.get("provisional_disease")):
        issues.append(ValidationIssue("provisional_disease", "blank or not a string", "return a faithful short clinicopathological provisional disease description"))
    cmcs = doc.get("bootstrap_cmcs")
    if not isinstance(cmcs, list) or not cmcs:
        issues.append(ValidationIssue("bootstrap_cmcs", "must be a non-empty list", "select one or more exact supplied CMC values from the clinicopathological/provisional disease family"))
    else:
        seen = set()
        for i, cmc in enumerate(cmcs):
            if cmc not in vocab.CASE_MAJOR_CATEGORY_SET:
                issues.append(ValidationIssue(f"bootstrap_cmcs[{i}]", f"unknown CMC {cmc!r}", "use an exact allowed CMC"))
            if cmc in seen:
                issues.append(ValidationIssue(f"bootstrap_cmcs[{i}]", f"duplicate CMC {cmc!r}", "list each CMC once"))
            seen.add(cmc)
    variants = doc.get("variants")
    if not isinstance(variants, list):
        issues.append(ValidationIssue("variants", f"expected a list, received {type(variants).__name__}", "return every detected NGS variant in case order"))
    else:
        for i, row in enumerate(variants, 1):
            loc = f"variants[{i-1}]"
            if not isinstance(row, dict):
                issues.append(ValidationIssue(loc, f"expected object, received {type(row).__name__}", "return variant_id, gene, description"))
                continue
            _exact_keys(issues, row, {"variant_id", "gene", "description"}, loc)
            expected_id = f"V{i}"
            if row.get("variant_id") != expected_id:
                issues.append(ValidationIssue(f"{loc}.variant_id", f"received {row.get('variant_id')!r}", f"use sequential stable ID {expected_id!r}"))
            gene = row.get("gene")
            if not _nonempty(gene) or gene != gene.upper():
                issues.append(ValidationIssue(f"{loc}.gene", f"invalid gene {gene!r}", "use the reported uppercase gene symbol"))
            if not _nonempty(row.get("description")):
                issues.append(ValidationIssue(f"{loc}.description", "blank or not a string", "preserve the complete reported variant description"))
    summary = doc.get("detected_variants_summary")
    if not _nonempty(summary):
        issues.append(ValidationIssue("detected_variants_summary", "blank or not a string", "return exactly one source-faithful sentence listing every detected NGS variant"))
    elif summary != summary.strip() or "\n" in summary or "\r" in summary:
        issues.append(ValidationIssue("detected_variants_summary", "must be exactly one physical line without surrounding whitespace", "return one clean invariant sentence"))
    elif not summary.endswith((".", "!", "?")):
        issues.append(ValidationIssue("detected_variants_summary", "sentence has no terminal punctuation", "end the invariant sentence with terminal punctuation"))
    if isinstance(summary, str) and isinstance(variants, list):
        for i, row in enumerate(variants):
            if not isinstance(row, dict):
                continue
            gene = row.get("gene")
            desc = row.get("description") or ""
            if isinstance(gene, str) and gene and gene not in summary:
                issues.append(ValidationIssue("detected_variants_summary", f"does not contain reported gene {gene!r} from variants[{i}]", "list every detected gene in the invariant sentence"))
            for pattern, label in ((r"(?:NM_\d+(?:\.\d+)?:)?c\.[^,; )]+", "coding HGVS"), (r"p\.\([^,;]+?\)", "protein HGVS"), (r"VAF\s*[^,;]+", "VAF")):
                match = re.search(pattern, str(desc), flags=re.IGNORECASE)
                if match and match.group(0) not in summary:
                    issues.append(ValidationIssue("detected_variants_summary", f"does not preserve supplied {label} {match.group(0)!r} from variants[{i}]", f"copy the supplied {label} exactly into the invariant sentence"))
    facts = doc.get("case_facts")
    if not isinstance(facts, list):
        issues.append(ValidationIssue("case_facts", f"expected list, received {type(facts).__name__}", "return case facts as a list"))
    else:
        for i, row in enumerate(facts, 1):
            loc = f"case_facts[{i-1}]"
            if not isinstance(row, dict):
                issues.append(ValidationIssue(loc, f"expected object, received {type(row).__name__}", "return fact_id, kind, value"))
                continue
            _exact_keys(issues, row, {"fact_id", "kind", "value"}, loc)
            expected_id = f"C{i}"
            if row.get("fact_id") != expected_id:
                issues.append(ValidationIssue(f"{loc}.fact_id", f"received {row.get('fact_id')!r}", f"use sequential stable ID {expected_id!r}"))
            for field in ("kind", "value"):
                if not _nonempty(row.get(field)):
                    issues.append(ValidationIssue(f"{loc}.{field}", "blank or not a string", "return a non-empty case-source value"))
    fail("structured case", issues)
    return "structured case validated"


def case_genes(case: dict) -> list[str]:
    genes = []
    for row in case.get("variants") or []:
        gene = row.get("gene")
        if isinstance(gene, str) and gene not in genes:
            genes.append(gene)
    return genes


def _validate_fact_reason_row(
    issues: list[ValidationIssue], row: dict, loc: str, diagnosis_ids: set[str], permitted_tags: set[str]
) -> None:
    _exact_keys(issues, row, {"diagnosis_ids", "fact", "reason", "candidate_card_tags"}, loc)
    ids = row.get("diagnosis_ids")
    if not isinstance(ids, list) or not ids:
        issues.append(ValidationIssue(f"{loc}.diagnosis_ids", "must be a non-empty list", "scope the fact to one or more returned diagnosis IDs"))
    elif any(x not in diagnosis_ids for x in ids):
        issues.append(ValidationIssue(f"{loc}.diagnosis_ids", f"contains unknown ID(s) {ids!r}", "use only diagnosis IDs returned in this same artifact"))
    if not _nonempty(row.get("fact")) or not str(row.get("fact", "")).rstrip().endswith("."):
        issues.append(ValidationIssue(f"{loc}.fact", "must be non-empty reportable prose ending with a full stop", "return one complete patient-level proposition ending in '.'"))
    if not _nonempty(row.get("reason")):
        issues.append(ValidationIssue(f"{loc}.reason", "blank or not a string", "return a short auditable clinical justification"))
    _validate_candidate_tags(issues, row.get("candidate_card_tags"), f"{loc}.candidate_card_tags", permitted_tags)


def validate_who5_text(text: str, permitted_tags: set[str]) -> str:
    doc = parse_yaml_mapping(text, "WHO5 diagnosis")
    issues: list[ValidationIssue] = []
    _exact_keys(issues, doc, {"diagnoses", "supporting_facts", "contradicting_facts"})
    diagnoses = doc.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        issues.append(ValidationIssue("diagnoses", "must contain at least one diagnosis", "return every established or indeterminate WHO5 diagnosis"))
        diagnoses = []
    diagnosis_ids: set[str] = set()
    for i, row in enumerate(diagnoses, 1):
        loc = f"diagnoses[{i-1}]"
        if not isinstance(row, dict):
            issues.append(ValidationIssue(loc, f"expected object, received {type(row).__name__}", "return the complete diagnosis row"))
            continue
        _exact_keys(issues, row, {"diagnosis_id", "schema_disease", "status", "diagnosis", "fact", "reason", "candidate_card_tags"}, loc)
        expected_id = f"DX{i}"
        if row.get("diagnosis_id") != expected_id:
            issues.append(ValidationIssue(f"{loc}.diagnosis_id", f"received {row.get('diagnosis_id')!r}", f"use sequential ID {expected_id!r}"))
        diagnosis_ids.add(expected_id)
        disease = row.get("schema_disease")
        if disease not in vocab.CASE_DISEASE_SET or disease in WHO5_EXCLUDED_SCHEMA_DISEASES:
            issues.append(ValidationIssue(f"{loc}.schema_disease", f"invalid WHO5 routing disease {disease!r}", "use one exact supplied canonical WHO5 schema disease; MDS/AML is ICC-only"))
        if row.get("status") not in {"established", "indeterminate"}:
            issues.append(ValidationIssue(f"{loc}.status", f"invalid status {row.get('status')!r}", "use only established or indeterminate"))
        if not _nonempty(row.get("diagnosis")):
            issues.append(ValidationIssue(f"{loc}.diagnosis", "blank or not a string", "return the WHO5 diagnostic label"))
        if not _nonempty(row.get("fact")) or not str(row.get("fact", "")).rstrip().endswith("."):
            issues.append(ValidationIssue(f"{loc}.fact", "must be reportable prose ending with a full stop", "state the WHO5 diagnosis as a complete sentence ending in '.'"))
        if not _nonempty(row.get("reason")):
            issues.append(ValidationIssue(f"{loc}.reason", "blank or not a string", "return a short auditable clinical justification"))
        _validate_candidate_tags(issues, row.get("candidate_card_tags"), f"{loc}.candidate_card_tags", permitted_tags)
    for field in ("supporting_facts", "contradicting_facts"):
        rows = doc.get(field)
        if not isinstance(rows, list):
            issues.append(ValidationIssue(field, f"expected list, received {type(rows).__name__}", "return a YAML list; use [] when none"))
            continue
        for i, row in enumerate(rows):
            loc = f"{field}[{i}]"
            if not isinstance(row, dict):
                issues.append(ValidationIssue(loc, f"expected object, received {type(row).__name__}", "return the complete fact/reason row"))
                continue
            _validate_fact_reason_row(issues, row, loc, diagnosis_ids, permitted_tags)
    fail("WHO5 diagnosis", issues)
    return "WHO5 diagnosis validated"


def validate_icc_text(text: str, permitted_tags: set[str]) -> str:
    doc = parse_yaml_mapping(text, "ICC diagnosis")
    issues: list[ValidationIssue] = []
    _exact_keys(issues, doc, {"diagnoses"})
    rows = doc.get("diagnoses")
    if not isinstance(rows, list) or not rows:
        issues.append(ValidationIssue("diagnoses", "must contain at least one ICC diagnosis", "return every established or materially plausible ICC diagnosis"))
        rows = []
    for i, row in enumerate(rows, 1):
        loc = f"diagnoses[{i-1}]"
        if not isinstance(row, dict):
            issues.append(ValidationIssue(loc, f"expected object, received {type(row).__name__}", "return the complete ICC row"))
            continue
        _exact_keys(issues, row, {"diagnosis_id", "status", "diagnosis", "fact", "reason", "candidate_card_tags"}, loc)
        expected_id = f"ICC{i}"
        if row.get("diagnosis_id") != expected_id:
            issues.append(ValidationIssue(f"{loc}.diagnosis_id", f"received {row.get('diagnosis_id')!r}", f"use sequential ID {expected_id!r}"))
        if row.get("status") not in {"established", "indeterminate"}:
            issues.append(ValidationIssue(f"{loc}.status", f"invalid status {row.get('status')!r}", "use only established or indeterminate"))
        for field in ("diagnosis", "fact", "reason"):
            if not _nonempty(row.get(field)):
                issues.append(ValidationIssue(f"{loc}.{field}", "blank or not a string", "return a non-empty value"))
        if _nonempty(row.get("fact")) and not row["fact"].rstrip().endswith("."):
            issues.append(ValidationIssue(f"{loc}.fact", "does not end with a full stop", "end the complete reportable fact with '.'"))
        _validate_candidate_tags(issues, row.get("candidate_card_tags"), f"{loc}.candidate_card_tags", permitted_tags)
    fail("ICC diagnosis", issues)
    return "ICC diagnosis validated"


def active_who5_diagnoses(doc: dict) -> list[dict]:
    return [row for row in doc.get("diagnoses") or [] if row.get("status") in {"established", "indeterminate"}]


def derive_cmcs(doc: dict) -> list[str]:
    cmcs = []
    for row in active_who5_diagnoses(doc):
        disease = row.get("schema_disease")
        cmc = vocab.preferred_case_major_category(disease)
        if disease == vocab.NO_HAEMATOLOGICAL_MALIGNANCY:
            cmc = vocab.NO_HAEMATOLOGICAL_MALIGNANCY
        if not cmc:
            raise ValueError(f"WHO5 schema disease {disease!r} has no deterministic preferred CMC mapping")
        if cmc not in cmcs:
            cmcs.append(cmc)
    if not cmcs:
        raise ValueError("WHO5 state produced no active diagnosis from which to derive CMC")
    return cmcs


def who5_signature(doc: dict) -> tuple:
    return tuple(
        (
            row.get("schema_disease"),
            row.get("status"),
            " ".join(str(row.get("diagnosis") or "").split()).casefold(),
        )
        for row in active_who5_diagnoses(doc)
    )


def _surface_fields(
    issues: list[ValidationIssue], row: dict, loc: str, *, surface_key: str = "surface", fact_key: str = "fact", reason_key: str = "reason", tags_key: str = "candidate_card_tags", permitted_tags: set[str]
) -> None:
    surface = row.get(surface_key)
    if not isinstance(surface, bool):
        issues.append(ValidationIssue(f"{loc}.{surface_key}", f"expected boolean, received {surface!r}", "use true or false"))
        return
    fact = row.get(fact_key)
    reason = row.get(reason_key)
    if surface:
        if not _nonempty(fact) or not str(fact).rstrip().endswith("."):
            issues.append(ValidationIssue(f"{loc}.{fact_key}", "surface=true requires a complete fact ending with a full stop", "return reportable patient-level prose ending in '.'"))
        if not _nonempty(reason):
            issues.append(ValidationIssue(f"{loc}.{reason_key}", "surface=true requires a reason", "return a short auditable clinical justification"))
    else:
        if fact is not None or reason is not None:
            issues.append(ValidationIssue(loc, f"{surface_key}=false but fact/reason are not null", f"set {fact_key} and {reason_key} to null"))
    _validate_candidate_tags(issues, row.get(tags_key), f"{loc}.{tags_key}", permitted_tags)


def validate_domain_text(text: str, *, domain: str, spec: dict, permitted_tags: set[str]) -> str:
    doc = parse_yaml_mapping(text, f"{domain} task")
    issues: list[ValidationIssue] = []
    if domain == "prognosis":
        _exact_keys(issues, doc, {"decisions"})
        rows = doc.get("decisions")
        required = spec["required_pairs"]
        if not isinstance(rows, list):
            issues.append(ValidationIssue("decisions", f"expected list, received {type(rows).__name__}", "return one decision per required variant × diagnosis pair"))
            rows = []
        if len(rows) != len(required):
            issues.append(ValidationIssue("decisions", f"expected {len(required)} rows, received {len(rows)}", "return every required pair exactly once in supplied order"))
        for i, pair in enumerate(required):
            if i >= len(rows) or not isinstance(rows[i], dict):
                continue
            row = rows[i]; loc = f"decisions[{i}]"
            _exact_keys(issues, row, {"variant_id", "diagnosis_id", "effect", "scoring_system", "surface", "fact", "reason", "candidate_card_tags"}, loc)
            if (row.get("variant_id"), row.get("diagnosis_id")) != pair:
                issues.append(ValidationIssue(loc, f"wrong scope {(row.get('variant_id'), row.get('diagnosis_id'))!r}", f"use exact required pair {pair!r}"))
            if row.get("effect") not in {"favorable", "adverse", "neither"}:
                issues.append(ValidationIssue(f"{loc}.effect", f"invalid value {row.get('effect')!r}", "use favorable, adverse, or neither"))
            score = row.get("scoring_system")
            if score is not None and not _nonempty(score):
                issues.append(ValidationIssue(f"{loc}.scoring_system", f"invalid value {score!r}", "use a non-empty named system or null"))
            _surface_fields(issues, row, loc, permitted_tags=permitted_tags)
    elif domain == "treatment":
        _exact_keys(issues, doc, {"decisions"})
        rows = doc.get("decisions"); required = spec["required_pairs"]
        if not isinstance(rows, list):
            issues.append(ValidationIssue("decisions", f"expected list, received {type(rows).__name__}", "return one decision per required gene × diagnosis pair")); rows = []
        if len(rows) != len(required):
            issues.append(ValidationIssue("decisions", f"expected {len(required)} rows, received {len(rows)}", "return every required pair exactly once in supplied order"))
        fields = {"gene", "diagnosis_id", "drug_target", "target_surface", "target_fact", "target_reason", "target_candidate_card_tags", "drug_resistance", "resistance_surface", "resistance_fact", "resistance_reason", "resistance_candidate_card_tags"}
        for i, pair in enumerate(required):
            if i >= len(rows) or not isinstance(rows[i], dict): continue
            row=rows[i]; loc=f"decisions[{i}]"; _exact_keys(issues,row,fields,loc)
            if (row.get("gene"), row.get("diagnosis_id")) != pair:
                issues.append(ValidationIssue(loc, f"wrong scope {(row.get('gene'), row.get('diagnosis_id'))!r}", f"use exact required pair {pair!r}"))
            for key in ("drug_target", "drug_resistance"):
                if not isinstance(row.get(key), bool):
                    issues.append(ValidationIssue(f"{loc}.{key}", f"expected boolean, received {row.get(key)!r}", "use true or false"))
            _surface_fields(issues,row,loc,surface_key="target_surface",fact_key="target_fact",reason_key="target_reason",tags_key="target_candidate_card_tags",permitted_tags=permitted_tags)
            _surface_fields(issues,row,loc,surface_key="resistance_surface",fact_key="resistance_fact",reason_key="resistance_reason",tags_key="resistance_candidate_card_tags",permitted_tags=permitted_tags)
    elif domain == "biomarker":
        _exact_keys(issues, doc, {"decisions"})
        rows=doc.get("decisions"); required=spec["required_pairs"]
        if not isinstance(rows,list):
            issues.append(ValidationIssue("decisions",f"expected list, received {type(rows).__name__}","return one decision per required variant × diagnosis pair")); rows=[]
        if len(rows)!=len(required): issues.append(ValidationIssue("decisions",f"expected {len(required)} rows, received {len(rows)}","return every required pair exactly once in supplied order"))
        for i,pair in enumerate(required):
            if i>=len(rows) or not isinstance(rows[i],dict): continue
            row=rows[i]; loc=f"decisions[{i}]"; _exact_keys(issues,row,{"variant_id","diagnosis_id","mrd_usable","surface","fact","reason","candidate_card_tags"},loc)
            if (row.get("variant_id"),row.get("diagnosis_id"))!=pair: issues.append(ValidationIssue(loc,f"wrong scope {(row.get('variant_id'),row.get('diagnosis_id'))!r}",f"use exact required pair {pair!r}"))
            if not isinstance(row.get("mrd_usable"),bool): issues.append(ValidationIssue(f"{loc}.mrd_usable",f"expected boolean, received {row.get('mrd_usable')!r}","use true or false"))
            _surface_fields(issues,row,loc,permitted_tags=permitted_tags)
    elif domain == "germline":
        _exact_keys(issues, doc, {"variant_decisions", "clinical_picture"})
        rows=doc.get("variant_decisions"); required=spec["required_variants"]
        if not isinstance(rows,list): issues.append(ValidationIssue("variant_decisions",f"expected list, received {type(rows).__name__}","return one decision per detected variant")); rows=[]
        if len(rows)!=len(required): issues.append(ValidationIssue("variant_decisions",f"expected {len(required)} rows, received {len(rows)}","return every required variant exactly once in supplied order"))
        for i,variant_id in enumerate(required):
            if i>=len(rows) or not isinstance(rows[i],dict): continue
            row=rows[i]; loc=f"variant_decisions[{i}]"; _exact_keys(issues,row,{"variant_id","potentially_germline","surface","fact","reason","candidate_card_tags"},loc)
            if row.get("variant_id")!=variant_id: issues.append(ValidationIssue(f"{loc}.variant_id",f"received {row.get('variant_id')!r}",f"use exact required variant {variant_id!r}"))
            if not isinstance(row.get("potentially_germline"),bool): issues.append(ValidationIssue(f"{loc}.potentially_germline",f"expected boolean, received {row.get('potentially_germline')!r}","use true or false"))
            _surface_fields(issues,row,loc,permitted_tags=permitted_tags)
        cp=doc.get("clinical_picture")
        if not isinstance(cp,dict): issues.append(ValidationIssue("clinical_picture",f"expected object, received {type(cp).__name__}","return supportive, surface, fact, reason, candidate_card_tags"))
        else:
            _exact_keys(issues,cp,{"supportive","surface","fact","reason","candidate_card_tags"},"clinical_picture")
            if cp.get("supportive") not in {True,False,"uncertain"}: issues.append(ValidationIssue("clinical_picture.supportive",f"invalid value {cp.get('supportive')!r}","use true, false, or uncertain"))
            _surface_fields(issues,cp,"clinical_picture",permitted_tags=permitted_tags)
    else:
        raise ValueError(f"unknown domain {domain!r}")
    fail(f"{domain} task", issues)
    return f"{domain} task validated"


def facts_from_who5(doc: dict) -> list[dict]:
    facts=[]
    for row in doc.get("diagnoses") or []:
        facts.append({
            "fact_id": f"who5-{row['diagnosis_id']}", "domain":"diagnosis",
            "subject":{"diagnosis_ids":[row['diagnosis_id']]},
            "decision":{"classifier":"WHO5","schema_disease":row["schema_disease"],"status":row["status"],"diagnosis":row["diagnosis"]},
            "fact":row["fact"],"reason":row["reason"],"candidate_card_tags":row["candidate_card_tags"],
        })
    for field,prefix,kind in (("supporting_facts","who5-support","supporting"),("contradicting_facts","who5-contradiction","contradicting")):
        for i,row in enumerate(doc.get(field) or [],1):
            facts.append({"fact_id":f"{prefix}-{i}","domain":"diagnosis","subject":{"diagnosis_ids":row["diagnosis_ids"]},"decision":{"kind":kind},"fact":row["fact"],"reason":row["reason"],"candidate_card_tags":row["candidate_card_tags"]})
    return facts


def facts_from_icc(doc: dict) -> list[dict]:
    return [{"fact_id":f"icc-{row['diagnosis_id']}","domain":"diagnosis","subject":{"diagnosis_ids":[]},"decision":{"classifier":"ICC","status":row["status"],"diagnosis":row["diagnosis"]},"fact":row["fact"],"reason":row["reason"],"candidate_card_tags":row["candidate_card_tags"]} for row in doc.get("diagnoses") or []]


def facts_from_domain(domain: str, doc: dict) -> list[dict]:
    facts=[]
    if domain=="prognosis":
        for row in doc["decisions"]:
            if row["surface"]:
                facts.append({"fact_id":f"prognosis-{row['variant_id']}-{row['diagnosis_id']}","domain":domain,"subject":{"variant_id":row["variant_id"],"diagnosis_ids":[row["diagnosis_id"]]},"decision":{"effect":row["effect"],"scoring_system":row["scoring_system"]},"fact":row["fact"],"reason":row["reason"],"candidate_card_tags":row["candidate_card_tags"]})
    elif domain=="treatment":
        for row in doc["decisions"]:
            subject={"gene":row["gene"],"diagnosis_ids":[row["diagnosis_id"]]}
            if row["target_surface"]:
                facts.append({"fact_id":f"treatment-target-{row['gene']}-{row['diagnosis_id']}","domain":domain,"subject":subject,"decision":{"drug_target":row["drug_target"]},"fact":row["target_fact"],"reason":row["target_reason"],"candidate_card_tags":row["target_candidate_card_tags"]})
            if row["resistance_surface"]:
                facts.append({"fact_id":f"treatment-resistance-{row['gene']}-{row['diagnosis_id']}","domain":domain,"subject":subject,"decision":{"drug_resistance":row["drug_resistance"]},"fact":row["resistance_fact"],"reason":row["resistance_reason"],"candidate_card_tags":row["resistance_candidate_card_tags"]})
    elif domain=="biomarker":
        for row in doc["decisions"]:
            if row["surface"]:
                facts.append({"fact_id":f"biomarker-{row['variant_id']}-{row['diagnosis_id']}","domain":domain,"subject":{"variant_id":row["variant_id"],"diagnosis_ids":[row["diagnosis_id"]]},"decision":{"mrd_usable":row["mrd_usable"]},"fact":row["fact"],"reason":row["reason"],"candidate_card_tags":row["candidate_card_tags"]})
    elif domain=="germline":
        for row in doc["variant_decisions"]:
            if row["surface"]:
                facts.append({"fact_id":f"germline-{row['variant_id']}","domain":domain,"subject":{"variant_id":row["variant_id"],"diagnosis_ids":[]},"decision":{"potentially_germline":row["potentially_germline"]},"fact":row["fact"],"reason":row["reason"],"candidate_card_tags":row["candidate_card_tags"]})
        cp=doc["clinical_picture"]
        if cp["surface"]:
            facts.append({"fact_id":"germline-clinical","domain":domain,"subject":{"diagnosis_ids":[]},"decision":{"clinical_picture_supportive":cp["supportive"]},"fact":cp["fact"],"reason":cp["reason"],"candidate_card_tags":cp["candidate_card_tags"]})
    return facts


def validate_evidence_alignment_text(text: str, facts: list[dict], permitted_by_fact: dict[str,set[str]]) -> str:
    doc=parse_yaml_mapping(text,"evidence alignment"); issues=[]; _exact_keys(issues,doc,{"alignments"})
    rows=doc.get("alignments")
    if not isinstance(rows,list): issues.append(ValidationIssue("alignments",f"expected list, received {type(rows).__name__}","return one row per supplied fact in supplied order")); rows=[]
    if len(rows)!=len(facts): issues.append(ValidationIssue("alignments",f"expected {len(facts)} rows, received {len(rows)}","return every supplied fact_id exactly once in order"))
    for i,fact in enumerate(facts):
        if i>=len(rows) or not isinstance(rows[i],dict): continue
        row=rows[i]; loc=f"alignments[{i}]"; _exact_keys(issues,row,{"fact_id","citation"},loc)
        if row.get("fact_id")!=fact["fact_id"]: issues.append(ValidationIssue(f"{loc}.fact_id",f"received {row.get('fact_id')!r}",f"copy exact supplied fact_id {fact['fact_id']!r}"))
        citation=row.get("citation")
        if citation is None: continue
        if not isinstance(citation,str) or CARD_TAGS_RE.fullmatch(citation) is None:
            issues.append(ValidationIssue(f"{loc}.citation",f"invalid citation syntax {citation!r}","use null or adjacent exact runtime card tags")); continue
        tags=CARD_TAG_RE.findall(citation); permitted=permitted_by_fact.get(fact["fact_id"],set())
        unknown=sorted(set(tags)-permitted)
        if unknown: issues.append(ValidationIssue(f"{loc}.citation",f"card tag(s) are not permitted for this fact scope: {unknown}","use only cards supplied for this fact's diagnosis context or null"))
        if len(tags)!=len(set(tags)): issues.append(ValidationIssue(f"{loc}.citation","contains repeated card tag","include each card tag once"))
    fail("evidence alignment",issues); return "evidence alignment validated"


def apply_alignment(facts: list[dict], alignment: dict) -> list[dict]:
    by_id={row["fact_id"]:row["citation"] for row in alignment["alignments"]}
    return [dict(row,citation=by_id[row["fact_id"]]) for row in facts]


def validate_summary_text(text: str) -> str:
    lines=[line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]: lines.pop()
    issues=[]; current=None; seen_headings=[]; sentence_count=0
    if not lines: issues.append(ValidationIssue("Report","empty output","return the complete report under allowed headings"))
    for i,line in enumerate(lines,1):
        if not line: continue
        if line in HEADINGS:
            current=HEADINGS[line]; seen_headings.append(line); continue
        if line.startswith("**") and line.endswith("**"):
            issues.append(ValidationIssue(f"Line {i}",f"unknown heading {line!r}","use only the exact allowed bold headings")); continue
        if current is None:
            issues.append(ValidationIssue(f"Line {i}","sentence appears before an allowed heading","place every sentence under an allowed heading")); continue
        sentence_count+=1
        if line != line.strip(): issues.append(ValidationIssue(f"Line {i}","contains surrounding whitespace","remove leading/trailing whitespace"))
        if line.startswith(("-","*","#",">")): issues.append(ValidationIssue(f"Line {i}","uses Markdown list/heading structure","return plain sentence prose"))
        if not line.endswith("."): issues.append(ValidationIssue(f"Line {i}","sentence does not end with a full stop","end the sentence with '.'"))
        if "[card:" in line: issues.append(ValidationIssue(f"Line {i}","contains a runtime card tag","remove citations from synthesis prose"))
    if len(seen_headings)!=len(set(seen_headings)): issues.append(ValidationIssue("Headings","a heading is repeated","use each domain heading at most once"))
    if sentence_count==0: issues.append(ValidationIssue("Report body","contains no sentences","return at least one report sentence"))
    fail("final synthesis",issues); return "final synthesis validated"


def sentence_manifest(text: str) -> list[dict]:
    validate_summary_text(text)
    rows=[]; current=None; counts={d:0 for d in DOMAIN_HEADINGS}
    for line in text.splitlines():
        stripped=line.strip()
        if not stripped: continue
        if stripped in HEADINGS:
            current=HEADINGS[stripped]; continue
        counts[current]+=1
        rows.append({"sentence_id":f"{current}-{counts[current]}","domain":current,"sentence":stripped})
    return rows


def validate_sentence_alignment_text(text: str, sentences: list[dict], facts: list[dict]) -> str:
    doc=parse_yaml_mapping(text,"sentence-to-fact alignment"); issues=[]; _exact_keys(issues,doc,{"alignments"})
    rows=doc.get("alignments")
    if not isinstance(rows,list): issues.append(ValidationIssue("alignments",f"expected list, received {type(rows).__name__}","return one row per supplied sentence in order")); rows=[]
    if len(rows)!=len(sentences): issues.append(ValidationIssue("alignments",f"expected {len(sentences)} rows, received {len(rows)}","return every supplied sentence_id exactly once"))
    fact_map={f["fact_id"]:f for f in facts}
    for i,sentence in enumerate(sentences):
        if i>=len(rows) or not isinstance(rows[i],dict): continue
        row=rows[i]; loc=f"alignments[{i}]"; _exact_keys(issues,row,{"sentence_id","fact_ids"},loc)
        if row.get("sentence_id")!=sentence["sentence_id"]: issues.append(ValidationIssue(f"{loc}.sentence_id",f"received {row.get('sentence_id')!r}",f"copy exact supplied sentence_id {sentence['sentence_id']!r}"))
        ids=row.get("fact_ids")
        if not isinstance(ids,list) or not ids: issues.append(ValidationIssue(f"{loc}.fact_ids","must be a non-empty list","list one or more supplied same-domain fact IDs")); continue
        if len(ids)!=len(set(ids)): issues.append(ValidationIssue(f"{loc}.fact_ids","contains duplicates","list each represented fact once"))
        for fid in ids:
            fact=fact_map.get(fid)
            if fact is None: issues.append(ValidationIssue(f"{loc}.fact_ids",f"unknown fact ID {fid!r}","use only supplied fact IDs"))
            elif fact["domain"]!=sentence["domain"]: issues.append(ValidationIssue(f"{loc}.fact_ids",f"fact {fid!r} belongs to {fact['domain']}, not {sentence['domain']}","use only same-domain facts"))
    fail("sentence-to-fact alignment",issues); return "sentence-to-fact alignment validated"


def uncovered_fact_ids(alignment: dict, facts: list[dict]) -> list[str]:
    covered={fid for row in alignment.get("alignments") or [] for fid in (row.get("fact_ids") or [])}
    return [f["fact_id"] for f in facts if f["fact_id"] not in covered]


def render_cited_report(summary: str, alignment: dict, facts: list[dict]) -> str:
    fact_map={f["fact_id"]:f for f in facts}; align={r["sentence_id"]:r["fact_ids"] for r in alignment["alignments"]}
    manifest=sentence_manifest(summary); by_sentence={r["sentence"]:(r["sentence_id"],r["domain"]) for r in manifest}
    # sentence text may duplicate; consume IDs by ordered traversal instead of dict lookup.
    rendered=[]; si=0
    for line in summary.splitlines():
        stripped=line.strip()
        if not stripped: rendered.append(""); continue
        if stripped in HEADINGS: rendered.append(stripped); continue
        sentence=manifest[si]; si+=1
        tags=[]
        for fid in align[sentence["sentence_id"]]:
            citation=fact_map[fid].get("citation")
            if not citation: continue
            for tag in CARD_TAG_RE.findall(citation):
                token=f"[card:{tag}]"
                if token not in tags: tags.append(token)
        rendered.append(stripped + ((" " + "".join(tags)) if tags else ""))
    return "\n".join(rendered).rstrip()+"\n"


def validate_canonical_summary_doc(doc: dict, facts: list[dict]) -> str:
    """Validate the invariant summarization-scheduler output contract."""
    issues: list[ValidationIssue] = []
    if set(doc) != {"sentences"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly sentences"))
    rows = doc.get("sentences")
    if not isinstance(rows, list) or not rows:
        issues.append(ValidationIssue("sentences", f"expected non-empty list, received {type(rows).__name__}", "return one or more sentence rows")); rows=[]
    fact_map={f["fact_id"]:f for f in facts}; covered=set(); seen=set(); expected_counts={d:0 for d in DOMAIN_HEADINGS}
    for i,row in enumerate(rows):
        loc=f"sentences[{i}]"
        if not isinstance(row,dict):
            issues.append(ValidationIssue(loc,"expected mapping","return sentence_id, domain, sentence, fact_ids, card_tags")); continue
        expected={"sentence_id","domain","sentence","fact_ids","card_tags"}
        if set(row)!=expected:
            issues.append(ValidationIssue(loc,f"received fields {sorted(row)}",f"return exactly {sorted(expected)}"))
        sid=row.get("sentence_id"); domain=row.get("domain"); sentence=row.get("sentence"); ids=row.get("fact_ids"); tags=row.get("card_tags")
        if domain not in DOMAIN_HEADINGS:
            issues.append(ValidationIssue(f"{loc}.domain",f"invalid domain {domain!r}",f"use one of {sorted(DOMAIN_HEADINGS)}"))
        else:
            expected_counts[domain]+=1
            expected_sid=f"{domain}-{expected_counts[domain]}"
            if sid!=expected_sid:
                issues.append(ValidationIssue(f"{loc}.sentence_id",f"received {sid!r}",f"use deterministic sentence_id {expected_sid!r}"))
        if sid in seen: issues.append(ValidationIssue(f"{loc}.sentence_id",f"duplicate {sid!r}","use each sentence_id once"))
        seen.add(sid)
        if not isinstance(sentence,str) or not sentence.strip() or sentence!=sentence.strip() or not sentence.endswith(".") or "[card:" in sentence:
            issues.append(ValidationIssue(f"{loc}.sentence",f"invalid sentence {sentence!r}","return citation-free plain sentence prose ending with a full stop"))
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):
            issues.append(ValidationIssue(f"{loc}.fact_ids",f"invalid fact_ids {ids!r}","list one or more unique supplied fact IDs")); ids=[]
        expected_tags=[]
        for fid in ids:
            fact=fact_map.get(fid)
            if fact is None:
                issues.append(ValidationIssue(f"{loc}.fact_ids",f"unknown fact ID {fid!r}","use only supplied fact IDs")); continue
            if fact["domain"]!=domain:
                issues.append(ValidationIssue(f"{loc}.fact_ids",f"fact {fid!r} belongs to {fact['domain']}, not {domain}","use only same-domain facts")); continue
            covered.add(fid)
            citation=fact.get("citation")
            if citation:
                for raw in CARD_TAG_RE.findall(citation):
                    token=f"[card:{raw}]"
                    if token not in expected_tags: expected_tags.append(token)
        if tags!=expected_tags:
            issues.append(ValidationIssue(f"{loc}.card_tags",f"received {tags!r}",f"card_tags are deterministic from paired facts; expected {expected_tags!r}"))
    missing=[fid for fid in fact_map if fid not in covered]
    if missing: issues.append(ValidationIssue("fact coverage",f"omitted supplied fact IDs {missing}","represent every supplied fact at least once"))
    fail("canonical summarization output",issues)
    return "canonical summarization output validated"


def render_canonical_summary(doc: dict) -> str:
    """Render canonical sentence/card-tag YAML to citation-bearing report Markdown."""
    out=[]; current=None
    for row in doc.get("sentences") or []:
        domain=row["domain"]
        if domain!=current:
            if out: out.append("")
            out.append(DOMAIN_HEADINGS[domain]); current=domain
        tags="".join(row.get("card_tags") or [])
        out.append(row["sentence"] + ((" " + tags) if tags else ""))
    return "\n".join(out).rstrip()+"\n"


def sentence_card_interpretations(doc: dict, interpretation_by_tag: dict[str,str]) -> dict:
    """Deterministically pair each final sentence with the interpretations of its paired card tags."""
    rows=[]
    for row in doc.get("sentences") or []:
        cards=[]
        for tag in row.get("card_tags") or []:
            if tag not in interpretation_by_tag:
                raise ValueError(f"summary references card tag without a drawn-card interpretation: {tag}")
            cards.append({"card_tag":tag,"interpretation":interpretation_by_tag[tag]})
        rows.append({
            "sentence_id":row["sentence_id"],"domain":row["domain"],"sentence":row["sentence"],
            "fact_ids":list(row.get("fact_ids") or []),"cards":cards,
        })
    return {"sentences":rows}
