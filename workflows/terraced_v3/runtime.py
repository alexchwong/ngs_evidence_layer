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
CASE_REF_RE = re.compile(r"^[CV]\d+$")

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
                elif key == "card_tags" or str(key).endswith("_card_tags"):
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


def case_reference_ids(case: dict) -> set[str]:
    """Stable patient-source identifiers available to model patient-premise provenance."""
    refs = {str(row.get("variant_id")) for row in case.get("variants") or [] if row.get("variant_id")}
    refs.update(str(row.get("fact_id")) for row in case.get("case_facts") or [] if row.get("fact_id"))
    return refs


def _validate_case_refs(issues: list[ValidationIssue], value, path: str, permitted: set[str]) -> None:
    if not isinstance(value, list):
        issues.append(ValidationIssue(path, f"expected a list, received {type(value).__name__}", "return a YAML list of exact supplied case/variant IDs such as C2 or V1"))
        return
    seen = set()
    for i, ref in enumerate(value):
        loc = f"{path}[{i}]"
        if not isinstance(ref, str) or CASE_REF_RE.fullmatch(ref) is None:
            issues.append(ValidationIssue(loc, f"invalid case reference {ref!r}", "use one exact supplied patient-source ID such as C2 or V1"))
            continue
        if ref not in permitted:
            issues.append(ValidationIssue(loc, f"case reference {ref!r} was not supplied to this task", "use only an exact C#/V# identifier from the structured case or remove it"))
        if ref in seen:
            issues.append(ValidationIssue(loc, f"duplicate case reference {ref!r}", "list each case/variant source once"))
        seen.add(ref)


def _validate_card_tags(issues: list[ValidationIssue], value, path: str, permitted: set[str], permitted_case_refs: set[str] | None = None) -> None:
    if not isinstance(value, list):
        issues.append(ValidationIssue(path, f"expected a list, received {type(value).__name__}", "return a YAML list of exact supplied card tags"))
        return
    permitted_case_refs = permitted_case_refs or set()
    seen = set()
    for i, tag in enumerate(value):
        loc = f"{path}[{i}]"
        if isinstance(tag, str) and tag in permitted_case_refs:
            issues.append(ValidationIssue(
                loc,
                f"{tag!r} is a patient case/variant identifier, not a literature card tag",
                f"move {tag!r} to the sibling case_refs field; do not replace it with an arbitrary [card:...] tag. Use card_tags: [] when the statement is only a patient observation, and use card_tags only for literature-dependent interpretation",
            ))
            continue
        if not isinstance(tag, str) or CARD_TAGS_RE.fullmatch(tag) is None or len(CARD_TAG_RE.findall(tag)) != 1:
            issues.append(ValidationIssue(loc, f"invalid card tag {tag!r}", "use one exact supplied literature tag such as [card:0123456789ab]; C#/V# patient-source IDs belong in case_refs"))
            continue
        raw = CARD_TAG_RE.findall(tag)[0]
        if raw not in permitted:
            issues.append(ValidationIssue(loc, f"tag {tag} was not supplied to this task", "use only a supplied card tag or remove it; never substitute a case/variant ID into card_tags"))
        if raw in seen:
            issues.append(ValidationIssue(loc, f"duplicate tag {tag}", "list each card once"))
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


def _canonical_diagnosis_statement(authority: str, diagnosis: str) -> str:
    label=str(diagnosis or "").strip().rstrip(".")
    return f"{authority} classification: {label}."


def validate_who5_text(text: str, permitted_tags: set[str], permitted_case_refs: set[str] | None = None) -> str:
    permitted_case_refs = permitted_case_refs or set()
    doc = parse_yaml_mapping(text, "WHO5 diagnosis")
    issues: list[ValidationIssue] = []
    _exact_keys(issues, doc, {"diagnoses"})
    diagnoses = doc.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        issues.append(ValidationIssue("diagnoses", "must contain at least one diagnosis", "return every established or indeterminate WHO5 diagnosis"))
        diagnoses = []
    for i, row in enumerate(diagnoses, 1):
        loc=f"diagnoses[{i-1}]"
        if not isinstance(row,dict):
            issues.append(ValidationIssue(loc,f"expected object, received {type(row).__name__}","return the complete diagnosis row")); continue
        _exact_keys(issues,row,{"diagnosis_id","schema_disease","status","diagnosis","statement","reason","case_refs","card_tags"},loc)
        expected_id=f"DX{i}"
        if row.get("diagnosis_id")!=expected_id:
            issues.append(ValidationIssue(f"{loc}.diagnosis_id",f"received {row.get('diagnosis_id')!r}",f"use sequential ID {expected_id!r}"))
        disease=row.get("schema_disease")
        if disease not in vocab.CASE_DISEASE_SET or disease in WHO5_EXCLUDED_SCHEMA_DISEASES:
            issues.append(ValidationIssue(f"{loc}.schema_disease",f"invalid WHO5 routing disease {disease!r}","use one exact supplied canonical WHO5 schema disease; MDS/AML is ICC-only"))
        if row.get("status") not in {"established","indeterminate"}:
            issues.append(ValidationIssue(f"{loc}.status",f"invalid status {row.get('status')!r}","use only established or indeterminate"))
        if not _nonempty(row.get("diagnosis")):
            issues.append(ValidationIssue(f"{loc}.diagnosis","blank or not a string","return the WHO5 diagnostic label"))
        else:
            expected_statement=_canonical_diagnosis_statement("WHO5",row["diagnosis"])
            if row.get("statement")!=expected_statement:
                issues.append(ValidationIssue(f"{loc}.statement",f"received {row.get('statement')!r}",f"return exactly {expected_statement!r}; patient findings belong in reason"))
        if not _nonempty(row.get("reason")):
            issues.append(ValidationIssue(f"{loc}.reason","blank or not a string","justify the diagnosis using the relevant patient findings/premises"))
        _validate_case_refs(issues,row.get("case_refs"),f"{loc}.case_refs",permitted_case_refs)
        _validate_card_tags(issues,row.get("card_tags"),f"{loc}.card_tags",permitted_tags,permitted_case_refs)
    fail("WHO5 diagnosis",issues)
    return "WHO5 diagnosis validated"


def validate_icc_text(text: str, permitted_tags: set[str], permitted_case_refs: set[str] | None = None) -> str:
    permitted_case_refs = permitted_case_refs or set()
    doc=parse_yaml_mapping(text,"ICC diagnosis"); issues=[]; _exact_keys(issues,doc,{"diagnoses"})
    rows=doc.get("diagnoses")
    if not isinstance(rows,list) or not rows:
        issues.append(ValidationIssue("diagnoses","must contain at least one ICC diagnosis","return every established or materially plausible ICC diagnosis")); rows=[]
    for i,row in enumerate(rows,1):
        loc=f"diagnoses[{i-1}]"
        if not isinstance(row,dict): issues.append(ValidationIssue(loc,f"expected object, received {type(row).__name__}","return the complete ICC row")); continue
        _exact_keys(issues,row,{"diagnosis_id","status","diagnosis","statement","reason","case_refs","card_tags"},loc)
        expected_id=f"ICC{i}"
        if row.get("diagnosis_id")!=expected_id: issues.append(ValidationIssue(f"{loc}.diagnosis_id",f"received {row.get('diagnosis_id')!r}",f"use sequential ID {expected_id!r}"))
        if row.get("status") not in {"established","indeterminate"}: issues.append(ValidationIssue(f"{loc}.status",f"invalid status {row.get('status')!r}","use only established or indeterminate"))
        if not _nonempty(row.get("diagnosis")): issues.append(ValidationIssue(f"{loc}.diagnosis","blank or not a string","return the ICC diagnostic label"))
        else:
            expected_statement=_canonical_diagnosis_statement("ICC",row["diagnosis"])
            if row.get("statement")!=expected_statement: issues.append(ValidationIssue(f"{loc}.statement",f"received {row.get('statement')!r}",f"return exactly {expected_statement!r}; patient findings belong in reason"))
        if not _nonempty(row.get("reason")): issues.append(ValidationIssue(f"{loc}.reason","blank or not a string","justify the diagnosis using the relevant patient findings/premises"))
        _validate_case_refs(issues,row.get("case_refs"),f"{loc}.case_refs",permitted_case_refs)
        _validate_card_tags(issues,row.get("card_tags"),f"{loc}.card_tags",permitted_tags,permitted_case_refs)
    fail("ICC diagnosis",issues)
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
    issues: list[ValidationIssue], row: dict, loc: str, *, surface_key: str = "surface", statement_key: str = "statement", reason_key: str = "reason", refs_key: str = "case_refs", tags_key: str = "card_tags", permitted_tags: set[str], permitted_case_refs: set[str]
) -> None:
    surface=row.get(surface_key)
    if not isinstance(surface,bool):
        issues.append(ValidationIssue(f"{loc}.{surface_key}",f"expected boolean, received {surface!r}","use true or false")); return
    statement=row.get(statement_key); reason=row.get(reason_key)
    if surface:
        if not _nonempty(statement) or not str(statement).rstrip().endswith("."):
            issues.append(ValidationIssue(f"{loc}.{statement_key}","surface=true requires a complete statement ending with a full stop","return one atomic conclusion that answers this domain question; do not merely repeat a case observation"))
        if not _nonempty(reason):
            issues.append(ValidationIssue(f"{loc}.{reason_key}","surface=true requires a reason","put the patient observations/premises and concise justification here"))
    else:
        if statement is not None or reason is not None:
            issues.append(ValidationIssue(loc,f"{surface_key}=false but statement/reason are not null",f"set {statement_key} and {reason_key} to null"))
        if row.get(refs_key) not in ([],None): issues.append(ValidationIssue(f"{loc}.{refs_key}",f"{surface_key}=false has patient provenance {row.get(refs_key)!r}","set patient refs to [] because there is no surfaced statement"))
        if row.get(tags_key) not in ([],None): issues.append(ValidationIssue(f"{loc}.{tags_key}",f"{surface_key}=false has evidence provenance {row.get(tags_key)!r}","set card tags to [] because there is no surfaced statement"))
    _validate_case_refs(issues,row.get(refs_key),f"{loc}.{refs_key}",permitted_case_refs)
    _validate_card_tags(issues,row.get(tags_key),f"{loc}.{tags_key}",permitted_tags,permitted_case_refs)


def validate_domain_text(text: str, *, domain: str, spec: dict, permitted_tags: set[str], permitted_case_refs: set[str] | None = None) -> str:
    permitted_case_refs=permitted_case_refs or set(); doc=parse_yaml_mapping(text,f"{domain} task"); issues=[]
    if domain=="prognosis":
        _exact_keys(issues,doc,{"decisions"}); rows=doc.get("decisions"); required=spec["required_pairs"]
        if not isinstance(rows,list): issues.append(ValidationIssue("decisions",f"expected list, received {type(rows).__name__}","return one decision per required variant × diagnosis pair")); rows=[]
        if len(rows)!=len(required): issues.append(ValidationIssue("decisions",f"expected {len(required)} rows, received {len(rows)}","return every required pair exactly once in supplied order"))
        for i,pair in enumerate(required):
            if i>=len(rows) or not isinstance(rows[i],dict): continue
            row=rows[i]; loc=f"decisions[{i}]"; _exact_keys(issues,row,{"variant_id","diagnosis_id","effect","scoring_system","surface","statement","reason","case_refs","card_tags"},loc)
            if (row.get("variant_id"),row.get("diagnosis_id"))!=pair: issues.append(ValidationIssue(loc,f"wrong scope {(row.get('variant_id'),row.get('diagnosis_id'))!r}",f"use exact required pair {pair!r}"))
            if row.get("effect") not in {"favorable","adverse","neither"}: issues.append(ValidationIssue(f"{loc}.effect",f"invalid value {row.get('effect')!r}","use favorable, adverse, or neither"))
            score=row.get("scoring_system")
            if score is not None and not _nonempty(score): issues.append(ValidationIssue(f"{loc}.scoring_system",f"invalid value {score!r}","use a non-empty named system or null"))
            _surface_fields(issues,row,loc,permitted_tags=permitted_tags,permitted_case_refs=permitted_case_refs)
    elif domain=="treatment":
        _exact_keys(issues,doc,{"decisions"}); rows=doc.get("decisions"); required=spec["required_pairs"]
        if not isinstance(rows,list): issues.append(ValidationIssue("decisions",f"expected list, received {type(rows).__name__}","return one decision per required gene × diagnosis pair")); rows=[]
        if len(rows)!=len(required): issues.append(ValidationIssue("decisions",f"expected {len(required)} rows, received {len(rows)}","return every required pair exactly once in supplied order"))
        fields={"gene","diagnosis_id","drug_target","target_surface","target_statement","target_reason","target_case_refs","target_card_tags","drug_resistance","resistance_surface","resistance_statement","resistance_reason","resistance_case_refs","resistance_card_tags"}
        for i,pair in enumerate(required):
            if i>=len(rows) or not isinstance(rows[i],dict): continue
            row=rows[i]; loc=f"decisions[{i}]"; _exact_keys(issues,row,fields,loc)
            if (row.get("gene"),row.get("diagnosis_id"))!=pair: issues.append(ValidationIssue(loc,f"wrong scope {(row.get('gene'),row.get('diagnosis_id'))!r}",f"use exact required pair {pair!r}"))
            for key in ("drug_target","drug_resistance"):
                if not isinstance(row.get(key),bool): issues.append(ValidationIssue(f"{loc}.{key}",f"expected boolean, received {row.get(key)!r}","use true or false"))
            _surface_fields(issues,row,loc,surface_key="target_surface",statement_key="target_statement",reason_key="target_reason",refs_key="target_case_refs",tags_key="target_card_tags",permitted_tags=permitted_tags,permitted_case_refs=permitted_case_refs)
            _surface_fields(issues,row,loc,surface_key="resistance_surface",statement_key="resistance_statement",reason_key="resistance_reason",refs_key="resistance_case_refs",tags_key="resistance_card_tags",permitted_tags=permitted_tags,permitted_case_refs=permitted_case_refs)
    elif domain=="biomarker":
        _exact_keys(issues,doc,{"decisions"}); rows=doc.get("decisions"); required=spec["required_pairs"]
        if not isinstance(rows,list): issues.append(ValidationIssue("decisions",f"expected list, received {type(rows).__name__}","return one decision per required variant × diagnosis pair")); rows=[]
        if len(rows)!=len(required): issues.append(ValidationIssue("decisions",f"expected {len(required)} rows, received {len(rows)}","return every required pair exactly once in supplied order"))
        for i,pair in enumerate(required):
            if i>=len(rows) or not isinstance(rows[i],dict): continue
            row=rows[i]; loc=f"decisions[{i}]"; _exact_keys(issues,row,{"variant_id","diagnosis_id","mrd_usable","surface","statement","reason","case_refs","card_tags"},loc)
            if (row.get("variant_id"),row.get("diagnosis_id"))!=pair: issues.append(ValidationIssue(loc,f"wrong scope {(row.get('variant_id'),row.get('diagnosis_id'))!r}",f"use exact required pair {pair!r}"))
            if not isinstance(row.get("mrd_usable"),bool): issues.append(ValidationIssue(f"{loc}.mrd_usable",f"expected boolean, received {row.get('mrd_usable')!r}","use true or false"))
            _surface_fields(issues,row,loc,permitted_tags=permitted_tags,permitted_case_refs=permitted_case_refs)
    elif domain=="germline":
        _exact_keys(issues,doc,{"variant_decisions","clinical_picture"}); rows=doc.get("variant_decisions"); required=spec["required_variants"]
        if not isinstance(rows,list): issues.append(ValidationIssue("variant_decisions",f"expected list, received {type(rows).__name__}","return one decision per detected variant")); rows=[]
        if len(rows)!=len(required): issues.append(ValidationIssue("variant_decisions",f"expected {len(required)} rows, received {len(rows)}","return every required variant exactly once in supplied order"))
        for i,variant_id in enumerate(required):
            if i>=len(rows) or not isinstance(rows[i],dict): continue
            row=rows[i]; loc=f"variant_decisions[{i}]"; _exact_keys(issues,row,{"variant_id","potentially_germline","surface","statement","reason","case_refs","card_tags"},loc)
            if row.get("variant_id")!=variant_id: issues.append(ValidationIssue(f"{loc}.variant_id",f"received {row.get('variant_id')!r}",f"use exact required variant {variant_id!r}"))
            if not isinstance(row.get("potentially_germline"),bool): issues.append(ValidationIssue(f"{loc}.potentially_germline",f"expected boolean, received {row.get('potentially_germline')!r}","use true or false"))
            _surface_fields(issues,row,loc,permitted_tags=permitted_tags,permitted_case_refs=permitted_case_refs)
        cp=doc.get("clinical_picture")
        if not isinstance(cp,dict): issues.append(ValidationIssue("clinical_picture",f"expected object, received {type(cp).__name__}","return supportive, surface, statement, reason, case_refs, card_tags"))
        else:
            _exact_keys(issues,cp,{"supportive","surface","statement","reason","case_refs","card_tags"},"clinical_picture")
            if cp.get("supportive") not in {True,False,"uncertain"}: issues.append(ValidationIssue("clinical_picture.supportive",f"invalid value {cp.get('supportive')!r}","use true, false, or uncertain"))
            _surface_fields(issues,cp,"clinical_picture",permitted_tags=permitted_tags,permitted_case_refs=permitted_case_refs)
    else: raise ValueError(f"unknown domain {domain!r}")
    fail(f"{domain} task",issues); return f"{domain} task validated"

def statements_from_who5(doc: dict) -> list[dict]:
    return [{
        "domain":"diagnosis",
        "subject":{"diagnosis_ids":[row["diagnosis_id"]]},
        "decision":{"classifier":"WHO5","schema_disease":row["schema_disease"],"status":row["status"],"diagnosis":row["diagnosis"]},
        "statement":row["statement"],"reason":row["reason"],"case_refs":list(row["case_refs"]),"card_tags":list(row["card_tags"]),
    } for row in doc.get("diagnoses") or []]


def statements_from_icc(doc: dict) -> list[dict]:
    return [{
        "domain":"diagnosis","subject":{"diagnosis_ids":[]},
        "decision":{"classifier":"ICC","status":row["status"],"diagnosis":row["diagnosis"]},
        "statement":row["statement"],"reason":row["reason"],"case_refs":list(row["case_refs"]),"card_tags":list(row["card_tags"]),
    } for row in doc.get("diagnoses") or []]


def statements_from_domain(domain: str, doc: dict) -> list[dict]:
    statements=[]
    if domain=="prognosis":
        for row in doc["decisions"]:
            if row["surface"]:
                statements.append({"domain":domain,"subject":{"variant_id":row["variant_id"],"diagnosis_ids":[row["diagnosis_id"]]},"decision":{"effect":row["effect"],"scoring_system":row["scoring_system"]},"statement":row["statement"],"reason":row["reason"],"case_refs":list(row["case_refs"]),"card_tags":list(row["card_tags"])})
    elif domain=="treatment":
        for row in doc["decisions"]:
            subject={"gene":row["gene"],"diagnosis_ids":[row["diagnosis_id"]]}
            if row["target_surface"]:
                statements.append({"domain":domain,"subject":subject,"decision":{"drug_target":row["drug_target"]},"statement":row["target_statement"],"reason":row["target_reason"],"case_refs":list(row["target_case_refs"]),"card_tags":list(row["target_card_tags"])})
            if row["resistance_surface"]:
                statements.append({"domain":domain,"subject":subject,"decision":{"drug_resistance":row["drug_resistance"]},"statement":row["resistance_statement"],"reason":row["resistance_reason"],"case_refs":list(row["resistance_case_refs"]),"card_tags":list(row["resistance_card_tags"])})
    elif domain=="biomarker":
        for row in doc["decisions"]:
            if row["surface"]:
                statements.append({"domain":domain,"subject":{"variant_id":row["variant_id"],"diagnosis_ids":[row["diagnosis_id"]]},"decision":{"mrd_usable":row["mrd_usable"]},"statement":row["statement"],"reason":row["reason"],"case_refs":list(row["case_refs"]),"card_tags":list(row["card_tags"])})
    elif domain=="germline":
        for row in doc["variant_decisions"]:
            if row["surface"]:
                statements.append({"domain":domain,"subject":{"variant_id":row["variant_id"],"diagnosis_ids":[]},"decision":{"potentially_germline":row["potentially_germline"]},"statement":row["statement"],"reason":row["reason"],"case_refs":list(row["case_refs"]),"card_tags":list(row["card_tags"])})
        cp=doc["clinical_picture"]
        if cp["surface"]:
            statements.append({"domain":domain,"subject":{"diagnosis_ids":[]},"decision":{"clinical_picture_supportive":cp["supportive"]},"statement":cp["statement"],"reason":cp["reason"],"case_refs":list(cp["case_refs"]),"card_tags":list(cp["card_tags"])})
    else: raise ValueError(f"unknown statement domain {domain!r}")
    return statements


def _statement_identity_payload(statement: dict) -> dict:
    """Immutable reportable statement, justification and evidence provenance."""
    return {
        "domain":statement.get("domain"),
        "statement":statement.get("statement"),
        "reason":statement.get("reason"),
        "case_refs":list(statement.get("case_refs") or []),
        "card_tags":list(statement.get("card_tags") or []),
    }


def statement_signature(statement: dict) -> str:
    return json.dumps(_statement_identity_payload(statement),sort_keys=True,ensure_ascii=False,separators=(",",":"))


def new_statement_ledger() -> dict:
    return {"schema_version":3,"next_statement_number":1,"statements":[]}


def load_statement_ledger(path: Path) -> dict:
    if not path.is_file(): return new_statement_ledger()
    doc=parse_yaml_mapping(path.read_text(encoding="utf-8"),"statement ledger")
    if doc.get("schema_version")!=3 or not isinstance(doc.get("next_statement_number"),int) or not isinstance(doc.get("statements"),list):
        raise ValueError(f"invalid statement ledger structure in {path}")
    return doc


def active_ledger_statements(ledger: dict) -> list[dict]:
    return [row for row in ledger.get("statements") or [] if row.get("status")=="active"]


def statements_needing_evidence_check(ledger: dict, snapshot_key: str, candidates: list[dict]) -> list[dict]:
    active_signatures={statement_signature(row) for row in active_ledger_statements(ledger) if row.get("snapshot_key")==snapshot_key}
    seen=set(); out=[]
    for candidate in candidates:
        sig=statement_signature(candidate)
        if sig in seen: raise ValueError(f"snapshot {snapshot_key!r} contains duplicate reportable statements")
        seen.add(sig)
        if sig not in active_signatures: out.append(candidate)
    return out


def reconcile_statement_snapshot(ledger: dict, snapshot_key: str, candidates: list[dict], *, source: str) -> dict:
    seen=set()
    for candidate in candidates:
        sig=statement_signature(candidate)
        if sig in seen: raise ValueError(f"snapshot {snapshot_key!r} contains duplicate reportable statements")
        seen.add(sig)
    active=[row for row in active_ledger_statements(ledger) if row.get("snapshot_key")==snapshot_key]
    active_by_sig={statement_signature(row):row for row in active}; candidate_sigs={statement_signature(row) for row in candidates}
    for old in active:
        if statement_signature(old) not in candidate_sigs:
            old["status"]="withdrawn"; old["withdrawn_by"]={"source":source}
    for candidate in candidates:
        sig=statement_signature(candidate); existing=active_by_sig.get(sig)
        if existing is not None:
            existing["current_subject"]=candidate.get("subject") or {}; existing["current_decision"]=candidate.get("decision") or {}; existing["evidence_check"]=candidate.get("evidence_check",existing.get("evidence_check","not_checked")); existing["last_seen_by"]={"source":source}; continue
        number=int(ledger["next_statement_number"]); ledger["next_statement_number"]=number+1
        ledger["statements"].append({
            "statement_id":f"S{number:04d}","snapshot_key":snapshot_key,"status":"active",**_statement_identity_payload(candidate),
            "evidence_check":candidate.get("evidence_check","not_checked"),"introduced_by":{"source":source},"withdrawn_by":None,
            "current_subject":candidate.get("subject") or {},"current_decision":candidate.get("decision") or {},"last_seen_by":{"source":source},
        })
    return ledger


def reportable_active_statements(ledger: dict) -> list[dict]:
    return [{
        "statement_id":row["statement_id"],"domain":row["domain"],"statement":row["statement"],"reason":row.get("reason"),
        "case_refs":list(row.get("case_refs") or []),"card_tags":list(row.get("card_tags") or []),
    } for row in active_ledger_statements(ledger)]


def validate_semantic_preservation_check_text(text: str) -> str:
    doc=parse_yaml_mapping(text,"paraphrase semantic-preservation check"); issues=[]
    _exact_keys(issues,doc,{"preserved","issue"})
    preserved=doc.get("preserved")
    if not isinstance(preserved,bool):
        issues.append(ValidationIssue("preserved",f"expected boolean, received {preserved!r}","use true or false"))
    issue=doc.get("issue")
    if preserved is True and issue is not None:
        issues.append(ValidationIssue("issue","preserved=true requires issue: null","set issue to null"))
    if preserved is False and not _nonempty(issue):
        issues.append(ValidationIssue("issue","preserved=false requires a concise explanation","state the omitted, altered, or added proposition"))
    fail("paraphrase semantic-preservation check",issues)
    return "paraphrase semantic-preservation check validated"


def validate_summary_plan_doc(doc: dict, statements: list[dict]) -> str:
    """Validate report selection/composition over immutable clinical statements."""
    issues=[]; _exact_keys(issues,doc,{"dispositions","sentences"})
    statement_map={s["statement_id"]:s for s in statements}
    dispositions=doc.get("dispositions")
    if not isinstance(dispositions,list):
        issues.append(ValidationIssue("dispositions",f"expected list, received {type(dispositions).__name__}","return one disposition for every supplied statement in order")); dispositions=[]
    if len(dispositions)!=len(statements): issues.append(ValidationIssue("dispositions",f"expected {len(statements)} rows, received {len(dispositions)}","return every supplied statement exactly once in order"))
    included=set(); omitted=set()
    for i,statement in enumerate(statements):
        if i>=len(dispositions) or not isinstance(dispositions[i],dict): continue
        row=dispositions[i]; loc=f"dispositions[{i}]"; _exact_keys(issues,row,{"statement_id","decision","reason"},loc)
        sid=statement["statement_id"]
        if row.get("statement_id")!=sid: issues.append(ValidationIssue(f"{loc}.statement_id",f"received {row.get('statement_id')!r}",f"copy exact supplied statement_id {sid!r}"))
        decision=row.get("decision")
        if decision not in {"include","omit"}: issues.append(ValidationIssue(f"{loc}.decision",f"invalid value {decision!r}","use include or omit"))
        reason=row.get("reason")
        if statement.get("domain")=="diagnosis" and decision=="omit":
            issues.append(ValidationIssue(f"{loc}.decision","diagnostic classification statements cannot be omitted","include every established/indeterminate WHO5 and ICC diagnosis statement"))
        if decision=="include":
            included.add(sid)
            if reason is not None: issues.append(ValidationIssue(f"{loc}.reason","include requires reason: null","set reason to null"))
        elif decision=="omit":
            omitted.add(sid)
            if not _nonempty(reason): issues.append(ValidationIssue(f"{loc}.reason","omit requires a concise audit reason","state why this non-diagnostic statement is safely omitted"))
    rows=doc.get("sentences")
    if not isinstance(rows,list) or not rows: issues.append(ValidationIssue("sentences",f"expected non-empty list, received {type(rows).__name__}","return one or more ordered sentence plans")); rows=[]
    represented=set(); seen_ids=set(); counts={d:0 for d in DOMAIN_HEADINGS}; domain_order={d:i for i,d in enumerate(DOMAIN_HEADINGS)}; last_domain=-1
    for i,row in enumerate(rows):
        loc=f"sentences[{i}]"
        if not isinstance(row,dict): issues.append(ValidationIssue(loc,"expected mapping","return sentence_id, domain, source_statement_ids, draft_sentence")); continue
        _exact_keys(issues,row,{"sentence_id","domain","source_statement_ids","draft_sentence"},loc)
        domain=row.get("domain")
        if domain not in DOMAIN_HEADINGS: issues.append(ValidationIssue(f"{loc}.domain",f"invalid domain {domain!r}",f"use one of {list(DOMAIN_HEADINGS)}"))
        else:
            order=domain_order[domain]
            if order<last_domain: issues.append(ValidationIssue(f"{loc}.domain",f"domain {domain!r} appears after a later report section","group sentences in canonical report section order"))
            last_domain=max(last_domain,order); counts[domain]+=1; expected_sid=f"{domain}-{counts[domain]}"
            if row.get("sentence_id")!=expected_sid: issues.append(ValidationIssue(f"{loc}.sentence_id",f"received {row.get('sentence_id')!r}",f"use deterministic sentence_id {expected_sid!r}"))
        sentence_id=row.get("sentence_id")
        if sentence_id in seen_ids: issues.append(ValidationIssue(f"{loc}.sentence_id",f"duplicate {sentence_id!r}","use each sentence_id once"))
        seen_ids.add(sentence_id)
        draft=row.get("draft_sentence")
        if not isinstance(draft,str) or not draft.strip() or draft!=draft.strip() or not draft.endswith(".") or "[card:" in draft: issues.append(ValidationIssue(f"{loc}.draft_sentence",f"invalid sentence {draft!r}","return one citation-free complete sentence ending with a full stop"))
        ids=row.get("source_statement_ids")
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)): issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"invalid source_statement_ids {ids!r}","list one or more unique included supplied statement IDs")); continue
        for sid in ids:
            statement=statement_map.get(sid)
            if statement is None: issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"unknown statement ID {sid!r}","use only supplied statement IDs")); continue
            if sid in omitted: issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"omitted statement {sid!r} is used in a sentence","remove it or change disposition to include"))
            if statement["domain"]!=domain: issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"statement {sid!r} belongs to {statement['domain']}, not {domain}","merge only statements within the same report domain"))
            represented.add(sid)
    missing=sorted(included-represented)
    if missing: issues.append(ValidationIssue("included statement coverage",f"included statement IDs are not represented in any sentence: {missing}","represent every included statement in at least one sentence"))
    unexpected=sorted(represented-included)
    if unexpected: issues.append(ValidationIssue("sentence sources",f"sentence sources are not dispositioned include: {unexpected}","only included statements may appear in sentence plans"))
    fail("summarization plan",issues); return "summarization plan validated"


def validate_summary_plan_text(text: str, statements: list[dict]) -> str:
    return validate_summary_plan_doc(parse_yaml_mapping(text,"summarization plan"),statements)


def paraphrase_items(plan: dict, statements: list[dict]) -> list[dict]:
    validate_summary_plan_doc(plan,statements)
    statement_map={s["statement_id"]:s for s in statements}; use_counts={}
    for row in plan["sentences"]:
        for sid in row["source_statement_ids"]: use_counts[sid]=use_counts.get(sid,0)+1
    out=[]
    for row in plan["sentences"]:
        ids=list(row["source_statement_ids"])
        out.append({
            "sentence_id":row["sentence_id"],"domain":row["domain"],"draft_sentence":row["draft_sentence"],
            "source_statement_ids":ids,
            "source_statements":[{"statement_id":sid,"statement":statement_map[sid]["statement"]} for sid in ids],
            "split_source_statement_ids":[sid for sid in ids if use_counts.get(sid,0)>1],
        })
    return out


def validate_paraphrase_text(text: str, item: dict) -> str:
    doc=parse_yaml_mapping(text,"paraphrased sentence"); issues=[]; _exact_keys(issues,doc,{"sentence_id","sentence"})
    if doc.get("sentence_id")!=item["sentence_id"]: issues.append(ValidationIssue("sentence_id",f"received {doc.get('sentence_id')!r}",f"copy exact sentence_id {item['sentence_id']!r}"))
    sentence=doc.get("sentence")
    if not isinstance(sentence,str) or not sentence.strip() or sentence!=sentence.strip() or not sentence.endswith(".") or "[card:" in sentence or "\n" in sentence: issues.append(ValidationIssue("sentence",f"invalid sentence {sentence!r}","return exactly one self-contained citation-free sentence ending with a full stop"))
    fail("paraphrased sentence",issues); return "paraphrased sentence validated"


def deterministic_sentence_card_tags(source_statement_ids: list[str], statements: list[dict]) -> list[str]:
    statement_map={s["statement_id"]:s for s in statements}; tags=[]
    for sid in source_statement_ids:
        for tag in statement_map[sid].get("card_tags") or []:
            if tag not in tags: tags.append(tag)
    return tags


def validate_canonical_summary_doc(doc: dict, statements: list[dict]) -> str:
    issues=[]; _exact_keys(issues,doc,{"dispositions","sentences"}); statement_map={s["statement_id"]:s for s in statements}; included=set()
    dispositions=doc.get("dispositions")
    if not isinstance(dispositions,list): issues.append(ValidationIssue("dispositions",f"expected list, received {type(dispositions).__name__}","preserve validated dispositions")); dispositions=[]
    if len(dispositions)!=len(statements): issues.append(ValidationIssue("dispositions",f"expected {len(statements)} rows, received {len(dispositions)}","preserve one disposition per supplied statement"))
    for i,statement in enumerate(statements):
        if i>=len(dispositions) or not isinstance(dispositions[i],dict): continue
        row=dispositions[i]; loc=f"dispositions[{i}]"; _exact_keys(issues,row,{"statement_id","decision","reason"},loc); sid=statement["statement_id"]
        if row.get("statement_id")!=sid: issues.append(ValidationIssue(f"{loc}.statement_id",f"received {row.get('statement_id')!r}",f"expected {sid!r}"))
        if row.get("decision")=="include":
            included.add(sid)
            if row.get("reason") is not None: issues.append(ValidationIssue(f"{loc}.reason","include requires reason: null","preserve plan disposition"))
        elif row.get("decision")=="omit":
            if statement.get("domain")=="diagnosis": issues.append(ValidationIssue(f"{loc}.decision","diagnostic classification statements cannot be omitted","include the diagnosis statement"))
            if not _nonempty(row.get("reason")): issues.append(ValidationIssue(f"{loc}.reason","omit requires an audit reason","preserve omission reason"))
        else: issues.append(ValidationIssue(f"{loc}.decision",f"invalid value {row.get('decision')!r}","use include or omit"))
    rows=doc.get("sentences")
    if not isinstance(rows,list) or not rows: issues.append(ValidationIssue("sentences",f"expected non-empty list, received {type(rows).__name__}","return ordered paraphrased sentences")); rows=[]
    represented=set(); counts={d:0 for d in DOMAIN_HEADINGS}; domain_order={d:i for i,d in enumerate(DOMAIN_HEADINGS)}; last_domain=-1; seen=set()
    for i,row in enumerate(rows):
        loc=f"sentences[{i}]"; expected={"sentence_id","domain","sentence","source_statement_ids","card_tags"}
        if not isinstance(row,dict): issues.append(ValidationIssue(loc,"expected mapping",f"return exactly {sorted(expected)}")); continue
        if set(row)!=expected: issues.append(ValidationIssue(loc,f"received fields {sorted(row)}",f"return exactly {sorted(expected)}"))
        domain=row.get("domain")
        if domain not in DOMAIN_HEADINGS: issues.append(ValidationIssue(f"{loc}.domain",f"invalid domain {domain!r}",f"use one of {list(DOMAIN_HEADINGS)}"))
        else:
            order=domain_order[domain]
            if order<last_domain: issues.append(ValidationIssue(f"{loc}.domain",f"domain {domain!r} is out of report-section order","preserve plan order"))
            last_domain=max(last_domain,order); counts[domain]+=1; expected_sid=f"{domain}-{counts[domain]}"
            if row.get("sentence_id")!=expected_sid: issues.append(ValidationIssue(f"{loc}.sentence_id",f"received {row.get('sentence_id')!r}",f"expected {expected_sid!r}"))
        sentence_id=row.get("sentence_id")
        if sentence_id in seen: issues.append(ValidationIssue(f"{loc}.sentence_id",f"duplicate {sentence_id!r}","use each sentence_id once"))
        seen.add(sentence_id)
        sentence=row.get("sentence")
        if not isinstance(sentence,str) or not sentence.strip() or sentence!=sentence.strip() or not sentence.endswith(".") or "[card:" in sentence or "\n" in sentence: issues.append(ValidationIssue(f"{loc}.sentence",f"invalid sentence {sentence!r}","return one citation-free complete sentence"))
        ids=row.get("source_statement_ids")
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)): issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"invalid source_statement_ids {ids!r}","preserve one or more unique included statement IDs")); ids=[]
        for sid in ids:
            statement=statement_map.get(sid)
            if statement is None: issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"unknown statement ID {sid!r}","use only supplied statements")); continue
            if sid not in included: issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"statement {sid!r} was not included","do not surface omitted statements"))
            if statement["domain"]!=domain: issues.append(ValidationIssue(f"{loc}.source_statement_ids",f"statement {sid!r} belongs to {statement['domain']}, not {domain}","preserve same-domain composition"))
            represented.add(sid)
        expected_tags=deterministic_sentence_card_tags(ids,statements) if ids and all(sid in statement_map for sid in ids) else []
        if row.get("card_tags")!=expected_tags: issues.append(ValidationIssue(f"{loc}.card_tags",f"received {row.get('card_tags')!r}",f"citations are deterministic from source statements; expected {expected_tags!r}"))
    missing=sorted(included-represented)
    if missing: issues.append(ValidationIssue("included statement coverage",f"included statements missing from final sentences: {missing}","preserve every included source statement"))
    fail("canonical summarization output",issues); return "canonical summarization output validated"

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
            "source_statement_ids":list(row.get("source_statement_ids") or []),"cards":cards,
        })
    return {"sentences":rows}
