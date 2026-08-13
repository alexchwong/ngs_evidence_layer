# NEL categorical marking prompt

## Unit of assessment

Assess **each rubric section independently**:

- **R1 — Diagnosis and classification**
- **R2 — Prognostic interpretation**
- **R3 — Clinical actionability**
- **R4 — MRD interpretation**
- **R5 — Possible germline flagging**

Assign exactly one category to each rubric section. An answer may therefore be fully correct for one rubric and partially correct, erroneous or not applicable for another.

Within an applicable rubric, assess all of its case-specific **RnCm** criteria together and assign one outcome to the rubric as a whole. Do not assign separate outcomes to individual RnCm criteria.

## Categories

### Fully correct

All essential case-specific criteria for the rubric are satisfied, and the answer contains no material incorrect statement within that rubric. Concise wording, different ordering and additional correct context do not reduce the category.

### Partially correct

The central conclusion for the rubric is present and correct, but an important required qualification, distinction, limitation or secondary conclusion is incomplete or imprecise. The defect does not reverse the main interpretation.

Examples include:

- Correct diagnosis but omission of a required material WHO-5/ICC divergence.
- Correct prognostic category but omission of a required molecular driver or limitation.
- Correct treatment implication stated without a required qualification concerning disease phase, access or uncertainty.
- Correct possible-germline flag without recommending constitutional confirmation.

### Omission error

The central required conclusion for an applicable rubric is absent and cannot reasonably be inferred from the answer. The answer does not make a material contradictory claim within that rubric.

Examples include:

- No prognostic interpretation when R2 contains case-specific criteria.
- Failure to identify NPM1 as the required dedicated MRD target.
- Failure to flag possible germline origin when R5 is applicable.

### Commission error

The answer makes a material incorrect assertion within the rubric where silence or a qualified statement would have been preferable. A correct statement elsewhere in the same rubric does not neutralise the error.

Examples include:

- Assigning the wrong diagnosis or prognostic category.
- Applying a prognostic model to a disease for which it is not validated.
- Calling IDH1, IDH2, DNMT3A or another unsupported variant a validated stand-alone MRD marker.
- Interpreting routine NGS non-detection as biological absence or molecular remission.
- Declaring a tumour-only variant germline.
- Recommending a mutation-directed treatment unsupported by the detected alteration.
- Overstating drug sensitivity where only a cautious possibility is supported.
- Stating a negative finding that is false or contradicts supplied patient facts, or using a negative finding to support a materially incorrect classification or management conclusion.

### Hallucination commission error

The answer fabricates or materially misrepresents evidence to support a claim. This category supersedes an ordinary commission error for that rubric.

This includes:

- Inventing a study, guideline, trial, approval, threshold, quotation, patient result or database entry.
- Giving a citation that does not exist.
- Attributing a claim or quotation to a real source that does not support it.
- Falsely claiming that testing demonstrated an event not supplied in the case, such as constitutional origin, phase, copy-neutral loss of heterozygosity, a second mutation or a cytogenetic abnormality.

An unsupported scientific or clinical assertion without fabricated evidence is an ordinary commission error, not automatically a hallucination commission error.

### Not applicable

Use **not applicable** when the case contains no criteria for that rubric. This is the default outcome for any rubric not listed as applicable in the case-specific marking criteria.

Do not infer applicability merely because the candidate discusses that topic. For example, an unsolicited treatment or germline comment does not make R3 or R5 applicable. However, a material incorrect unsolicited statement should be recorded under the most relevant applicable rubric when it changes or contradicts the required interpretation; otherwise note it separately without changing a not-applicable outcome.

## Outcome precedence

First determine whether the rubric is applicable.

- If no case-specific criteria exist for that rubric, assign **not applicable**.
- If the rubric is applicable, use this precedence when more than one defect is present:

1. Hallucination commission error
2. Commission error
3. Omission error
4. Partially correct
5. Fully correct

Use **omission error** when the central required conclusion is absent. Use **partially correct** only when the central conclusion is present and correct but a secondary required element is incomplete.

## Prompt for the marking LLM

You are marking an NGS Evidence Layer (NEL) final report against a case-specific categorical rubric.

### Inputs

You will receive:

1. The validation case identifier.
2. `validation-case.md` — the original clinical, morphological and laboratory case information.
3. `report-final.md` — the candidate NEL report to mark.
4. `marking-criteria.md` — the case-specific RnCm marking criteria.
5. `evidence.md` — NEL evidence for verifying literature claims and citations only.

### Core task

Score **R1, R2, R3, R4 and R5 separately**. Always return all five rubric sections.

For each rubric:

1. Determine whether any case-specific criteria exist for that rubric.
2. If none exist, assign **not applicable**.
3. If criteria exist, assess all criteria in that rubric together.
4. Assign exactly one outcome:
   - **fully correct**
   - **partially correct**
   - **omission error**
   - **commission error**
   - **hallucination commission error**
5. State which RnCm criteria were met, omitted or contradicted.

Do not calculate points, percentages, averages or a single overall category.

### General marking rules

- Mark `report-final.md` only. Content absent from the final report is absent for scoring, even if it may have appeared earlier in the NEL workflow.
- The case-specific marking criteria define what conclusions are required. Do not create additional requirements from `evidence.md` or outside knowledge.
- Use `validation-case.md` as the sole source of supplied patient facts.
- Use `evidence.md` only to verify whether literature-derived claims and citations in `report-final.md` are supported; do not use it to add expected conclusions beyond the marking criteria.
- Do not use outside medical knowledge or external sources.
- For a purely prohibitive criterion such as “do not infer” or “do not calculate”, silence satisfies that prohibition. Do not require an explicit negative statement unless the criterion itself requires one.
- Compare the candidate report only with the supplied case information and case-specific expected criteria.
- Treat supplied clinical and morphological findings, including any stated morphological diagnosis, as fixed facts. Do not require the candidate to reconstruct or challenge the morphology.
- WHO-5 is the primary diagnostic classifier.
- Do not penalise omission of ICC unless the case-specific criteria require it because ICC produces a materially different diagnostic entity. A different name for the same entity is not sufficient.
- Do not require a secondary prognostic classifier unless it materially changes the category.
- When less-intensive AML treatment is explicitly documented, ELN 2024 Less-Intensive is preferred. Do not penalise an answer that presents ELN 2022 first or as the primary classifier when the clinically relevant category is correct. If the case-specific criteria require both because the categories materially differ, both must be stated, but their order is not scored.
- Do not require calculation of a complete prognostic score when necessary inputs are missing. Accept the correct molecular contribution or limitation when that is what the criteria require.
- CHRS may apply to either CHIP or CCUS when the required variables are available.
- Do not require reporting of an absent mutation unless its presence is ordinarily expected in the relevant differential diagnosis, or its absence directly changes classification, allelic-state interpretation or management.
- Do not reward lists of irrelevant negative findings.
- A factually correct negative statement is neutral even when unnecessary or low-value. Do not lower the category solely because it is mentioned. Penalise a negative statement only when it is false, contradicts the supplied case, or materially contributes to an incorrect interpretation.
- Do not penalise concise wording when the required meaning is clear.
- Do not reward repetition, verbosity or restatement of supplied clinical and morphological facts unless needed to support the molecular interpretation.
- A material incorrect assertion within an applicable rubric is a commission error even when the answer also contains the correct conclusion.
- Use the hallucination category only when fabrication or material misrepresentation is demonstrable from the supplied inputs. Do not label a citation hallucinated merely because support cannot be determined from `evidence.md`.

### MRD-specific rules

- Distinguish routine diagnostic-panel sensitivity from dedicated high-sensitivity MRD testing.
- Non-detection on routine NGS means only that the variant is below that assay's reportable threshold. It does not establish biological absence, clearance or molecular remission.
- NPM1 requires dedicated high-sensitivity testing when it is the validated leukaemia-specific MRD target.
- IDH1 and IDH2 are not validated stand-alone MRD markers and must not independently establish molecular remission or relapse.
- DNMT3A and other clonal-haematopoiesis-associated variants must not be used as stand-alone determinants of MRD status when the case-specific criteria exclude them.
- Do not invent a universal treatment timepoint, specimen type, assay sensitivity or threshold when these are not supplied.

### Possible-germline rules

Apply these rules only when R5 contains case-specific criteria:

- Require wording such as **possible**, **suspected** or **presumed germline**.
- Require constitutional confirmation using an appropriate validated non-haematopoietic specimen and, where specified, genetic counselling or donor review.
- Do not accept a definitive germline call from tumour-only sequencing.
- Do not require germline flagging merely because a VAF is near 50%; the recognised gene, variant and personal phenotype must provide the case-specific trigger.
- Do not require assertions about phase, shared clonality or which allele is constitutional unless directly demonstrated.

## Required output format

```markdown
## Case [validation case identifier]

### R1 — Diagnosis and classification
**Category:** [fully correct | partially correct | omission error | commission error | hallucination commission error | not applicable]

**Criteria assessment:** [For example: Met R1C1 and R1C2; omitted R1C3; contradicted none. Write "No R1 criteria" when not applicable.]

**Reason:** [One or two sentences identifying the decisive basis for the category.]

**Candidate evidence:** [Quote or closely paraphrase the relevant statement. Write "No relevant statement" for an omission and "Not applicable" when no criteria exist.]

**Expected:** [State the minimum required conclusion or limitation. Write "No case-specific R1 criteria" when not applicable.]

### R2 — Prognostic interpretation
[Use the same fields.]

### R3 — Clinical actionability
[Use the same fields.]

### R4 — MRD interpretation
[Use the same fields.]

### R5 — Possible germline flagging
[Use the same fields.]
```

Always return all five rubric sections. Do not produce a numeric total, convert categories into points or assign an overall pass/fail result.
