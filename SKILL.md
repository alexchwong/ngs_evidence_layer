---
name: ngs_evidence_layer
description: Corpus-grounded evidence layer for myeloid NGS interpretation. It collates publication statements into gene-indexed, quote-backed cards and renders deterministic evidence blocks; it does not synthesise or conclude.
---

# NGS evidence layer

## Scope and downstream contract

This skill turns publications into evidence cards and a case into a block of
evidence meanings with card IDs and deterministic citations. It is an evidence
layer, not a report writer: it does not resolve conflicting classifiers, rank
findings, recommend treatment, or draft an interpretative summary.

The governing rule is: **no model haematology knowledge enters output.** Every
assertion comes from an accepted publication and traces through a card ID to one
private source-verbatim quote. A gene the corpus cannot address is named as
unassessed rather than answered from memory.

Ingestion prompts are data under `prompts/`; this file is orientation and retrieval
scope, not a phase prompt. `rules/agreed_reporting_rules.md` is the canonical
extraction checklist. See `INGEST.md` for operations.

## Core evidence invariants

- one publication per fresh model session;
- one quote per card and one card per quote, with a 400-word quote cap;
- cards contain at least one gene and exactly one category: `diagnosis`,
  `prognosis`, `treatment`, `biomarker`, or `germline`;
- interpretations carry every source-stated population, treatment, allelic,
  variant, analysis, classifier, threshold, branch, and exclusion qualifier;
- negative and exclusion facts are first-class evidence;
- `escalates_to` appears only where a diagnosis card's source states a change of
  major diagnostic category;
- an independent model audits quote support and independent utility without
  rewriting extraction content;
- quote text never enters the distributable corpus or retrieval output.

## Disease vocabulary

The canonical closed vocabulary and umbrella relationships live in
`schema/disease_vocabulary.json`. No free-text subtype or modifier is a tag. Where a
source is specific, the card includes both the specific disease and required
umbrella (for example APL + AML, or ET + MPN-U). A genuinely disease-agnostic claim
uses an empty disease array.

Classifier editions, therapy-related context, paediatric context, thresholds, and
variant-level distinctions remain explicit in interpretation prose because the
categorical index deliberately does not encode them.

## Supersession and coexistence

Supersession applies only between versions of the same publication. Different
publications coexist even when they disagree: WHO and ICC, or successive guideline
families, remain separately citable cards. Cross-publication deduplication is out of
scope; only byte-identical rendered interpretations collapse while retaining all
citations.

## Retrieval

Retrieval surrounds two bounded model steps with deterministic code. Case intake
emits the provisional major category, NGS genes, and structured patient facts with
stable IDs, for example:

```json
{
  "provisional_disease": "myeloid neoplasm, unspecified",
  "genes": ["SF3B1"],
  "case_facts": [
    {"fact_id": "F-SF3B1", "type": "variant", "gene": "SF3B1", "vaf_percent": 30},
    {"fact_id": "F-RS", "type": "morphology", "ring_sideroblast_percent": 7}
  ]
}
```

Genes come strictly from the NGS result block. The provisional disease comes from
the closed vocabulary and is not upgraded from model knowledge. Case facts must
preserve the supplied values; absent information is not inferred.

### Diagnosis pass

`scripts/retrieve.py diagnosis` retrieves every diagnosis card for submitted genes
without a disease filter and carries the case facts into Step 3. The adjudication
model uses `prompts/diagnostic_adjudication_prompt.md` to compare only those facts
with the retrieved cards. It may compose complex source-stated criteria but may not
supply a missing rule, threshold, exclusion, or patient fact from model knowledge.
Legacy `escalates_to` values are provenance, not a runtime logic gate.

The adjudication returns a source-supported `diagnostic_label` and a closed-vocabulary
`refined_disease`. The latter is the major category that controls downstream card
calling. For example, `MDS-SF3B1` is represented by `diagnostic_label: "MDS-SF3B1"`
and `refined_disease: "MDS"`. Every required criterion must cite retrieved card IDs
and supplied fact IDs; missing facts make the result `indeterminate` and preserve the
provisional category.

### Full pass

`scripts/retrieve.py full` applies:

- diagnosis: cards already returned by the diagnosis pass;
- prognosis, treatment, biomarker: gene match and either refined-disease match or
  an empty disease array;
- germline: gene match only.

The script validates the adjudication and passes its exact
`downstream_filter_disease`/`refined_disease` value to this filter. It rejects changed
major categories with unknown or unmet required criteria, unretrieved card IDs, or
unsupplied case-fact IDs.

It also returns disease-filtered cards under `suppressed`, submitted genes with no
card under `not_assessed`, and corpus/card provenance.

### Rendering

`scripts/render.py` emits interpretation strings only, ordered by category, gene,
evidence tier, publication year, then card ID. Citations are numbered by script.
Weak evidence drops first if the token budget binds; guideline criteria and
multivariable-adjusted findings are never silently dropped.

## Exclusions

- no live evidence sources;
- no approval-status or jurisdiction modelling;
- no ACMG/ClinGen/VICC meta-evidence layer;
- no clinical decision or report synthesis;
- no PDF extraction;
- no claim that example expected outputs are a clinical gold standard.