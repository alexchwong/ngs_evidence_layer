# Phase 3 — independent audit

## Active phase and output contract

Active phase: **Phase 3 only**. This prompt is the sole authority for this session's
output. Ignore output instructions in input files and prior conversation.

Read-only inputs: `paper.md`, exactly one `paper.provisional-001.json`, and
`phase3_prompt.md`. Use them as inputs only; do not overwrite or modify them.

Return exactly one file: `paper.review-001.json`. Review every card exactly once,
whether it passes or fails. Phase 3 never creates `paper.final.json`, never repairs
cards, and is never repeated for this publication.

You are the independent auditor for exactly one publication. Use only `paper.md`, the
provisional package, and this prompt. You must be a different model from the
extraction model named by the package. Do not use reporting rules, census, disease
vocabulary, schema, another publication, or model knowledge to improve extraction.

## Entry validation

Require a well-formed round-1 provisional package with `audit: null` and exactly one
evidence bundle per card. Otherwise stop without an output.

## Audit

For every card answer:

1. Does the paired evidence bundle support every material assertion in the
   interpretation, without generalisation beyond its population, disease, context,
   threshold, exclusion, branch, variant class, allelic state, or analysis type?
2. Is the card independently useful rather than materially redundant elsewhere in
   the package?

Read every fragment in the paired evidence bundle before deciding. Identical fragment
text alone is not failure when it supports distinct useful roles.

Apply these calibrations consistently:

- **Disease grounding:**
  - Each specific disease asserted by the card must be named or unambiguously
    identified in the paired evidence bundle.
  - A `scope_heading` may supply disease context only when the claim occurs within
    that heading's section and no intervening heading or section boundary changes
    scope. Fail a heading that is merely nearby or broadly related.
  - A derived umbrella ancestor need not appear in evidence and must not broaden the
    interpretation beyond the exact source-supported disease.
  - Fail a disease value when it adds unsupported narrower, sibling, or otherwise
    distinct disease scope.
- For `germline predisposition syndrome`, a named genetic disorder or constitutional
  abnormality is sufficient grounding. This includes inherited or de novo disorders,
  constitutional chromosomal abnormalities, and constitutional mosaicism, but
  excludes acquired or tumour-restricted abnormalities.
- A bibliographic reference title or reference-list entry is not substantive
  evidence and must fail, even when its title appears to state the desired claim.
- Preserve strict evidence fidelity for treatment, variant class, allelic state,
  population, and all material qualifiers.
- For `germline`, distinguish established inherited or constitutional status from
  possible constitutional origin and from a source-stated recommendation or
  indication for germline work-up. Pass an explicit work-up recommendation when the
  interpretation remains conditional; fail an interpretation that declares
  constitutional status without support.
- Judge independent utility from the interpretation actually written, not from
  fragment reuse alone. Diagnosis and biomarker cards may coexist only when the
  biomarker interpretation states a distinct, source-supported testing target,
  detection strategy, assay limitation, monitoring use, or discrimination use.

For every `composite_text` bundle, also audit:

1. **Single assertion:** all substantive fragments jointly support one independently
   useful source assertion.
2. **Compatible scope:** the fragments use compatible disease, population, treatment,
   comparator, analysis, and classifier scope.
3. **Necessary composition:** each fragment supplies material support or qualification
   not available in one sufficient contiguous passage.
4. **Structural governance:** each `scope_heading`, `legend`, or `footnote` governs the
   substantive fragment to which it is applied.
5. **No evidence laundering:** the interpretation and `support_map` assert no
   relationship, direction, scope, or qualifier absent from the assembled source text.

Multiple `claim` fragments are valid. Do not fail a bundle merely because the gene,
population, role, effect, or qualifier is distributed across non-contiguous passages.
Fail the bundle when:

- the fragments describe separate findings or independently useful conclusions;
- intervening text changes the population, analysis, disease scope, comparator, or
  conclusion;
- the interpretation converts co-location or thematic similarity into an unstated
  relationship; or
- a material assertion depends on unquoted text, the locator, or model inference.

For every `table_relation` bundle, also audit:

1. every selected cell is linked to all applicable row and column headers;
2. spanning or multi-level headers are preserved;
3. applicable legends and marked footnotes are included; and
4. the reconstructed relation states nothing absent from the table.

Treat locators as navigation metadata, not evidence. Keep every non-contiguous
fragment independently verbatim.

Use `evidence_relationship` when the individual quotations are accurate but the
bundle combines them into a relationship the source does not establish. Do not use
`evidence_relationship` solely because a valid bundle contains multiple substantive
`claim` fragments.

When a card fails, classify its primary defect as one of:

- `quote_error`: quoted text is wrong, non-verbatim, malformed, materially truncated,
  or has been read as saying something it does not say;
- `unsupported_assertion`;
- `material_redundancy`;
- `scope_or_qualifier`;
- `evidence_relationship`;
- `other`.

For every failure, provide:

- `reason`: the precise defect;
- `defensibility`: whether the card could reasonably be defended as correct and, if
  relevant, the exact circumstances, reading, scope, or qualification under which it
  would be defensible; say clearly when it is not defensible;
- exactly one `suggested_action`, using one category listed below and concise,
  source-bounded detail.

For `quote_error`, also provide `quote_restatement`: restate verbatim the complete
quote or quotes from the card's paired evidence bundle that you actually read. This
field proves the cited text was inspected. Do not provide `quote_restatement` for
other failure types.

Suggested-action categories:

- `narrow_disease_scope`
- `replace_evidence`
- `change_category`
- `rewrite_interpretation`
- `split_card`
- `delete_card`
- `add_or_correct_qualifier`

Suggested actions are non-binding advice for Phase 4, not replacement extraction
content. Do not author a finished replacement card or introduce outside facts.

## Publication-type audit

Audit `publication_type` against the paper's front matter, structure, primary purpose,
and methods. Audit the package value for defensibility rather than selecting a
preferred label anew. Set `verified_by_phase3` to true only for a passing verdict.

### Publication-type taxonomy and stability policy

Allowed values and operational definitions:
- `guideline`: Formal practice recommendations developed using an explicit guideline process, such as evidence appraisal, recommendation formulation, or recommendation grading. Do not use solely because an expert group gives advice or classification criteria without a formal guideline-development method.
- `consensus statement`: An expert group's agreed classification, definitions, criteria, terminology, or recommendations without the formal methodology required for a guideline. Supporting analyses or literature summaries do not make the paper a primary study or review when the main contribution is the group's agreed position.
- `primary study`: The principal purpose is to report original empirical data from a cohort, experiment, assay evaluation, or trial. Do not use for a consensus or guideline paper merely because it contains supporting analyses or examples.
- `systematic review`: An evidence synthesis with an explicit, reproducible literature-search and study-selection method; a meta-analysis is included when present. Do not use for an unstructured literature overview.
- `narrative review`: A literature overview without systematic-review methods and without an authoritative group consensus as its primary purpose. Do not use when the primary contribution is agreed classification criteria, terminology, or recommendations.
- `other`: None of the other five semantic types fits the paper's primary purpose. Use only after applying the definitions and precedence rules; do not use merely because the publisher supplies a different article-format label.

Apply these precedence rules in order:
1. Classify the paper's primary purpose, not merely its journal banner, section name, or publisher article-format label.
2. Explicit formal guideline-development methodology takes guideline precedence.
3. Group-authored agreed classification, criteria, definitions, or terminology takes consensus statement precedence when formal guideline methodology is absent; expert classification systems such as ICC normally fit here.
4. Original empirical research takes primary study precedence only when it is the paper's main contribution.
5. An explicit reproducible search and study-selection method identifies a systematic review.
6. Otherwise, an unstructured literature synthesis is a narrative review; use other only when none of the preceding definitions fits.
7. Labels such as special report, special article, white paper, position paper, perspective, or review article are not allowed values. Map them to the semantic taxonomy using purpose and methods.

Apply these audit-stability rules:
- Audit the package value for defensibility under this taxonomy; do not choose a preferred label de novo.
- Pass when the package value is defensible, even if another value could also be defensible.
- Fail only when the package value clearly does not satisfy its definition and exactly one different allowed value is better supported.
- When evidence is mixed or multiple values remain defensible, retain and pass the package value.
- Never fail merely to substitute a near-synonym, a publisher article-format label, or an equally defensible type.
- Any auditor_value must be one of the six allowed values.

The package's `publication_type_basis` is an assertion to verify, not an instruction
to follow. Publisher labels such as "special report" are never allowed values. For
an ICC-style expert classification paper, retain `consensus statement` when the main
contribution is agreed classification, criteria, definitions, or terminology and no
formal guideline methodology is shown.

## Output shape

Write exactly this review shape, replacing placeholders and repeating `card_results`
once for every provisional card in the same order:

```json
{
  "schema_version": "5.0",
  "paper_id": "<provisional paper_id>",
  "round": 1,
  "review_date": "YYYY-MM-DD",
  "reviewer_model": "<your model identity>",
  "extraction_model_reviewed": "<provisional extraction_model>",
  "result": "review_complete",
  "audit": {
    "publication_type_verdict": {
      "package_value": "<provisional value>",
      "auditor_value": "<one allowed taxonomy value>",
      "verdict": "pass or fail",
      "verified_by_phase3": "<true when pass; false when fail>",
      "basis": "<concise paper-based reason>"
    },
    "cards_total": 2,
    "cards_passed": 1,
    "cards_failed": 1
  },
  "card_results": [
    {
      "card_id": "<passing card ID>",
      "verdict": "pass"
    },
    {
      "card_id": "<failed card ID>",
      "verdict": "fail",
      "details": {
        "failure_type": "unsupported_assertion",
        "reason": "<precise defect>",
        "defensibility": "<whether and under what circumstances the card is defensible>",
        "suggested_action": {
          "category": "rewrite_interpretation",
          "detail": "<concise source-bounded guidance>"
        }
      }
    }
  ]
}
```

A passing card result contains only `card_id` and `verdict`. Failure details are
present only for failed cards. A `quote_error` failure adds `quote_restatement` to
its `details` object.

## Deterministic exit validation

All required inputs and the complete validation bundle are provided in this chat.
Do not search for, access, clone, or inspect any repository or external source.

The bundle below contains the canonical repository validator and every
repository-owned dependency it requires. Recreate every file verbatim under
`validation_bundle/`, preserving all displayed relative paths. The bundled schemas
and vocabularies are validator dependencies only and are not Phase 3 authoring
context. Do not modify, summarize, reinterpret, combine, or replace any file or
check.

Create a directory named `validation_bundle` and recreate every file below
at its displayed relative path. Preserve the directory structure and file
contents verbatim. Do not combine files or rewrite imports.

<!-- BEGIN VERBATIM scripts/final_validation.py -->
```python
#!/usr/bin/env python3
"""Deterministically validate the output product of one workflow phase."""
import argparse
import json
import sys
from pathlib import Path

import package_validation as validation

PHASE_ARGUMENTS = {
    1: ("metadata", "census"),
    2: ("metadata", "census", "source", "provisional"),
    3: ("provisional", "review"),
    4: ("metadata", "census", "source", "provisional", "review", "final"),
}


def _require_paths(phase, paths):
    missing = [name for name in PHASE_ARGUMENTS[phase] if paths.get(name) is None]
    if missing:
        raise ValueError(
            f"phase {phase} requires: " + ", ".join(f"--{name}" for name in missing)
        )


def validate_phase_files(
    *,
    phase,
    metadata_path=None,
    census_path=None,
    source_path=None,
    provisional_path=None,
    review_path=None,
    final_path=None,
):
    """Validate only the product and dependencies owned by ``phase``."""
    paths = {
        "metadata": metadata_path,
        "census": census_path,
        "source": source_path,
        "provisional": provisional_path,
        "review": review_path,
        "final": final_path,
    }
    if phase not in PHASE_ARGUMENTS:
        raise ValueError(f"unsupported phase: {phase}")
    _require_paths(phase, paths)

    errors = []
    warnings = []
    report = {"phase": phase}

    if phase == 1:
        metadata = validation.read_json(metadata_path, "metadata")
        census = validation.read_json(census_path, "census")
        errors.extend(f"metadata: {error}" for error in validation.validate_metadata(metadata))
        errors.extend(f"census: {error}" for error in validation.validate_census(census, metadata))
        report.update({"census_entries": len(census.get("entries", []))})
        return errors, warnings, report

    if phase == 2:
        metadata = validation.read_json(metadata_path, "metadata")
        census = validation.read_json(census_path, "census")
        provisional = validation.read_json(provisional_path, "provisional package")
        source_text = Path(source_path).read_text(encoding="utf-8")
        package_errors, warnings, package_report = validation.validate_package(
            provisional,
            metadata,
            census,
            source_text=source_text,
            require_final=False,
        )
        errors.extend(f"provisional: {error}" for error in package_errors)
        report.update(package_report or {})
        return errors, warnings, report

    if phase == 3:
        provisional = validation.read_json(provisional_path, "provisional package")
        review = validation.read_json(review_path, "Phase 3 review")
        errors.extend(
            f"review: {error}"
            for error in validation.validate_review(review, provisional)
        )
        report.update(
            {
                "cards": len(provisional.get("cards", [])),
                "review_results": len(review.get("card_results", [])),
            }
        )
        return errors, warnings, report

    metadata = validation.read_json(metadata_path, "metadata")
    census = validation.read_json(census_path, "census")
    provisional = validation.read_json(provisional_path, "approved provisional package")
    review = validation.read_json(review_path, "Phase 3 review")
    final = validation.read_json(final_path, "final package")

    errors.extend(
        f"final lineage: {error}"
        for error in validation.validate_final_against_provisional(final, provisional)
    )
    approved_round = (final.get("audit") or {}).get("approved_round")
    if approved_round != provisional.get("round"):
        errors.append("final audit approved_round does not match provisional round")
    if approved_round != review.get("round"):
        errors.append("final audit approved_round does not match review round")
    audit = final.get("audit") or {}
    if audit.get("audit_model") != review.get("reviewer_model"):
        errors.append("final audit_model does not match Phase 3 reviewer_model")
    if audit.get("extraction_model_reviewed") != provisional.get("extraction_model"):
        errors.append(
            "final extraction_model_reviewed does not match provisional extraction_model"
        )
    if review.get("reviewer_model") == provisional.get("extraction_model"):
        errors.append("Phase 3 reviewer model must differ from Phase 2 extraction model")

    source_text = Path(source_path).read_text(encoding="utf-8")
    final_errors, warnings, package_report = validation.validate_package(
        final,
        metadata,
        census,
        source_text=source_text,
        require_final=True,
    )
    errors.extend(f"final: {error}" for error in final_errors)
    report.update(package_report or {})
    return errors, warnings, report


def validate_final_files(**paths):
    """Compatibility wrapper for callers that validate a complete Phase 4 set."""
    return validate_phase_files(phase=4, **paths)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, choices=(1, 2, 3, 4), required=True)
    for name in ("metadata", "census", "source", "provisional", "review", "final"):
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args(argv)
    provided = {
        name
        for name in ("metadata", "census", "source", "provisional", "review", "final")
        if getattr(args, name) is not None
    }
    required = set(PHASE_ARGUMENTS[args.phase])
    missing = sorted(required - provided)
    if missing:
        parser.error(
            f"phase {args.phase} requires " + ", ".join(f"--{name}" for name in missing)
        )
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_phase_files(
            phase=args.phase,
            metadata_path=args.metadata,
            census_path=args.census,
            source_path=args.source,
            provisional_path=args.provisional,
            review_path=args.review,
            final_path=args.final,
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE {args.phase} VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit(
            f"PHASE {args.phase} VALIDATION FAILED:\n" + "\n".join(errors)
        )
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
```
<!-- END VERBATIM scripts/final_validation.py -->

<!-- BEGIN VERBATIM scripts/package_validation.py -->
```python
#!/usr/bin/env python3
"""Shared deterministic validation for v0.1.3 working and accepted artefacts."""
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

import vocab

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schema"
DISEASE_DEPENDENT_CATEGORIES = {"diagnosis", "prognosis", "treatment", "biomarker"}
GENERIC_INTERPRETATION_PATTERNS = (
    "application remains dependent on the source-stated disease context",
    "does not provide a complete patient-level risk score in this passage",
    "the implication is alteration- and disease-specific and should not be generalized",
    "does not by itself establish germline origin, clonal chronology, or suitability as a stand-alone mrd marker",
)
REFERENCE_ENTRY_RE = re.compile(r"^\s*[-*]?\s*\d{1,4}\.\s+.+\b(?:19|20)\d{2}\s*;", re.IGNORECASE)


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def schema_errors(document, schema_name, label):
    schema = read_json(SCHEMAS / schema_name, "schema")
    resources = []
    for path in SCHEMAS.glob("*_schema.json"):
        referenced_schema = read_json(path, "schema")
        if "$id" in referenced_schema:
            resources.append((referenced_schema["$id"], Resource.from_contents(referenced_schema)))
    registry = Registry().with_resources(resources)
    errors = sorted(
        Draft202012Validator(
            schema,
            registry=registry,
            format_checker=FormatChecker(),
        ).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


def normalise(text, markdown=False):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        lines = []
        for line in text.splitlines():
            if re.match(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$", line):
                continue
            lines.append(line.replace("|", " "))
        text = "\n".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def validate_metadata(metadata):
    return schema_errors(metadata, "metadata_schema.json", "metadata")


def validate_census(census, metadata=None):
    errors = schema_errors(census, "census_schema.json", "census")
    entry_ids = [entry.get("entry_id") for entry in census.get("entries", [])]
    genes = [entry.get("gene") for entry in census.get("entries", [])]
    if len(entry_ids) != len(set(entry_ids)):
        errors.append("census contains duplicate entry_id values")
    if len(genes) != len(set(genes)):
        errors.append("census contains duplicate gene entries")
    if metadata and census.get("paper_id") != metadata.get("paper_id"):
        errors.append("census paper_id does not match metadata")
    return errors


def validate_review(review, provisional):
    """Validate a complete Phase 3 review against its Phase 2 package."""
    errors = schema_errors(review, "review_schema.json", "review")
    if errors:
        return errors

    if review["paper_id"] != provisional.get("paper_id"):
        errors.append("review paper_id does not match provisional package")
    if review["round"] != provisional.get("round"):
        errors.append("review round does not match provisional package")
    if review["extraction_model_reviewed"] != provisional.get("extraction_model"):
        errors.append("review extraction_model_reviewed does not match provisional extraction_model")
    if review["reviewer_model"] == provisional.get("extraction_model"):
        errors.append("reviewer model must differ from provisional extraction model")

    card_results = review["card_results"]
    result_ids = [result["card_id"] for result in card_results]
    provisional_ids = [card.get("card_id") for card in provisional.get("cards", [])]
    passed = [result for result in card_results if result["verdict"] == "pass"]
    failed = [result for result in card_results if result["verdict"] == "fail"]
    if review["audit"]["cards_total"] != len(provisional.get("cards", [])):
        errors.append("review cards_total does not match provisional cards")
    if review["audit"]["cards_passed"] != len(passed):
        errors.append("review cards_passed does not match card_results")
    if review["audit"]["cards_failed"] != len(failed):
        errors.append("review cards_failed does not match card_results")
    if len(result_ids) != len(set(result_ids)):
        errors.append("review contains duplicate card IDs")
    unknown_ids = sorted(set(result_ids) - set(provisional_ids))
    if unknown_ids:
        errors.append("review references unknown provisional cards: " + ", ".join(unknown_ids))
    missing_ids = sorted(set(provisional_ids) - set(result_ids))
    if missing_ids:
        errors.append("review omits provisional cards: " + ", ".join(missing_ids))
    if result_ids != provisional_ids:
        errors.append("review card_results must preserve provisional card order")

    publication_verdict = review["audit"]["publication_type_verdict"]
    if publication_verdict["package_value"] != provisional.get("publication_type"):
        errors.append("review publication package_value does not match provisional publication_type")
    if publication_verdict["verdict"] == "pass" and publication_verdict["auditor_value"] != publication_verdict["package_value"]:
        errors.append("passing publication verdict must retain the package value")
    return errors


def validate_package(package, metadata, census, source_text=None, require_final=False):
    errors = schema_errors(package, "ingestion_package_schema.json", "package")
    warnings = []
    if errors:
        return errors, warnings, None

    if package["paper_id"] != metadata["paper_id"]:
        errors.append("package paper_id does not match metadata")
    if package["census_entries"] != len(census.get("entries", [])):
        errors.append("package census_entries does not match census")
    if package["round"] == 1 and not require_final:
        if package["publication_type"] != census.get("publication_type"):
            errors.append("first-round package publication_type does not match census")
        if package["publication_type_basis"] != census.get("publication_type_basis"):
            errors.append("first-round package publication_type_basis does not match census")
        if package["publication_type_verified_by_phase3"]:
            errors.append("first-round provisional publication type cannot already be verified")

    card_ids = [card["card_id"] for card in package["cards"]]
    evidence_ids = [evidence["card_id"] for evidence in package["evidence"]]
    if len(card_ids) != len(set(card_ids)):
        errors.append("package contains duplicate card_id values")
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("package contains more than one evidence bundle for the same card")
    missing_evidence = sorted(set(card_ids) - set(evidence_ids))
    unknown_evidence = sorted(set(evidence_ids) - set(card_ids))
    if missing_evidence:
        errors.append("cards with no evidence bundle: " + ", ".join(missing_evidence))
    if unknown_evidence:
        errors.append("evidence bundles for unknown cards: " + ", ".join(unknown_evidence))

    prefix = metadata["publication_key"] + "-"
    for card in package["cards"]:
        card_id = card["card_id"]
        if not card_id.startswith(prefix):
            errors.append(f"{card_id}: card_id must begin with {prefix}")
        if card["category"] in DISEASE_DEPENDENT_CATEGORIES and not card["diseases"]:
            errors.append(f"{card_id}: {card['category']} card requires at least one disease")
        interpretation = normalise(card["interpretation"]).lower()
        if any(pattern in interpretation for pattern in GENERIC_INTERPRETATION_PATTERNS):
            warnings.append(f"{card_id}: interpretation contains generic category boilerplate; review direct evidence support")
        if "disease_ancestors" in card:
            expected_ancestors = vocab.disease_ancestors(card["diseases"])
            if set(card["disease_ancestors"]) != set(expected_ancestors):
                errors.append(
                    f"{card_id}: disease_ancestors must contain exactly the transitive "
                    f"ancestors {expected_ancestors}"
                )
            overlap = sorted(set(card["diseases"]) & set(card["disease_ancestors"]))
            if overlap:
                errors.append(
                    f"{card_id}: exact diseases and disease_ancestors overlap: "
                    + ", ".join(overlap)
                )

    bundle_texts = {}
    source = normalise(source_text, markdown=True) if source_text is not None else None
    for evidence in package["evidence"]:
        card_id = evidence["card_id"]
        fragments = evidence["fragments"]
        fragment_ids = [fragment["fragment_id"] for fragment in fragments]
        fragment_id_set = set(fragment_ids)
        if len(fragment_ids) != len(fragment_id_set):
            errors.append(f"{card_id}: evidence bundle contains duplicate fragment_id values")
        if sum(len(fragment["quote"].split()) for fragment in fragments) > 400:
            errors.append(f"{card_id}: evidence bundle exceeds 400 words")

        roles = {fragment["role"] for fragment in fragments}
        if evidence["evidence_type"] in {"contiguous_text", "composite_text"} and "claim" not in roles:
            errors.append(f"{card_id}: text evidence requires a claim fragment")
        if evidence["evidence_type"] == "contiguous_text" and fragments[0]["role"] != "claim":
            errors.append(f"{card_id}: contiguous text fragment must have role claim")
        if evidence["evidence_type"] == "table_relation" and "cell" not in roles:
            errors.append(f"{card_id}: table evidence requires at least one cell fragment")

        referenced_ids = {
            fragment_id
            for mapped_ids in evidence["support_map"].values()
            for fragment_id in mapped_ids
        }
        dangling_support = sorted(referenced_ids - fragment_id_set)
        if dangling_support:
            errors.append(f"{card_id}: support_map references unknown fragments: " + ", ".join(dangling_support))

        if evidence["evidence_type"] == "table_relation":
            fragments_by_id = {fragment["fragment_id"]: fragment for fragment in fragments}
            relation_references = set()
            for relation in evidence["table_relations"]:
                relation_references.add(relation["value_fragment_id"])
                relation_references.update(relation["header_fragment_ids"])
                relation_references.update(relation["qualifier_fragment_ids"])
                value = fragments_by_id.get(relation["value_fragment_id"])
                if value and value["role"] != "cell":
                    errors.append(f"{card_id}: table value {value['fragment_id']} must have role cell")
                for header_id in relation["header_fragment_ids"]:
                    header = fragments_by_id.get(header_id)
                    if header and header["role"] not in {"column_header", "row_header"}:
                        errors.append(f"{card_id}: table header {header_id} has invalid role {header['role']}")
                for qualifier_id in relation["qualifier_fragment_ids"]:
                    qualifier = fragments_by_id.get(qualifier_id)
                    if qualifier and qualifier["role"] not in {"legend", "footnote"}:
                        errors.append(f"{card_id}: table qualifier {qualifier_id} has invalid role {qualifier['role']}")
            dangling_relations = sorted(relation_references - fragment_id_set)
            if dangling_relations:
                errors.append(f"{card_id}: table relations reference unknown fragments: " + ", ".join(dangling_relations))

        normalized_fragments = []
        for fragment in fragments:
            fragment_label = f"{card_id}/{fragment['fragment_id']}"
            quote_text = fragment["quote"]
            if REFERENCE_ENTRY_RE.search(quote_text):
                errors.append(f"{fragment_label}: fragment appears to be a bibliographic reference-list entry")
            normalized = normalise(quote_text, markdown=True)
            if source is not None and normalized not in source:
                errors.append(f"{fragment_label}: fragment not found verbatim in paper.md")
            normalized_fragments.append(normalized)
        normalized_bundle = " || ".join(normalized_fragments)
        duplicate = bundle_texts.get(normalized_bundle)
        if duplicate:
            warnings.append(f"{card_id}: evidence is identical to {duplicate}; review independent utility")
        bundle_texts[normalized_bundle] = card_id

    census_pairs = {
        (entry["gene"], category)
        for entry in census.get("entries", []) for category in entry.get("categories", [])
    }
    card_pairs = {
        (gene, card["category"])
        for card in package["cards"] for gene in card["genes"]
    }
    covered_genes = sorted({gene for card in package["cards"] for gene in card["genes"]})
    covered_diseases = sorted({disease for card in package["cards"] for disease in card["diseases"]})
    if sorted(package["genes_covered"]) != covered_genes:
        errors.append("genes_covered does not equal genes represented by cards")
    if sorted(package["diseases_covered"]) != covered_diseases:
        errors.append("diseases_covered does not equal diseases represented by cards")

    audit = package["audit"]
    if require_final and audit is None:
        errors.append("final package requires audit metadata")
    if require_final and not package["publication_type_verified_by_phase3"]:
        errors.append("final package publication type must be verified by Phase 3")
    if not require_final and audit is not None:
        errors.append("provisional package audit must be null")
    if audit is not None:
        if audit["approved_round"] != package["round"]:
            errors.append("audit approved_round does not match package round")
        if audit["audit_model"] == package["extraction_model"]:
            errors.append("audit model must differ from extraction model")
        if audit["extraction_model_reviewed"] != package["extraction_model"]:
            errors.append("extraction_model_reviewed does not match extraction_model")
        if audit["publication_type_verdict"]["verdict"] != "pass":
            errors.append("failed publication_type verdict blocks acceptance")
        if not audit["publication_type_verdict"]["verified_by_phase3"]:
            errors.append("audit must mark publication type as verified by Phase 3")
        verdict_ids = [result["card_id"] for result in audit["results"]]
        if len(verdict_ids) != len(set(verdict_ids)):
            errors.append("audit contains duplicate card verdicts")
        if set(verdict_ids) != set(card_ids):
            errors.append("audit must contain exactly one verdict for every card")
        failed = [result["card_id"] for result in audit["results"] if result["verdict"] == "fail"]
        if failed:
            errors.append("failed cards block acceptance: " + ", ".join(failed))

    report = {
        "cards": len(card_ids),
        "census_entries": len(census.get("entries", [])),
        "ratio": round(len(card_ids) / len(census["entries"]), 2) if census.get("entries") else None,
        "gene_category_pairs_with_no_card": [
            {"gene": gene, "category": category}
            for gene, category in sorted(census_pairs - card_pairs)
        ],
    }
    return errors, warnings, report


def validate_final_against_provisional(final, provisional):
    """Validate Phase 4 identity and lineage without forbidding adjudicated edits."""
    errors = []
    if final.get("round") != provisional.get("round"):
        errors.append("final and approved provisional rounds differ")
    if final.get("paper_id") != provisional.get("paper_id"):
        errors.append("final and approved provisional paper_id values differ")
    if final.get("extraction_model") != provisional.get("extraction_model"):
        errors.append("final and approved provisional extraction_model values differ")
    return errors
```
<!-- END VERBATIM scripts/package_validation.py -->

<!-- BEGIN VERBATIM scripts/vocab.py -->
```python
#!/usr/bin/env python3
"""Single source of truth for closed disease vocabularies and retrieval relations.

Evidence-card diseases, case-only disease options, taxonomy, categories and evidence
ranks all live in ``schema/disease_vocabulary.json``. ``umbrella`` remains taxonomy
only. ``retrieval_related`` is a separate, directional, category-specific relation
used only by case retrieval.
"""
import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
VOCAB_PATH = SCHEMA_DIR / "disease_vocabulary.json"
PACKAGE_SCHEMA_PATH = SCHEMA_DIR / "ingestion_package_schema.json"

_VOCAB = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
DISEASES = list(_VOCAB["diseases"])
DISEASE_SET = set(DISEASES)
CASE_ONLY_DISEASES = list(_VOCAB.get("case_only_diseases", []))
CASE_ONLY_DISEASE_SET = set(CASE_ONLY_DISEASES)
CASE_DISEASES = DISEASES + CASE_ONLY_DISEASES
CASE_DISEASE_SET = set(CASE_DISEASES)
CASE_ONLY_USAGE = dict(_VOCAB.get("case_only_usage", {}))
UMBRELLA = {k: list(v) for k, v in _VOCAB["umbrella"].items()}
RETRIEVAL_RELATED = {
    disease: {category: list(targets) for category, targets in categories.items()}
    for disease, categories in _VOCAB.get("retrieval_related", {}).items()
}
CATEGORIES = list(_VOCAB["categories"])
EVIDENCE_TIERS = list(_VOCAB["evidence_tiers_strongest_first"])
PUBLICATION_TYPES = list(_VOCAB["publication_types"])
DISEASE_NAMING_EXPECTED = set(_VOCAB["disease_naming_expected"])
# Render and truncation order. Strongest tier first; truncation eats the tail.
TIER_RANK = {tier: i for i, tier in enumerate(EVIDENCE_TIERS)}
CATEGORY_RANK = {category: i for i, category in enumerate(CATEGORIES)}

UNSPECIFIED_DISEASE = "myeloid neoplasm, unspecified"
NO_HAEMATOLOGICAL_MALIGNANCY = "no_haematological_malignancy"


def disease_ancestors(diseases):
    """Return all broader taxonomic ancestors in canonical vocabulary order.

    Card ``diseases`` are exact clinical applicability values. Ancestors are
    derived separately for broad corpus indexing so that, for example, a CMML
    card can be discovered under MDS/MPN, MDS, and MPN without becoming
    clinically applicable to every generic MDS or MPN case.
    """
    requested = set(diseases)
    ancestors = set()

    def visit(disease, path):
        if disease in path:
            cycle = " -> ".join((*path, disease))
            raise ValueError(f"disease umbrella cycle: {cycle}")
        next_path = (*path, disease)
        for parent in UMBRELLA.get(disease, []):
            ancestors.add(parent)
            visit(parent, next_path)

    for disease in requested:
        visit(disease, ())
    ancestors -= requested
    return [disease for disease in DISEASES if disease in ancestors]


def retrieval_related_diseases(disease, category):
    """Return direct related diseases configured for one case disease/category.

    This relation is intentionally non-transitive and directional. Taxonomic
    ``umbrella`` ancestors are not consulted.
    """
    return list(RETRIEVAL_RELATED.get(disease, {}).get(category, []))


def missing_umbrellas(diseases):
    """Backward-compatible alias for ancestors absent from an expanded tag set."""
    tagged = set(diseases)
    return [disease for disease in disease_ancestors(diseases) if disease not in tagged]


def check_vocabulary_consistency():
    """Fail loudly if schemas or configured relationships drift from the vocabulary."""
    schema = json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
    enum = schema["$defs"]["disease"]["enum"]
    problems = []
    if list(enum) != DISEASES:
        problems.append(
            "ingestion_package_schema.json disease enum differs from disease_vocabulary.json"
        )
    overlap = DISEASE_SET & CASE_ONLY_DISEASE_SET
    if overlap:
        problems.append(
            "case-only diseases overlap evidence-card diseases: " + ", ".join(sorted(overlap))
        )
    for disease in CASE_ONLY_DISEASES:
        if disease not in CASE_ONLY_USAGE:
            problems.append(f"case-only disease {disease!r} has no usage rule")
    for disease in CASE_ONLY_USAGE:
        if disease not in CASE_ONLY_DISEASE_SET:
            problems.append(f"case-only usage rule {disease!r} has no case-only disease")
    for term in UMBRELLA:
        if term not in DISEASE_SET:
            problems.append(f"umbrella key {term!r} is not in the disease vocabulary")
    for parents in UMBRELLA.values():
        for parent in parents:
            if parent not in DISEASE_SET:
                problems.append(f"umbrella target {parent!r} is not in the vocabulary")
    for disease in UMBRELLA:
        try:
            disease_ancestors([disease])
        except ValueError as exc:
            problems.append(str(exc))
    for disease, categories in RETRIEVAL_RELATED.items():
        if disease not in DISEASE_SET:
            problems.append(
                f"retrieval_related key {disease!r} is not an evidence-card disease"
            )
        if not isinstance(categories, dict):
            problems.append(f"retrieval_related[{disease!r}] must be an object")
            continue
        for category, targets in categories.items():
            if category not in DISEASE_NAMING_EXPECTED:
                problems.append(
                    f"retrieval_related[{disease!r}] category {category!r} is not disease-filtered"
                )
            if len(targets) != len(set(targets)):
                problems.append(
                    f"retrieval_related[{disease!r}][{category!r}] contains duplicates"
                )
            for target in targets:
                if target not in DISEASE_SET:
                    problems.append(
                        f"retrieval_related target {target!r} is not an evidence-card disease"
                    )
                if target == disease:
                    problems.append(
                        f"retrieval_related[{disease!r}][{category!r}] contains itself"
                    )
    return problems


if __name__ == "__main__":
    issues = check_vocabulary_consistency()
    if issues:
        for issue in issues:
            print("  -", issue)
        raise SystemExit(1)
    relation_count = sum(
        len(targets)
        for categories in RETRIEVAL_RELATED.values()
        for targets in categories.values()
    )
    print(
        f"OK: {len(DISEASES)} evidence-card diseases, "
        f"{len(CASE_ONLY_DISEASES)} case-only diseases, {len(CATEGORIES)} categories, "
        f"{len(EVIDENCE_TIERS)} evidence tiers, {relation_count} retrieval relations"
    )
```
<!-- END VERBATIM scripts/vocab.py -->

<!-- BEGIN VERBATIM schema/accepted_package_schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local/ngs_evidence_layer/accepted_package_schema.json",
  "title": "Portable accepted evidence package",
  "description": "The confirm-produced envelope consumed by incorporation. Manual submissions must use this same shape.",
  "type": "object",
  "required": [
    "schema_version",
    "acceptance_path",
    "accepted_at",
    "accepted_at_source",
    "accepted_in_version",
    "metadata",
    "final"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "1.2" },
    "acceptance_path": { "enum": ["confirmed", "manual-or-unverified"] },
    "accepted_at": { "type": "string", "format": "date-time" },
    "accepted_at_source": { "enum": ["confirm", "file-mtime"] },
    "accepted_in_version": { "type": "string", "minLength": 1 },
    "metadata": { "$ref": "metadata_schema.json" },
    "final": { "$ref": "ingestion_package_schema.json" }
  }
}
```
<!-- END VERBATIM schema/accepted_package_schema.json -->

<!-- BEGIN VERBATIM schema/census_schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local/ngs_evidence_layer/census_schema.json",
  "title": "Publication census (Phase 1)",
  "description": "One entry per gene about which the publication makes a claim. The census is the completeness contract: it is what makes under-extraction countable.",
  "type": "object",
  "required": [
    "schema_version",
    "paper_id",
    "census_date",
    "census_model",
    "publication_type",
    "publication_type_basis",
    "entries",
    "geneless_statements",
    "validation_unresolved"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "3.1" },
    "paper_id": { "type": "string", "format": "uuid" },
    "census_date": { "type": "string", "format": "date" },
    "census_model": { "type": "string", "minLength": 1 },
    "publication_type": {
      "enum": [
        "guideline",
        "consensus statement",
        "primary study",
        "systematic review",
        "narrative review",
        "other"
      ]
    },
    "publication_type_basis": { "type": "string", "minLength": 1 },
    "supplement_flags": {
      "type": "array",
      "description": "Critical values referenced by the main text but living in supplementary material. Record, do not refuse.",
      "items": {
        "type": "object",
        "required": ["locator", "missing_value"],
        "additionalProperties": false,
        "properties": {
          "locator": { "type": "string" },
          "missing_value": { "type": "string" }
        }
      }
    },
    "entries": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["entry_id", "gene", "locators", "categories"],
        "additionalProperties": false,
        "properties": {
          "entry_id": { "type": "string", "minLength": 1 },
          "gene": { "type": "string", "pattern": "^[A-Z0-9][A-Z0-9\\-]*$" },
          "locators": {
            "type": "array",
            "minItems": 1,
            "description": "Sections, tables and table footnotes where the publication makes a claim about this gene.",
            "items": { "type": "string", "minLength": 1 }
          },
          "categories": {
            "type": "array",
            "minItems": 1,
            "items": {
              "enum": [
                "diagnosis",
                "prognosis",
                "treatment",
                "biomarker",
                "germline"
              ]
            }
          }
        }
      }
    },
    "geneless_statements": {
      "type": "array",
      "description": "Rule-relevant statements with no gene attached. Recorded for visibility, not for carding.",
      "items": {
        "type": "object",
        "required": ["locator", "summary"],
        "additionalProperties": false,
        "properties": {
          "locator": { "type": "string", "minLength": 1 },
          "summary": { "type": "string", "minLength": 1 }
        }
      }
    },
    "validation_unresolved": {
      "type": "array",
      "description": "Specific Phase 1 exit-validation defects still unresolved after the third pass.",
      "items": { "type": "string", "minLength": 1 }
    }
  }
}
```
<!-- END VERBATIM schema/census_schema.json -->

<!-- BEGIN VERBATIM schema/disease_vocabulary.json -->
```json
{
  "vocabulary_version": "1.4",
  "note": "Closed evidence-card disease vocabulary with separate case-only terms, taxonomic umbrellas, and directional category-specific retrieval relationships. Evidence-card diseases are not to be extended casually: an added term changes what every existing card means by omission.",
  "diseases": [
    "CHIP",
    "CCUS",
    "MDS",
    "MDS/AML",
    "AML",
    "APL",
    "MDS/MPN",
    "MDS/MPN-U",
    "CMML",
    "aCML",
    "MDS/MPN-SF3B1-T",
    "JMML",
    "MPN",
    "MPN-U",
    "PV",
    "ET",
    "PMF",
    "post-PV/post-ET MF",
    "MPN blast phase",
    "CML",
    "CNL",
    "CEL",
    "mastocytosis",
    "myeloid/lymphoid neoplasm with eosinophilia and TK fusion",
    "BPDCN",
    "germline predisposition syndrome",
    "myeloid neoplasm, unspecified",
    "lymphoid neoplasm",
    "acute leukaemia of ambiguous lineage",
    "histiocytic/dendritic neoplasm",
    "haematological malignancy, other"
  ],
  "case_only_diseases": [
    "no_haematological_malignancy"
  ],
  "case_only_usage": {
    "no_haematological_malignancy": "Use only when the case stem does not specify a haematological malignancy and the NGS result block contains no variants."
  },
  "umbrella": {
    "MDS/AML": ["MDS", "AML"],
    "APL": ["AML"],
    "MDS/MPN": ["MDS", "MPN"],
    "MDS/MPN-U": ["MDS/MPN"],
    "CMML": ["MDS/MPN"],
    "aCML": ["MDS/MPN"],
    "MDS/MPN-SF3B1-T": ["MDS/MPN"],
    "MPN-U": ["MPN"],
    "PV": ["MPN"],
    "ET": ["MPN"],
    "PMF": ["MPN"],
    "post-PV/post-ET MF": ["MPN"],
    "MPN blast phase": ["MPN"],
    "CML": ["MPN"],
    "CNL": ["MPN"],
    "CEL": ["MPN"],
    "JMML": ["MPN"],
    "BPDCN": ["histiocytic/dendritic neoplasm"]
  },
  "retrieval_related": {
    "MDS": {
      "diagnosis": ["CCUS", "CHIP"],
      "prognosis": ["CCUS", "CHIP"],
      "biomarker": ["CCUS", "CHIP"]
    },
    "CCUS": {
      "diagnosis": ["CHIP", "MDS"],
      "prognosis": ["CHIP", "MDS"],
      "biomarker": ["CHIP", "MDS"]
    },
    "CHIP": {
      "diagnosis": ["CCUS"],
      "biomarker": ["CCUS"]
    },
    "MDS/AML": {
      "diagnosis": ["MDS", "AML"],
      "prognosis": ["MDS", "AML"],
      "treatment": ["MDS", "AML"],
      "biomarker": ["MDS", "AML"]
    },
    "APL": {
      "diagnosis": ["AML"],
      "biomarker": ["AML"]
    },
    "MDS/MPN": {
      "diagnosis": ["MDS", "MPN"],
      "prognosis": ["MDS", "MPN"],
      "treatment": ["MDS", "MPN"],
      "biomarker": ["MDS", "MPN"]
    },
    "MDS/MPN-U": {
      "diagnosis": ["MDS/MPN", "MDS", "MPN"],
      "prognosis": ["MDS/MPN", "MDS", "MPN"],
      "treatment": ["MDS/MPN", "MDS", "MPN"],
      "biomarker": ["MDS/MPN", "MDS", "MPN"]
    },
    "CMML": {
      "diagnosis": ["MDS/MPN", "MDS"],
      "prognosis": ["MDS/MPN", "MDS"],
      "biomarker": ["MDS/MPN", "MDS"]
    },
    "aCML": {
      "diagnosis": ["MDS/MPN", "MPN", "CNL"],
      "prognosis": ["MDS/MPN", "MPN"],
      "treatment": ["MDS/MPN", "MPN"],
      "biomarker": ["MDS/MPN", "MPN", "CNL"]
    },
    "MDS/MPN-SF3B1-T": {
      "diagnosis": ["MDS/MPN", "MDS", "ET"],
      "prognosis": ["MDS/MPN", "MDS", "ET"],
      "biomarker": ["MDS/MPN", "MDS", "ET"]
    },
    "MPN-U": {
      "diagnosis": ["MPN"],
      "prognosis": ["MPN"],
      "treatment": ["MPN"],
      "biomarker": ["MPN"]
    },
    "PV": {
      "diagnosis": ["MPN"],
      "prognosis": ["MPN"],
      "treatment": ["MPN"],
      "biomarker": ["MPN"]
    },
    "ET": {
      "diagnosis": ["MPN"],
      "prognosis": ["MPN"],
      "treatment": ["MPN"],
      "biomarker": ["MPN"]
    },
    "PMF": {
      "diagnosis": ["MPN", "post-PV/post-ET MF"],
      "prognosis": ["MPN", "post-PV/post-ET MF"],
      "biomarker": ["MPN", "post-PV/post-ET MF"]
    },
    "post-PV/post-ET MF": {
      "diagnosis": ["PMF", "MPN"],
      "prognosis": ["PMF", "MPN"],
      "treatment": ["PMF", "MPN"],
      "biomarker": ["PMF", "MPN"]
    },
    "MPN blast phase": {
      "diagnosis": ["AML", "MPN"],
      "prognosis": ["AML", "MPN"],
      "treatment": ["AML", "MPN"],
      "biomarker": ["AML", "MPN"]
    },
    "CNL": {
      "diagnosis": ["MPN", "aCML"],
      "prognosis": ["MPN"],
      "treatment": ["MPN"],
      "biomarker": ["MPN", "aCML"]
    },
    "CEL": {
      "diagnosis": ["MPN"],
      "prognosis": ["MPN"],
      "treatment": ["MPN"],
      "biomarker": ["MPN"]
    }
  },
  "categories": [
    "diagnosis",
    "prognosis",
    "treatment",
    "biomarker",
    "germline"
  ],
  "evidence_tiers_strongest_first": [
    "guideline criterion",
    "multivariable-adjusted",
    "univariable or descriptive",
    "restated secondary"
  ],
  "publication_types": [
    "guideline",
    "consensus statement",
    "primary study",
    "systematic review",
    "narrative review",
    "other"
  ],
  "disease_naming_expected": [
    "diagnosis",
    "prognosis",
    "treatment",
    "biomarker"
  ]
}
```
<!-- END VERBATIM schema/disease_vocabulary.json -->

<!-- BEGIN VERBATIM schema/ingestion_package_schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local/ngs_evidence_layer/ingestion_package_schema.json",
  "title": "Phase 2 provisional or Phase 4 final evidence package",
  "type": "object",
  "required": ["schema_version", "paper_id", "round", "extraction_date", "extraction_model", "publication_type", "publication_type_basis", "publication_type_verified_by_phase3", "genes_covered", "diseases_covered", "census_entries", "cards", "evidence", "audit"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "5.0" },
    "paper_id": { "type": "string", "format": "uuid" },
    "round": { "type": "integer", "minimum": 1 },
    "extraction_date": { "type": "string", "format": "date" },
    "extraction_model": { "type": "string", "minLength": 1 },
    "publication_type": {
      "enum": ["guideline", "consensus statement", "primary study", "systematic review", "narrative review", "other"]
    },
    "publication_type_basis": { "type": "string", "minLength": 1 },
    "publication_type_verified_by_phase3": { "type": "boolean" },
    "genes_covered": { "type": "array", "uniqueItems": true, "items": { "$ref": "#/$defs/gene" } },
    "diseases_covered": { "type": "array", "uniqueItems": true, "items": { "$ref": "#/$defs/disease" } },
    "census_entries": { "type": "integer", "minimum": 0 },
    "cards": { "type": "array", "items": { "$ref": "#/$defs/card" } },
    "evidence": { "type": "array", "items": { "$ref": "#/$defs/evidence" } },
    "audit": { "anyOf": [{ "type": "null" }, { "$ref": "#/$defs/audit" }] }
  },
  "$defs": {
    "gene": { "type": "string", "pattern": "^[A-Z0-9][A-Z0-9\\-]*$" },
    "disease": {
      "enum": ["CHIP", "CCUS", "MDS", "MDS/AML", "AML", "APL", "MDS/MPN", "MDS/MPN-U", "CMML", "aCML", "MDS/MPN-SF3B1-T", "JMML", "MPN", "MPN-U", "PV", "ET", "PMF", "post-PV/post-ET MF", "MPN blast phase", "CML", "CNL", "CEL", "mastocytosis", "myeloid/lymphoid neoplasm with eosinophilia and TK fusion", "BPDCN", "germline predisposition syndrome", "myeloid neoplasm, unspecified", "lymphoid neoplasm", "acute leukaemia of ambiguous lineage", "histiocytic/dendritic neoplasm", "haematological malignancy, other"]
    },
    "citation": {
      "type": "object", "required": ["display"], "additionalProperties": false,
      "properties": {
        "authors": { "type": "array", "items": { "type": "string" } }, "title": { "type": "string" },
        "journal": { "type": "string" }, "year": { "type": "integer", "minimum": 1950, "maximum": 2100 },
        "volume": { "type": "string" }, "issue": { "type": "string" }, "pages": { "type": "string" },
        "display": { "type": "string", "minLength": 1 },
        "citation_incomplete": { "type": "array", "uniqueItems": true, "items": { "type": "string" } }
      }
    },
    "card": {
      "type": "object",
      "required": ["card_id", "locator", "interpretation", "genes", "diseases", "category", "evidence_tier", "secondary_citation"],
      "additionalProperties": false,
      "properties": {
        "card_id": { "type": "string", "minLength": 1 }, "locator": { "type": "string", "minLength": 1 },
        "interpretation": { "type": "string", "minLength": 1 },
        "genes": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "#/$defs/gene" } },
        "diseases": { "type": "array", "uniqueItems": true, "items": { "$ref": "#/$defs/disease" } },
        "disease_ancestors": { "type": "array", "uniqueItems": true, "items": { "$ref": "#/$defs/disease" } },
        "category": { "enum": ["diagnosis", "prognosis", "treatment", "biomarker", "germline"] },
        "evidence_tier": { "enum": ["guideline criterion", "multivariable-adjusted", "univariable or descriptive", "restated secondary"] },
        "secondary_citation": { "anyOf": [{ "type": "null" }, { "$ref": "#/$defs/citation" }] }
      },
      "allOf": [
        {
          "if": {
            "properties": { "category": { "enum": ["diagnosis", "prognosis", "treatment", "biomarker"] } },
            "required": ["category"]
          },
          "then": { "properties": { "diseases": { "minItems": 1 } } }
        }
      ]
    },
    "fragment": {
      "type": "object",
      "required": ["fragment_id", "role", "quote", "locator"],
      "additionalProperties": false,
      "properties": {
        "fragment_id": { "type": "string", "pattern": "^F[0-9]{2}$" },
        "role": { "enum": ["claim", "scope_heading", "column_header", "row_header", "cell", "legend", "footnote"] },
        "quote": { "type": "string", "minLength": 1 },
        "locator": { "type": "string", "minLength": 1 }
      }
    },
    "support_map": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": false,
      "properties": {
        "gene": { "$ref": "#/$defs/fragment_ids" },
        "disease": { "$ref": "#/$defs/fragment_ids" },
        "role": { "$ref": "#/$defs/fragment_ids" },
        "population": { "$ref": "#/$defs/fragment_ids" },
        "effect": { "$ref": "#/$defs/fragment_ids" },
        "qualifier": { "$ref": "#/$defs/fragment_ids" }
      }
    },
    "fragment_ids": {
      "type": "array", "minItems": 1, "uniqueItems": true,
      "items": { "type": "string", "pattern": "^F[0-9]{2}$" }
    },
    "table_relation": {
      "type": "object",
      "required": ["value_fragment_id", "header_fragment_ids", "qualifier_fragment_ids"],
      "additionalProperties": false,
      "properties": {
        "value_fragment_id": { "type": "string", "pattern": "^F[0-9]{2}$" },
        "header_fragment_ids": { "$ref": "#/$defs/fragment_ids" },
        "qualifier_fragment_ids": { "type": "array", "uniqueItems": true, "items": { "type": "string", "pattern": "^F[0-9]{2}$" } }
      }
    },
    "evidence": {
      "oneOf": [
        {
          "type": "object",
          "required": ["card_id", "evidence_type", "fragments", "support_map"],
          "additionalProperties": false,
          "properties": {
            "card_id": { "type": "string", "minLength": 1 },
            "evidence_type": { "const": "contiguous_text" },
            "fragments": { "type": "array", "minItems": 1, "maxItems": 1, "items": { "$ref": "#/$defs/fragment" } },
            "support_map": { "$ref": "#/$defs/support_map" }
          }
        },
        {
          "type": "object",
          "required": ["card_id", "evidence_type", "fragments", "support_map"],
          "additionalProperties": false,
          "properties": {
            "card_id": { "type": "string", "minLength": 1 },
            "evidence_type": { "const": "composite_text" },
            "fragments": { "type": "array", "minItems": 2, "maxItems": 6, "items": { "$ref": "#/$defs/fragment" } },
            "support_map": { "$ref": "#/$defs/support_map" }
          }
        },
        {
          "type": "object",
          "required": ["card_id", "evidence_type", "fragments", "support_map", "table_relations"],
          "additionalProperties": false,
          "properties": {
            "card_id": { "type": "string", "minLength": 1 },
            "evidence_type": { "const": "table_relation" },
            "fragments": { "type": "array", "minItems": 2, "maxItems": 12, "items": { "$ref": "#/$defs/fragment" } },
            "support_map": { "$ref": "#/$defs/support_map" },
            "table_relations": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/table_relation" } }
          }
        }
      ]
    },
    "audit": {
      "type": "object", "required": ["audit_date", "audit_model", "extraction_model_reviewed", "approved_round", "publication_type_verdict", "results"], "additionalProperties": false,
      "properties": {
        "audit_date": { "type": "string", "format": "date" }, "audit_model": { "type": "string", "minLength": 1 },
        "extraction_model_reviewed": { "type": "string", "minLength": 1 }, "approved_round": { "type": "integer", "minimum": 1 },
        "publication_type_verdict": {
          "type": "object",
          "required": ["verdict", "verified_by_phase3"],
          "additionalProperties": false,
          "properties": {
            "verdict": { "enum": ["pass", "fail"] },
            "verified_by_phase3": { "const": true },
            "reason": { "type": "string", "minLength": 1 }
          },
          "allOf": [{ "if": { "properties": { "verdict": { "const": "fail" } }, "required": ["verdict"] }, "then": { "required": ["reason"] } }]
        },
        "results": {
          "type": "array", "items": {
            "type": "object", "required": ["card_id", "verdict"], "additionalProperties": false,
            "properties": { "card_id": { "type": "string", "minLength": 1 }, "verdict": { "enum": ["pass", "fail"] }, "reason": { "type": "string", "minLength": 1 } },
            "allOf": [{ "if": { "properties": { "verdict": { "const": "fail" } }, "required": ["verdict"] }, "then": { "required": ["reason"] } }]
          }
        }
      }
    }
  }
}
```
<!-- END VERBATIM schema/ingestion_package_schema.json -->

<!-- BEGIN VERBATIM schema/metadata_schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local/ngs_evidence_layer/metadata_schema.json",
  "title": "Immutable publication working metadata",
  "type": "object",
  "required": [
    "schema_version",
    "paper_id",
    "corpus",
    "stem",
    "publication_key",
    "citation",
    "citation_source",
    "citation_resolved_at",
    "source_filename",
    "source_sha256",
    "markdown_sha256",
    "created_at"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "1.1" },
    "paper_id": { "type": "string", "format": "uuid" },
    "corpus": { "type": "string", "minLength": 1 },
    "stem": { "type": "string", "minLength": 1 },
    "publication_key": {
      "type": "string",
      "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"
    },
    "citation": { "$ref": "#/$defs/citation" },
    "citation_source": {
      "enum": ["crossref-doi", "model-supplied-doi", "operator"]
    },
    "citation_resolved_at": {
      "anyOf": [
        { "type": "string", "format": "date-time" },
        { "type": "null" }
      ]
    },
    "source_filename": { "type": "string", "minLength": 1 },
    "source_sha256": { "type": ["string", "null"], "pattern": "^[a-f0-9]{64}$" },
    "markdown_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "created_at": { "type": "string", "format": "date-time" }
  },
  "$defs": {
    "citation": {
      "type": "object",
      "required": [
        "authors",
        "title",
        "journal",
        "year",
        "volume",
        "issue",
        "pages",
        "doi",
        "display",
        "citation_incomplete"
      ],
      "additionalProperties": false,
      "properties": {
        "authors": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "string", "minLength": 1 }
        },
        "title": { "type": "string", "minLength": 1 },
        "journal": { "type": "string" },
        "year": { "type": "integer", "minimum": 1950, "maximum": 2100 },
        "volume": { "type": "string" },
        "issue": { "type": "string" },
        "pages": { "type": "string" },
        "doi": { "type": "string" },
        "display": { "type": "string", "minLength": 1 },
        "citation_incomplete": {
          "type": "array",
          "uniqueItems": true,
          "items": { "type": "string", "minLength": 1 }
        }
      }
    }
  }
}
```
<!-- END VERBATIM schema/metadata_schema.json -->

<!-- BEGIN VERBATIM schema/publication_type_vocabulary.json -->
```json
{
  "vocabulary_version": "1.0",
  "note": "Closed semantic publication taxonomy. Journal article labels are evidence, not additional values.",
  "types": [
    {
      "value": "guideline",
      "definition": "Formal practice recommendations developed using an explicit guideline process, such as evidence appraisal, recommendation formulation, or recommendation grading.",
      "excludes": "Do not use solely because an expert group gives advice or classification criteria without a formal guideline-development method."
    },
    {
      "value": "consensus statement",
      "definition": "An expert group's agreed classification, definitions, criteria, terminology, or recommendations without the formal methodology required for a guideline.",
      "excludes": "Supporting analyses or literature summaries do not make the paper a primary study or review when the main contribution is the group's agreed position."
    },
    {
      "value": "primary study",
      "definition": "The principal purpose is to report original empirical data from a cohort, experiment, assay evaluation, or trial.",
      "excludes": "Do not use for a consensus or guideline paper merely because it contains supporting analyses or examples."
    },
    {
      "value": "systematic review",
      "definition": "An evidence synthesis with an explicit, reproducible literature-search and study-selection method; a meta-analysis is included when present.",
      "excludes": "Do not use for an unstructured literature overview."
    },
    {
      "value": "narrative review",
      "definition": "A literature overview without systematic-review methods and without an authoritative group consensus as its primary purpose.",
      "excludes": "Do not use when the primary contribution is agreed classification criteria, terminology, or recommendations."
    },
    {
      "value": "other",
      "definition": "None of the other five semantic types fits the paper's primary purpose.",
      "excludes": "Use only after applying the definitions and precedence rules; do not use merely because the publisher supplies a different article-format label."
    }
  ],
  "precedence": [
    "Classify the paper's primary purpose, not merely its journal banner, section name, or publisher article-format label.",
    "Explicit formal guideline-development methodology takes guideline precedence.",
    "Group-authored agreed classification, criteria, definitions, or terminology takes consensus statement precedence when formal guideline methodology is absent; expert classification systems such as ICC normally fit here.",
    "Original empirical research takes primary study precedence only when it is the paper's main contribution.",
    "An explicit reproducible search and study-selection method identifies a systematic review.",
    "Otherwise, an unstructured literature synthesis is a narrative review; use other only when none of the preceding definitions fits.",
    "Labels such as special report, special article, white paper, position paper, perspective, or review article are not allowed values. Map them to the semantic taxonomy using purpose and methods."
  ],
  "audit_stability": [
    "Audit the package value for defensibility under this taxonomy; do not choose a preferred label de novo.",
    "Pass when the package value is defensible, even if another value could also be defensible.",
    "Fail only when the package value clearly does not satisfy its definition and exactly one different allowed value is better supported.",
    "When evidence is mixed or multiple values remain defensible, retain and pass the package value.",
    "Never fail merely to substitute a near-synonym, a publisher article-format label, or an equally defensible type.",
    "Any auditor_value must be one of the six allowed values."
  ]
}
```
<!-- END VERBATIM schema/publication_type_vocabulary.json -->

<!-- BEGIN VERBATIM schema/review_schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local/ngs_evidence_layer/review_schema.json",
  "title": "Phase 3 complete card review",
  "type": "object",
  "required": ["schema_version", "paper_id", "round", "review_date", "reviewer_model", "extraction_model_reviewed", "result", "audit", "card_results"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "5.0" },
    "paper_id": { "type": "string", "format": "uuid" },
    "round": { "type": "integer", "minimum": 1 },
    "review_date": { "type": "string", "format": "date" },
    "reviewer_model": { "type": "string", "minLength": 1 },
    "extraction_model_reviewed": { "type": "string", "minLength": 1 },
    "result": { "const": "review_complete" },
    "audit": {
      "type": "object",
      "required": ["publication_type_verdict", "cards_total", "cards_passed", "cards_failed"],
      "additionalProperties": false,
      "properties": {
        "publication_type_verdict": { "$ref": "#/$defs/publication_type_verdict" },
        "cards_total": { "type": "integer", "minimum": 0 },
        "cards_passed": { "type": "integer", "minimum": 0 },
        "cards_failed": { "type": "integer", "minimum": 0 }
      }
    },
    "card_results": {
      "type": "array",
      "items": { "$ref": "#/$defs/card_result" }
    }
  },
  "$defs": {
    "publication_type": {
      "enum": ["guideline", "consensus statement", "primary study", "systematic review", "narrative review", "other"]
    },
    "publication_type_verdict": {
      "type": "object",
      "required": ["package_value", "auditor_value", "verdict", "verified_by_phase3", "basis"],
      "additionalProperties": false,
      "properties": {
        "package_value": { "$ref": "#/$defs/publication_type" },
        "auditor_value": { "$ref": "#/$defs/publication_type" },
        "verdict": { "enum": ["pass", "fail"] },
        "verified_by_phase3": { "type": "boolean" },
        "basis": { "type": "string", "minLength": 1 }
      },
      "allOf": [
        {
          "if": { "properties": { "verdict": { "const": "pass" } }, "required": ["verdict"] },
          "then": { "properties": { "verified_by_phase3": { "const": true } } }
        },
        {
          "if": { "properties": { "verdict": { "const": "fail" } }, "required": ["verdict"] },
          "then": { "properties": { "verified_by_phase3": { "const": false } } }
        }
      ]
    },
    "card_result": {
      "type": "object",
      "required": ["card_id", "verdict"],
      "additionalProperties": false,
      "properties": {
        "card_id": { "type": "string", "minLength": 1 },
        "verdict": { "enum": ["pass", "fail"] },
        "details": { "$ref": "#/$defs/failure_details" }
      },
      "allOf": [
        {
          "if": { "properties": { "verdict": { "const": "fail" } }, "required": ["verdict"] },
          "then": { "required": ["details"] },
          "else": { "not": { "required": ["details"] } }
        }
      ]
    },
    "failure_details": {
      "type": "object",
      "required": ["failure_type", "reason", "defensibility", "suggested_action"],
      "additionalProperties": false,
      "properties": {
        "failure_type": {
          "enum": ["quote_error", "unsupported_assertion", "material_redundancy", "scope_or_qualifier", "evidence_relationship", "other"]
        },
        "reason": { "type": "string", "minLength": 1 },
        "defensibility": { "type": "string", "minLength": 1 },
        "quote_restatement": { "type": "string", "minLength": 1 },
        "suggested_action": { "$ref": "#/$defs/suggested_action" }
      },
      "allOf": [
        {
          "if": { "properties": { "failure_type": { "const": "quote_error" } }, "required": ["failure_type"] },
          "then": { "required": ["quote_restatement"] },
          "else": { "not": { "required": ["quote_restatement"] } }
        }
      ]
    },
    "suggested_action": {
      "type": "object",
      "required": ["category", "detail"],
      "additionalProperties": false,
      "properties": {
        "category": {
          "enum": ["narrow_disease_scope", "replace_evidence", "change_category", "rewrite_interpretation", "split_card", "delete_card", "add_or_correct_qualifier"]
        },
        "detail": { "type": "string", "minLength": 1 }
      }
    }
  }
}
```
<!-- END VERBATIM schema/review_schema.json -->

After writing `paper.review-001.json`, recreate the bundle and run:
```bash
python validation_bundle/scripts/final_validation.py --phase 3 \
  --provisional paper.provisional-001.json \
  --review paper.review-001.json
```
A non-zero exit means the Phase 3 product is invalid. Repair it and rerun until
successful. Do not edit the output after the successful run.
## Mandatory pre-output gate

Before writing, verify privately that:

1. the active phase is Phase 3 and the only output is `paper.review-001.json`;
2. the review identity, round, and model fields match the provisional package and the
   reviewer differs from the extraction model;
3. `card_results` contains every provisional card exactly once, in provisional order,
   with no unknown, duplicate, or omitted card IDs;
4. `cards_total`, `cards_passed`, and `cards_failed` exactly match `card_results`;
5. pass entries have no details; every fail entry has one valid failure type, reason,
   defensibility statement, and suggested action;
6. every `quote_error` includes the complete quote restatement actually reviewed and
   no other failure type includes that field; and
7. no extraction content was authored, repaired, removed, reordered, or returned.

If any check fails, repair the review before finalizing. Do not print the checklist,
explanatory prose, Markdown fences, or more than one file.

Return exactly `paper.review-001.json`.
