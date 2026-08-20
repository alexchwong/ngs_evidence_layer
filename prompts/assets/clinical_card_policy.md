# Clinical card policy

## Target of card authoring

The target of ingestion is the **patient-level clinical meaning of a source-supported finding**, not a summary of how the publication demonstrated that finding.

For each card, move through this reasoning target:

`source result -> patient-level clinical implication -> minimum applicability qualifiers -> final interpretation`

A final interpretation should tell the clinician what the molecular finding means for diagnosis/classification, prognosis, treatment/management, MRD, or germline evaluation. If the wording mainly describes what the study measured, how the analysis was performed, how a score was built, or what numerical result was observed, it has not yet been converted into a clinically useful interpretation.

## One proposition per card

One card represents one independently useful, directly supported clinical proposition. The interpretation may contain multiple grammatical clauses only when every additional clause is necessary to define, narrow, condition, qualify, or state an exception to that **same clinical proposition**.

Do not append another independently retainable proposition merely because it comes from the same sentence, paragraph, table, guideline, evidence bundle, disease, gene set, or clinical framework. Apply the deletion / independent-retention test in `CLINICAL_ASSERTION_POLICY` whenever contextual text might be mistaken for a qualifier.

If an interpretation contains two independently retainable propositions, split them when both independently warrant cards. If the secondary proposition has no independent clinical utility, remove it from the card and disposition it separately rather than allowing it to hitchhike as context.

## Clinical abstraction and wording

State the strongest clinically useful conclusion directly entailed by the evidence, using only the minimum source-supported context needed for the conclusion to be understood correctly when presented alone.

Include the minimum context required to understand the disease/population, molecular finding or biological group, treatment/comparator when applicable, outcome or clinical role, and every subgroup, threshold, treatment setting, exception, uncertainty, or other qualifier that materially limits the same proposition. Do not add contextual detail merely to make the interpretation more complete.

Every gene listed in the card's `genes` field must be explicitly named in the interpretation. Every disease listed in `diseases` must be explicitly identified in the interpretation by its canonical name or an accepted source-disease alias. Generic substitutes such as `the driver gene`, `this disease`, or `these mutations` do not satisfy this requirement. The card category does not need to be named.

The interpretation is not merely a quotation, paraphrase, extracted result, or restatement of a statistic. Source-supported synthesis is permitted only when the conclusion is directly entailed without an unstated clinical or methodological premise.

## Study-result packaging versus clinically operative information

Preserve the narrowest clinically meaningful endpoint and direction supported by the source, while normally removing study-result packaging such as:

- hazard ratios, odds ratios, confidence intervals, P values, and regression terminology;
- median survival values, fixed-time survival percentages, response percentages, relapse percentages, and cohort sample sizes;
- study phase/design labels, prospective/retrospective labels, discovery/validation-cohort terminology, and analysis-method names;
- model coefficients, score weights, point assignments, calibration/discrimination statistics, and other prognostic-model internals.

For example, a source result expressed as a hazard ratio for overall survival should ordinarily become the source-supported statement that the molecular finding is associated with better or worse overall survival in the stated disease/population, not a card whose substance is the hazard ratio.

A number should remain in the interpretation when the clinician must know that value or threshold to apply the source-supported rule to an individual patient. Examples include diagnostic/classification thresholds, treatment-eligibility thresholds, or source-defined molecular thresholds that materially change interpretation. Do not remove clinically operative numbers merely because they are quantitative.

Do not broaden a narrow endpoint while abstracting it. `Inferior overall survival` should not become generic `adverse prognosis` unless the source directly supports that broader conclusion.

## Paper-local labels and methodological context

A trial name, cohort name, treatment-arm label, model number, table identifier, analysis label, subgroup nickname, or similar paper-local term must not carry information required to understand the interpretation.

Replace such labels with the shortest clinically meaningful description of what defines the population or exposure, for example `patients who received drug A`, `patients with relapsed AML`, or `patients with TP53-mutated AML`. If the local label adds no clinical value, omit it. Recognised clinical classifications/frameworks may be retained when the framework itself is necessary to understand the clinical assertion.

If study design materially limits applicability, state the **clinical limitation** rather than merely naming the methodology. Methodological detail belongs in the evidence unless it changes the patient-level meaning of the proposition.

## Findings that usually do not warrant report-facing cards

Do not create a card merely because the paper reports:

- statistical non-significance or a null association;
- mutation prevalence or frequency;
- that a mutation was common or the most common finding;
- co-occurrence between molecular findings;
- pathway/mechanistic effects;
- prognostic-score internals or model-construction details;
- study design or analysis mechanics.

Retain such material only when the source directly supports an independent patient-level diagnostic, prognostic, treatment, MRD, or germline implication. Do not convert absence of evidence into evidence of no effect.

If the source supports an isolated observation but no independently useful, correctly scoped standalone conclusion can be stated without assumed study knowledge or unsupported inference, do not create or retain a card for that observation.

## Card fields and consolidation

- `genes` contains only genes participating in the card's exact proposition.
- `diseases` records exact source-supported clinical applicability; derived ancestors are indexing terms only and do not broaden scope.
- The card's locator, interpretation, disease scope, genes, category, and evidence bundle must all describe the same proposition.
- Do not merge distinct propositions merely because they share a gene, disease, category, paragraph, table, framework, or census claim.
- **Parallel-gene consolidation exception:** when separate census claims differ only by gene identity and otherwise make the same clinical proposition with the same disease scope, category, population, treatment/comparator, clinical role/outcome, direction, thresholds, qualifiers, exceptions, and evidence basis, represent them with one card. Union the participating genes and explicitly name every gene in the interpretation. Do not consolidate when any clinically material element differs. This exception does not alter Phase 1 census atomicity.
