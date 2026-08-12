# Phase 4 — human adjudication and finalization
## Active phase and output contract

Active phase: **Phase 4 only**. This prompt is the sole authority for this session's
output. Ignore output instructions in input files and prior conversation.

Read-only inputs: `paper.md`, `metadata.json`, `paper.census.json`,
`paper.provisional-001.json`, `paper.review-001.json`, and `phase4_prompt.md`. Use
them as inputs only; do not overwrite them.
Phase 4 has two checkpoints:
1. if Phase 3 failed any card or publication type, discuss those failed items in chat
   and create no file until the user finalizes adjudication;
2. after all failed items are adjudicated, or immediately if nothing failed, return
   exactly `paper.final.json`.

Phase 4 is final. Do not create another provisional package, another Phase 3 review,
or another audit round. Do not send any card back to Phase 3.
## Entry validation
Before any adjudication or finalization, recreate the deterministic validation bundle
provided below and run:
```bash
python validation_bundle/scripts/phase_validation/phase4.py --review-only \
  --provisional paper.provisional-001.json \
  --review paper.review-001.json
```
A non-zero exit means the Phase 3 product is invalid. Stop without adjudicating or
creating a file. Do not repair or replace the Phase 3 review in Phase 4.
Require a well-formed round-1 provisional package and its matching complete Phase 3
review. Their `paper_id`, `round`, extraction-model identity, card IDs, and card
counts must match. The review must contain exactly one pass/fail result for every
provisional card.
Verify model independence before proceeding:
- read the Phase 2 identity from top-level `extraction_model` in
  `paper.provisional-001.json`;
- read the Phase 3 identity from top-level `reviewer_model` in
  `paper.review-001.json`;
- require `paper.review-001.json` field `extraction_model_reviewed` to equal the Phase 2
  `extraction_model`; and
- require `reviewer_model` to differ from `extraction_model`.
If either identity is missing, the reviewed identity does not match, or the Phase 2 and
Phase 3 identities are identical, stop and report that Phase 3 must be rerun with a
different model. A missing, mismatched, incomplete, or malformed artefact stops the
session.
## Mandatory human adjudication
Adjudicate only:

- cards Phase 3 marked `fail`; and
- publication type, if Phase 3 marked it `fail`.

Retain passed cards unchanged. Do not show them or ask the user about them.
### Initial chat output
Print one numerically ordered section for each failed card directly in chat. Use
headings and bullet points; do not create a Markdown file. For each failed card,
show:
1. the exact `card_id`;
2. the current interpretation and all card fields;
3. the complete paired evidence;
4. the complete Phase 3 failure details and suggested action;
5. Phase 4's independent, source-checked suggestion for resolving the failure; and
6. a request for the user's free-text questions, decision, or instructions.
Keep Phase 3's and Phase 4's suggestions separate. Neither is the user's decision.
If publication type failed, add a separate numbered section with its current value
and basis, Phase 3 findings, Phase 4's independent suggestion, and a request for
free-text input. If nothing failed, create `paper.final.json` without asking
questions.
### Discussion and finalization
- Accept free-text discussion and instructions over any number of chat turns.
- Answer the user's questions about any failed item.
- Do not expect the next response to contain final decisions.
- Treat all instructions as provisional until the user sends `FINALIZE` on its own
  line.
- Before `FINALIZE`, do not create or return `paper.final.json`.
- Never infer or supply the user's decision.
- Never treat a Phase 3 or Phase 4 suggestion as the user's decision.
When the user sends `FINALIZE`:
- verify that the user explicitly and unambiguously addressed every failed item;
- if anything remains unresolved, ask only about those items and wait for another
  `FINALIZE`; and
- otherwise apply the user's instructions and create `paper.final.json`.
Human instructions direct amendments but are not source evidence. Verify all retained
or amended content against `paper.md`, the reporting rules, vocabulary, schema, and
shared card standards below. If an instruction is unsupported, explain the conflict
and continue discussion; do not silently invent or substitute evidence. Do not record
the user's decisions, discussion, or adjudication history on cards or elsewhere in
the final package.
## Final package construction

### Card evidence contract

Every card must have exactly one evidence bundle. The bundle must directly support
every material assertion in the interpretation using source-verbatim fragments from
the paper. A locator is navigation metadata, not evidence.

Preserve every material disease, population, treatment, comparator, variant class,
allelic state, threshold, branch, exclusion, analysis, classifier, certainty, and
other qualifier stated by the source. Do not use a bibliographic reference-list entry,
a heading alone, unsupported nearby text, or model knowledge as substantive evidence.
For germline content, distinguish established inherited or constitutional status from
possible constitutional origin and from a recommendation or indication for germline
work-up; a work-up recommendation supports only a conditional interpretation.

Use `contiguous_text` when one coherent contiguous passage is sufficient. Its sole
fragment has role `claim` and may contain multiple contiguous sentences. Start with
the explicit role claim and expand backward or forward as needed to capture antecedents,
scope, population, treatment, comparator, analysis, thresholds, exclusions, direction,
or clinical consequence. Treat contrast words, exceptions, thresholds, unresolved
pronouns, subgroup distinctions, and a following sentence that changes clinical meaning
as boundary warnings. Stop only when the fragment supports every material element of
the interpretation without relying on unquoted context.

Use `composite_text` only when no single coherent passage contains the minimal
sufficient evidence. Use two to six independently verbatim fragments. One or more
`claim` fragments may jointly support one source assertion; add `scope_heading`,
`legend`, or `footnote` fragments only when they provide necessary governing context.
Every fragment must contribute material support recorded in `support_map`. All
fragments must have compatible disease, population, treatment, comparator, analysis,
and classifier scope. Do not combine separate findings, populations, analyses,
classifier branches, or independently useful conclusions merely because they mention
the same gene. Removing any fragment must leave a material assertion unsupported or
underqualified; otherwise use `contiguous_text`, narrow the interpretation, split the
card, or omit it.

A `scope_heading` is valid only when the substantive passage occurs within that
heading's section and no intervening heading changes scope. A heading supplies context;
it does not establish a role claim by itself.

Use `table_relation` when a table value cannot be interpreted defensibly without its
governing labels. Quote each required `column_header`, `row_header`, `cell`, `legend`,
and `footnote` as a separate fragment. Every relation must identify one value fragment,
all applicable row and column headers, and any marked legend or footnote. Preserve
spanning or multi-level headers. Omit the card when merged cells, continuation rows,
conversion damage, or missing markers leave the relation ambiguous. Do not replace
source labels with model-authored key/value facts.

Before finalizing a card, decompose its interpretation into atomic assertions and map
each material assertion to explicit source words in `support_map`, including gene or
alteration class, disease, population, role and direction, treatment or analysis
context, comparator, certainty, thresholds, branches, and exclusions when applicable.
If any assertion lacks support, expand the bundle, narrow the interpretation, split the
card, or omit it. Once sufficient evidence is assembled, do not shorten it merely for
concision.

### Card utility gate

A card must support a distinct, clinically useful sentence that could materially
contribute to a concise NGS report.

- Create or retain at most one card for each independently useful, directly supported
  role from this publication.
- Do not create or retain a material duplicate of another card from the same
  publication.
- Gene presence, mutation frequency, co-occurrence, enrichment, an entity name,
  molecular mechanism, fusion-partner list, or census category does not by itself
  establish a diagnostic, prognostic, treatment, biomarker, or germline role.
- Do not infer prognosis from frequency, treatment from a kinase or fusion list,
  germline status from tumour findings, or biomarker utility from a diagnostic claim.
- Diagnosis and biomarker cards may coexist only when the biomarker card states a
  distinct source-supported testing target, detection strategy, assay limitation,
  monitoring use, or discrimination use.

Start from the complete provisional package and apply the adjudicated outcomes.
Retain, amend, split, or delete cards as directed. Every resulting card must satisfy
the shared card standards. Recompute card IDs when splitting, one-to-one evidence
pairing, `genes_covered`, `diseases_covered`, and canonical `disease_ancestors`.
Set `publication_type` and `publication_type_basis` to the adjudicated final values.
Set `publication_type_verified_by_phase3` to true: Phase 3 supplied the independent
assessment and the human adjudication is final, including when it retains or corrects
a Phase 3 failure.
### Source disease alias policy

Apply this policy when retaining or amending any card disease:

A source-stated disease may ground a canonical card disease only when it is already
canonical or exactly matches a reviewed alias in the canonical source-alias file,
ignoring surrounding whitespace and letter case only.

Emit only the canonical target in `diseases`, but preserve the source's actual disease
or population wording in evidence and interpretation. Do not use fuzzy matching,
stemming, punctuation substitution, semantic inference, or nearest-term mapping. A
source term that is neither canonical nor a configured alias remains outside the
controlled vocabulary.

Canonical source aliases:

```json
{
  "clonal haematopoiesis": "CHIP",
  "clonal haemopoiesis": "CHIP"
}
```

For audit identity fields, copy strings exactly and do not infer substitutes:
- `audit.audit_model` must be copied verbatim from the Phase 3 review's top-level
  `reviewer_model`. It records the Phase 3 model identity, not the Phase 4 model.
- `audit.extraction_model_reviewed` must be copied verbatim from the top-level
  `extraction_model` in `paper.provisional-001.json`.
- The Phase 3 review's top-level `reviewer_model` must differ from the provisional
  package's top-level `extraction_model`. Do not rename either field.
Keep `round` equal to 1. Populate the existing final `audit` shape:
```json
{
  "audit_date": "YYYY-MM-DD",
  "audit_model": "<Phase 3 reviewer_model>",
  "extraction_model_reviewed": "<provisional extraction_model>",
  "approved_round": 1,
  "publication_type_verdict": {
    "verdict": "pass",
    "verified_by_phase3": true,
    "reason": "Phase 3 review completed and the human adjudication is final."
  },
  "results": [
    {
      "card_id": "<exact resulting card ID>",
      "verdict": "pass"
    }
  ]
}
```
Repeat `results` exactly once for every resulting card. All resulting cards are
marked pass because the human review and action taken are final. Do not add human
decision fields to the audit; adjudication is represented by the final card content.
## Reporting rules
# Agreed reporting rules for interpretative myeloid NGS summaries

## Scope and report structure

These rules apply to a concise interpretative summary for clinical haematologists. The purpose is to explain how the detected NGS findings alter or refine the diagnosis, prognosis, management, measurable residual disease assessment or consideration of germline predisposition in the supplied clinical and morphological context.

Use the following order, omitting sections that are not relevant:

1. Integrated diagnosis and classification
2. Prognostic significance
3. Clinically actionable implications
4. MRD implications
5. Possible germline predisposition

Do not repeat the clinical history, morphology or standard treatment unless needed to explain the effect of a molecular finding.

# R1 — Diagnosis and classification

1. **Interpret variants in the supplied clinicopathological context.** Do not diagnose a myeloid neoplasm from mutation number, mutation identity or VAF alone. Treat the stated morphological diagnosis as the starting point and explain only how the molecular result confirms, changes, excludes or qualifies it.

2. **Use WHO-5 as the primary diagnostic classifier.** State the WHO-5 diagnosis.

3. **Assess ICC separately.** State the ICC diagnosis. Then assess whether it is materially the same as the WHO-5 diagnosis.

4. **State the integrated diagnosis when a detected alteration is entity-defining.** Apply the required blast range, morphology, cytogenetic findings, variant class, VAF threshold and exclusion criteria. Do not substitute a biologically related mutation for the mutation required by the entity definition.

5. **Respect diagnostic precedence.** When more than one molecular or cytogenetic feature is present, assign the entity with the appropriate classification precedence rather than listing competing diagnoses. Keep entity assignment separate from prognostic effects of co-mutations.

6. **Distinguish clonal haematopoiesis from a myeloid neoplasm.** When morphology is non-diagnostic, classify a qualifying clone as:
   - **CHIP** when cytopenia is absent or an adequate external cause explains the cytopenia; or
   - **CCUS** when cytopenia is persistent, otherwise unexplained and no myeloid neoplasm is established.

   A small clone must not be used to overcall MDS, MPN or another neoplasm.

7. **Actively assess relevant competing diagnoses.** A genotype may suggest a differential but does not override mandatory clinical or morphological criteria. Check the decisive variables, such as absolute and relative monocytosis, eosinophilia, dysgranulopoiesis, blast percentage, fibrosis, reactive causes and defining rearrangements.

8. **Report negative molecular findings only when they are diagnostically informative.** Mention absence only when the alteration is ordinarily expected in the relevant differential, directly changes the diagnostic label, establishes triple-negative status, or helps determine allelic state. Do not list unrelated absent genes.

9. **Interpret VAF conservatively.** VAF may support a small, substantial or dominant clonal population, but bulk sequencing does not establish:
   - founding versus secondary status;
   - chronological order;
   - whether variants occur in the same cells;
   - cis/trans phase; or
   - germline origin.

10. **Apply TP53 allelic-state rules explicitly.** Distinguish a single monoallelic mutation from multi-hit or biallelic disease. A single mutation without a qualifying second hit must not be called biallelic. Two qualifying TP53 mutations, or a mutation with a qualifying deletion/copy-neutral loss of heterozygosity, support multi-hit status under the applicable classifier.

11. **Do not use a low VAF to dismiss an otherwise established diagnosis when low allele burden is biologically expected.** Conversely, do not use a high VAF as a substitute for missing diagnostic criteria.

12. **Account for assay scope.** A negative SNV/indel panel does not exclude rearrangements, copy-number changes or variants outside validated coverage. Integrate cytogenetics, FISH, fusion testing and other assays where relevant.

13. **Use precise variant-level interpretation.** Therapeutic or diagnostic implications may depend on the exact exon, codon, alteration type or fusion partner rather than merely the gene name.

# R2 — Prognostic interpretation

1. **Use the appropriate disease-specific prognostic framework.** Prefer a validated disease-specific prognostic system where one exists. For findings not addressed by that system, use high-quality disease-specific prognostic evidence.

2. **Assign a prognostic contribution to each detected pathogenic variant.** For each pathogenic or likely pathogenic variant, state whether it has a favourable, adverse or no established prognostic contribution in the relevant disease. Use the applicable prognostic system first; if it does not address the variant, use high-quality disease-specific evidence.

3. **Report molecular contributions rather than composite clinical scores.** When a prognostic system incorporates non-molecular variables, report how the detected molecular findings contribute to prognosis without calculating the complete score or assigning its overall risk tier.

4. **Use ELN 2022 as the primary AML risk classification.** ELN 2024 Less-Intensive may additionally be reported when it gives a materially different risk category. Reporting ELN 2024 Less-Intensive is mandatory when the patient is already receiving less-intensive treatment or is explicitly unsuitable for intensive therapy. Reporting ELN 2022 is optional if and only if ELN 2024 is mandatory.

5. **Do not transfer prognostic effects between diseases or models.** Apply a prognostic system only to the disease for which it is validated, and do not assign a variant a prognostic effect based solely on evidence from another disease.

6. **Apply negative panel findings when required by the prognostic model.** When a gene is included in the NGS panel and no reportable variant is identified, treat it as wild-type for the purpose of the selected prognostic system. Do not extend this inference beyond the validated scope of the assay.

7. **Apply TP53 prognostic effects according to allelic state.** Distinguish monoallelic TP53 alterations from TP53 multi-hit disease and apply the prognostic effect appropriate to the established allelic state.

8. **Include only clinically relevant prognostic evidence.** Omit prevalence, epidemiological background and prognostic associations that do not contribute to the patient-level prognostic interpretation.

# R3 — Clinical actionability

1. **Report only management implications that arise from the detected alteration.** Do not restate standard-of-care treatment that would apply regardless of the NGS result.

2. **Link therapy to the exact actionable alteration and disease setting.** Specify the relevant mutation, fusion or pathway, the treatment phase where necessary, and whether the implication is established, optional or investigational.

3. **Report treatment-specific molecular modifiers.** For a therapy relevant to the patient, report detected alterations that are supported to modify response, resistance, relapse risk or survival. Do not extrapolate treatment-specific effects to overall prognosis.

4. **Do not overstate sensitivity or resistance.** Use qualified wording when evidence is limited, variant-specific or based on small series. “May be sensitive” is appropriate when a definitive response cannot be predicted.

5. **State approval and access context when relevant.** Distinguish approved frontline, relapsed/refractory, trial-only and jurisdiction-dependent uses without turning the report into a treatment protocol.

6. **Do not invent actionability.** When the detected variants do not select an approved mutation-specific therapy, say so only if this is clinically useful; otherwise omit therapy commentary.

7. **Keep diagnostic, prognostic and predictive roles separate.** A mutation may define the disease or worsen prognosis without selecting a targeted drug. Conversely, a therapeutically actionable mutation may not define the diagnostic entity.

8. **Recommend transplant assessment only when the molecular finding materially alters risk, donor selection or therapeutic strategy.** Do not recommend transplantation solely because a mutation is present.

9. **For kinase alterations, interpret the precise molecular class.** Different variants in the same gene can have different pathway activation and drug sensitivity; do not apply one mutation’s treatment logic to another.

10. **For cytogenetically defined actionable disease, recognise that the treatment implication may arise outside the NGS panel.** Integrate defining fusions, rearrangements or deletions detected by cytogenetics or FISH.

11. **When possible germline predisposition is identified, separate immediate disease treatment from genetic counselling, constitutional confirmation and donor-selection implications.**

# R4 — MRD interpretation

1. **Do not assume that a diagnostic NGS variant is an MRD marker.** Use only disease-, gene-, assay- and timepoint-validated MRD approaches.

2. **Distinguish routine-panel sensitivity from dedicated MRD sensitivity.** “Not detected” on a routine assay means below that assay’s reportable threshold, not biological absence or molecular remission.

3. **When a validated leukaemia-specific marker is present, identify it explicitly and recommend an appropriate high-sensitivity assay.** For NPM1-mutated AML, the specific NPM1 mutation is the preferred molecular MRD target.

4. **Do not assign MRD status from persistent clonal-haematopoiesis-associated mutations.** Variants such as DNMT3A, TET2 and ASXL1 may persist independently of active leukaemia and must not determine remission status by themselves.

5. **Do not use IDH1 or IDH2 as stand-alone MRD markers.** Persistence or clearance should not independently establish molecular remission, relapse or treatment failure.

6. **Use FLT3-ITD only within a validated high-sensitivity strategy.** When a validated leukaemia-specific marker such as NPM1 is available, FLT3-ITD should be complementary rather than the sole follow-up marker.

7. **Do not promote other non-validated mutations to stand-alone MRD markers.** Interpret genes such as spliceosome, cohesin, transcription-factor or signalling mutations only within a validated multimodal strategy.

8. **If no validated molecular marker is available, say so and keep multiparameter flow cytometry, morphology and clinical assessment central.** Do not manufacture a molecular endpoint.

9. **Interpret residual variants using assay threshold, specimen, treatment regimen, treatment timepoint and serial kinetics.** Do not assign relapse from a single low-level result without corroboration.

10. **Do not escalate treatment solely because an unvalidated residual mutation remains detectable.** Correlate with the validated marker, flow cytometry, morphology and clinical course.

11. **Do not transfer AML-specific MRD guidance to other myeloid neoplasms unless a disease-specific validated framework exists.** Silence is appropriate where no validated molecular MRD recommendation applies.

# R5 — Possible germline predisposition

1. **Flag possible germline origin when the combination of gene, variant type, VAF and personal phenotype is compatible with a recognised hereditary predisposition.** Do not rely on VAF alone.

2. **Never diagnose germline status from tumour-only sequencing.** Use wording such as “possible germline,” “suspected germline” or “presumed germline pending constitutional confirmation.”

3. **Recognise characteristic molecular architectures.** Examples include a near-heterozygous loss-of-function predisposition variant with a lower-VAF recurrent somatic second event, or a pathogenic variant associated with a longstanding constitutional phenotype.

4. **Recommend confirmation using a validated non-haematopoietic specimen and genetic counselling.** Cultured skin fibroblasts are preferred where blood, marrow, saliva or buccal cells may be contaminated by the haematopoietic clone.

5. **Do not infer which allele is constitutional, whether variants are in cis or trans, or whether two variants occur in the same clone from bulk VAF alone.** Phasing or lineage-resolved testing may be required.

6. **Do not dismiss germline predisposition because no near-50% variant was detected on the myeloid panel.** A recurrent low-VAF somatic “second hit,” relevant phenotype or incomplete assay coverage may still justify dedicated constitutional testing, including copy-number analysis where appropriate.

7. **State the practical implications of confirmation.** These may include related-donor selection, family counselling and cascade testing. Do not recommend testing relatives as though germline status were already confirmed.

8. **Keep germline interpretation separate from somatic prognostic scoring.** Where somatic versus germline origin changes the applicability of a prognostic model, state that the molecular risk contribution is provisional pending constitutional testing.

9. **Avoid indiscriminate germline flagging.** A common somatic hotspot at a plausible somatic VAF, without a compatible phenotype or predisposition-gene context, should not trigger routine germline recommendations.

# Style requirements

- Lead with the clinically important conclusion.
- Be concise and specific.
- Explain only the molecular facts that change diagnosis, prognosis, management, MRD interpretation or germline assessment.
- Distinguish established findings from possibilities and uncertainties.
- Do not speculate beyond the supplied data.
- Do not fabricate literature, evidence, thresholds, assay performance or treatment approvals.
## Disease vocabulary

```json
{
  "vocabulary_version": "1.5",
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
## Output schema

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
## Deterministic exit validation

The bundle below contains the canonical self-contained validator for this phase.
Recreate every displayed file verbatim under `validation_bundle/` at its displayed
relative path. Do not search for or clone the repository, modify the bundled file,
summarize or reinterpret it, rewrite imports, or substitute another validator.

<!-- BEGIN VERBATIM scripts/phase_validation/phase4.py -->
```python
#!/usr/bin/env python3
"""Self-contained deterministic validation for Phase 4 entry and final output."""
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

PACKAGE_SCHEMA = json.loads(r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://local/ngs_evidence_layer/ingestion_package_schema.json","title":"Phase 2 provisional or Phase 4 final evidence package","type":"object","required":["schema_version","paper_id","round","extraction_date","extraction_model","publication_type","publication_type_basis","publication_type_verified_by_phase3","genes_covered","diseases_covered","census_entries","cards","evidence","audit"],"additionalProperties":false,"properties":{"schema_version":{"const":"5.0"},"paper_id":{"type":"string","format":"uuid"},"round":{"type":"integer","minimum":1},"extraction_date":{"type":"string","format":"date"},"extraction_model":{"type":"string","minLength":1},"publication_type":{"enum":["guideline","consensus statement","primary study","systematic review","narrative review","other"]},"publication_type_basis":{"type":"string","minLength":1},"publication_type_verified_by_phase3":{"type":"boolean"},"genes_covered":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/gene"}},"diseases_covered":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/disease"}},"census_entries":{"type":"integer","minimum":0},"cards":{"type":"array","items":{"$ref":"#/$defs/card"}},"evidence":{"type":"array","items":{"$ref":"#/$defs/evidence"}},"audit":{"anyOf":[{"type":"null"},{"$ref":"#/$defs/audit"}]}},"$defs":{"gene":{"type":"string","pattern":"^[A-Z0-9][A-Z0-9\\-]*$"},"disease":{"enum":["CHIP","CCUS","MDS","MDS/AML","AML","APL","MDS/MPN","MDS/MPN-U","CMML","aCML","MDS/MPN-SF3B1-T","JMML","MPN","MPN-U","PV","ET","PMF","post-PV/post-ET MF","MPN blast phase","CML","CNL","CEL","mastocytosis","myeloid/lymphoid neoplasm with eosinophilia and TK fusion","BPDCN","germline predisposition syndrome","myeloid neoplasm, unspecified","lymphoid neoplasm","acute leukaemia of ambiguous lineage","histiocytic/dendritic neoplasm","haematological malignancy, other"]},"citation":{"type":"object","required":["display"],"additionalProperties":false,"properties":{"authors":{"type":"array","items":{"type":"string"}},"title":{"type":"string"},"journal":{"type":"string"},"year":{"type":"integer","minimum":1950,"maximum":2100},"volume":{"type":"string"},"issue":{"type":"string"},"pages":{"type":"string"},"display":{"type":"string","minLength":1},"citation_incomplete":{"type":"array","uniqueItems":true,"items":{"type":"string"}}}},"card":{"type":"object","required":["card_id","locator","interpretation","genes","diseases","category","evidence_tier","secondary_citation"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"locator":{"type":"string","minLength":1},"interpretation":{"type":"string","minLength":1},"genes":{"type":"array","minItems":1,"uniqueItems":true,"items":{"$ref":"#/$defs/gene"}},"diseases":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/disease"}},"disease_ancestors":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/disease"}},"category":{"enum":["diagnosis","prognosis","treatment","biomarker","germline"]},"evidence_tier":{"enum":["guideline criterion","multivariable-adjusted","univariable or descriptive","restated secondary"]},"secondary_citation":{"anyOf":[{"type":"null"},{"$ref":"#/$defs/citation"}]}},"allOf":[{"if":{"properties":{"category":{"enum":["diagnosis","prognosis","treatment","biomarker"]}},"required":["category"]},"then":{"properties":{"diseases":{"minItems":1}}}}]},"fragment":{"type":"object","required":["fragment_id","role","quote","locator"],"additionalProperties":false,"properties":{"fragment_id":{"type":"string","pattern":"^F[0-9]{2}$"},"role":{"enum":["claim","scope_heading","column_header","row_header","cell","legend","footnote"]},"quote":{"type":"string","minLength":1},"locator":{"type":"string","minLength":1}}},"support_map":{"type":"object","minProperties":1,"additionalProperties":false,"properties":{"gene":{"$ref":"#/$defs/fragment_ids"},"disease":{"$ref":"#/$defs/fragment_ids"},"role":{"$ref":"#/$defs/fragment_ids"},"population":{"$ref":"#/$defs/fragment_ids"},"effect":{"$ref":"#/$defs/fragment_ids"},"qualifier":{"$ref":"#/$defs/fragment_ids"}}},"fragment_ids":{"type":"array","minItems":1,"uniqueItems":true,"items":{"type":"string","pattern":"^F[0-9]{2}$"}},"table_relation":{"type":"object","required":["value_fragment_id","header_fragment_ids","qualifier_fragment_ids"],"additionalProperties":false,"properties":{"value_fragment_id":{"type":"string","pattern":"^F[0-9]{2}$"},"header_fragment_ids":{"$ref":"#/$defs/fragment_ids"},"qualifier_fragment_ids":{"type":"array","uniqueItems":true,"items":{"type":"string","pattern":"^F[0-9]{2}$"}}}},"evidence":{"oneOf":[{"type":"object","required":["card_id","evidence_type","fragments","support_map"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"evidence_type":{"const":"contiguous_text"},"fragments":{"type":"array","minItems":1,"maxItems":1,"items":{"$ref":"#/$defs/fragment"}},"support_map":{"$ref":"#/$defs/support_map"}}},{"type":"object","required":["card_id","evidence_type","fragments","support_map"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"evidence_type":{"const":"composite_text"},"fragments":{"type":"array","minItems":2,"maxItems":6,"items":{"$ref":"#/$defs/fragment"}},"support_map":{"$ref":"#/$defs/support_map"}}},{"type":"object","required":["card_id","evidence_type","fragments","support_map","table_relations"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"evidence_type":{"const":"table_relation"},"fragments":{"type":"array","minItems":2,"maxItems":12,"items":{"$ref":"#/$defs/fragment"}},"support_map":{"$ref":"#/$defs/support_map"},"table_relations":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/table_relation"}}}}]},"audit":{"type":"object","required":["audit_date","audit_model","extraction_model_reviewed","approved_round","publication_type_verdict","results"],"additionalProperties":false,"properties":{"audit_date":{"type":"string","format":"date"},"audit_model":{"type":"string","minLength":1},"extraction_model_reviewed":{"type":"string","minLength":1},"approved_round":{"type":"integer","minimum":1},"publication_type_verdict":{"type":"object","required":["verdict","verified_by_phase3"],"additionalProperties":false,"properties":{"verdict":{"enum":["pass","fail"]},"verified_by_phase3":{"const":true},"reason":{"type":"string","minLength":1}},"allOf":[{"if":{"properties":{"verdict":{"const":"fail"}},"required":["verdict"]},"then":{"required":["reason"]}}]},"results":{"type":"array","items":{"type":"object","required":["card_id","verdict"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"verdict":{"enum":["pass","fail"]},"reason":{"type":"string","minLength":1}},"allOf":[{"if":{"properties":{"verdict":{"const":"fail"}},"required":["verdict"]},"then":{"required":["reason"]}}]}}}}}}''')
REVIEW_SCHEMA = json.loads(r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://local/ngs_evidence_layer/review_schema.json","title":"Phase 3 complete card review","type":"object","required":["schema_version","paper_id","round","review_date","reviewer_model","extraction_model_reviewed","result","audit","card_results"],"additionalProperties":false,"properties":{"schema_version":{"const":"5.0"},"paper_id":{"type":"string","format":"uuid"},"round":{"type":"integer","minimum":1},"review_date":{"type":"string","format":"date"},"reviewer_model":{"type":"string","minLength":1},"extraction_model_reviewed":{"type":"string","minLength":1},"result":{"const":"review_complete"},"audit":{"type":"object","required":["publication_type_verdict","cards_total","cards_passed","cards_failed"],"additionalProperties":false,"properties":{"publication_type_verdict":{"$ref":"#/$defs/publication_type_verdict"},"cards_total":{"type":"integer","minimum":0},"cards_passed":{"type":"integer","minimum":0},"cards_failed":{"type":"integer","minimum":0}}},"card_results":{"type":"array","items":{"$ref":"#/$defs/card_result"}}},"$defs":{"publication_type":{"enum":["guideline","consensus statement","primary study","systematic review","narrative review","other"]},"publication_type_verdict":{"type":"object","required":["package_value","auditor_value","verdict","verified_by_phase3","basis"],"additionalProperties":false,"properties":{"package_value":{"$ref":"#/$defs/publication_type"},"auditor_value":{"$ref":"#/$defs/publication_type"},"verdict":{"enum":["pass","fail"]},"verified_by_phase3":{"type":"boolean"},"basis":{"type":"string","minLength":1}},"allOf":[{"if":{"properties":{"verdict":{"const":"pass"}},"required":["verdict"]},"then":{"properties":{"verified_by_phase3":{"const":true}}}},{"if":{"properties":{"verdict":{"const":"fail"}},"required":["verdict"]},"then":{"properties":{"verified_by_phase3":{"const":false}}}}]},"card_result":{"type":"object","required":["card_id","verdict"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"verdict":{"enum":["pass","fail"]},"details":{"$ref":"#/$defs/failure_details"}},"allOf":[{"if":{"properties":{"verdict":{"const":"fail"}},"required":["verdict"]},"then":{"required":["details"]},"else":{"not":{"required":["details"]}}}]},"failure_details":{"type":"object","required":["failure_type","reason","defensibility","suggested_action"],"additionalProperties":false,"properties":{"failure_type":{"enum":["quote_error","unsupported_assertion","material_redundancy","scope_or_qualifier","evidence_relationship","other"]},"reason":{"type":"string","minLength":1},"defensibility":{"type":"string","minLength":1},"quote_restatement":{"type":"string","minLength":1},"suggested_action":{"$ref":"#/$defs/suggested_action"}},"allOf":[{"if":{"properties":{"failure_type":{"const":"quote_error"}},"required":["failure_type"]},"then":{"required":["quote_restatement"]},"else":{"not":{"required":["quote_restatement"]}}}]},"suggested_action":{"type":"object","required":["category","detail"],"additionalProperties":false,"properties":{"category":{"enum":["narrow_disease_scope","replace_evidence","change_category","rewrite_interpretation","split_card","delete_card","add_or_correct_qualifier"]},"detail":{"type":"string","minLength":1}}}}}''')
UMBRELLA = json.loads(r'''{"MDS/AML":["MDS","AML"],"APL":["AML"],"MDS/MPN":["MDS","MPN"],"MDS/MPN-U":["MDS/MPN"],"CMML":["MDS/MPN"],"aCML":["MDS/MPN"],"MDS/MPN-SF3B1-T":["MDS/MPN"],"MPN-U":["MPN"],"PV":["MPN"],"ET":["MPN"],"PMF":["MPN"],"post-PV/post-ET MF":["MPN"],"MPN blast phase":["MPN"],"CML":["MPN"],"CNL":["MPN"],"CEL":["MPN"],"JMML":["MPN"],"BPDCN":["histiocytic/dendritic neoplasm"]}''')
DISEASES = list(PACKAGE_SCHEMA["$defs"]["disease"]["enum"])
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


def disease_ancestors(diseases):
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


def schema_errors(document, schema, label):
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


def validate_review(review, provisional):
    """Validate a complete Phase 3 review against its Phase 2 package."""
    errors = schema_errors(review, REVIEW_SCHEMA, "review")
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
    errors = schema_errors(package, PACKAGE_SCHEMA, "package")
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
            expected_ancestors = disease_ancestors(card["diseases"])
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


def validate_review_files(*, provisional_path, review_path):
    provisional = read_json(provisional_path, "provisional package")
    review = read_json(review_path, "Phase 3 review")
    errors = [f"review: {error}" for error in validate_review(review, provisional)]
    return errors, [], {
        "phase": 3,
        "cards": len(provisional.get("cards", [])),
        "review_results": len(review.get("card_results", [])),
    }


def validate_phase_files(
    *, metadata_path, census_path, source_path, provisional_path, review_path, final_path
):
    metadata = read_json(metadata_path, "metadata")
    census = read_json(census_path, "census")
    provisional = read_json(provisional_path, "approved provisional package")
    review = read_json(review_path, "Phase 3 review")
    final = read_json(final_path, "final package")
    errors = [
        f"final lineage: {error}"
        for error in validate_final_against_provisional(final, provisional)
    ]
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
    final_errors, warnings, report = validate_package(
        final, metadata, census, source_text=source_text, require_final=True
    )
    errors.extend(f"final: {error}" for error in final_errors)
    phase_report = {"phase": 4}
    phase_report.update(report or {})
    return errors, warnings, phase_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--provisional", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--final", type=Path)
    args = parser.parse_args(argv)
    required = () if args.review_only else ("metadata", "census", "source", "final")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("Phase 4 exit validation requires " + ", ".join(f"--{name}" for name in missing))
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.review_only:
            errors, warnings, report = validate_review_files(
                provisional_path=args.provisional, review_path=args.review
            )
            label = "PHASE 4 ENTRY"
        else:
            errors, warnings, report = validate_phase_files(
                metadata_path=args.metadata,
                census_path=args.census,
                source_path=args.source,
                provisional_path=args.provisional,
                review_path=args.review,
                final_path=args.final,
            )
            label = "PHASE 4"
    except (OSError, ValueError) as exc:
        sys.exit(f"{label if 'label' in locals() else 'PHASE 4'} VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit(f"{label} VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
```
<!-- END VERBATIM scripts/phase_validation/phase4.py -->
After writing `paper.final.json`, recreate the bundle and run:
```bash
python validation_bundle/scripts/phase_validation/phase4.py \
  --metadata metadata.json \
  --census paper.census.json \
  --source paper.md \
  --provisional paper.provisional-001.json \
  --review paper.review-001.json \
  --final paper.final.json
```
A non-zero exit means the Phase 4 product is invalid. Repair `paper.final.json` and
rerun the validator until successful. Do not edit `paper.final.json` after the
successful run.
## Mandatory pre-output gate
Before writing, verify privately that:
1. the active phase is Phase 4, no passed card required adjudication, and every failed
   item was explicitly adjudicated and finalized by the user;
2. the only file output is `paper.final.json` and no input was overwritten;
3. every final assertion and evidence fragment is supported verbatim by `paper.md`;
4. every resulting card has exactly one paired evidence bundle and all paired IDs
   match;
5. `genes_covered`, `diseases_covered`, and every `disease_ancestors` array are exact;
6. package `round` and `audit.approved_round` are both 1;
7. the audit contains exactly one passing result for every resulting card and no
   result for a deleted or superseded card;
8. `audit.audit_model` exactly equals the Phase 3 review's top-level
   `reviewer_model`, and `audit.extraction_model_reviewed` exactly equals the
   provisional `extraction_model`;
9. the Phase 3 review's `reviewer_model` differs from the provisional package's
   `extraction_model`; and
10. the final package conforms to the output schema.
The final action before returning `paper.final.json` must be a successful run of the
deterministic validator against the exact file being returned. If any check fails,
repair the package and rerun it. Do not print the checklist, explanatory prose,
Markdown fences around JSON, or more than one file.

Return exactly `paper.final.json`.
