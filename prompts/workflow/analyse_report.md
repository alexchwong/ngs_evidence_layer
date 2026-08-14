# Analyse the case against all reporting rules

## Task

Answer every reporting rule using the integrated case and the retrieved evidence. 
Assign evidence-card tags that directly support each answer. 
Explicitly classify every rule outcome as reportable or omitted.

## REPORT versus OMIT classification

The following principles should be used when deciding whether to report a statement of fact.

### REPORT THE FOLLOWING:
- The presence of a variant alters clinical diagnosis, prognosis or treatment.
- The presence of a variant indicates the variant can be used as a biomarker
- The presence of a variant is suspicious for a germline variant.
- The absence of a variant contradicts the initial provisional diagnosis provided in the clinical stem
- A variant, which is usually expected to be present given the clinical context, alters diagnosis, prognosis, treatment.
- The presence of a variant, where there is no morphological evidence of haematological condition, indicates clonal haematopoiesis
- The presence of a variant indicates dual pathology
- The individual prognostic value of each NGS variant must be reported (adverse, favourable, or neutral)
- The relevant applicable prognostic score (when present) needs to be stated.

### OMIT THE FOLLOWING:
- The absence of a variant when the variant is not usually expected to be present given the clinical stem
- When treatment does not change from standard practice due to absence of a variant
- When there are no suitable biomarkers
- When there are no suspicious germline variants

## Task-specific rules

- Include every rule from `R1.1` through `R5.9` exactly once and in source order.
- Write exactly one line per rule. Do not add headings, bullets, blank lines, code fences, commentary, or other content.
- Begin each line with the exact rule ID followed by one space, then exactly one classification token: `REPORT:` or `OMIT:`.
- Every rule MUST be classified. A line without exactly one of these two tokens immediately after the rule ID is invalid.
- After `REPORT:` or `OMIT:`, give the rule's self-contained, case-specific outcome on that same line.
- Use the integrated diagnosis in `case.md`; do not re-adjudicate it.
- Use `evidence.md` as the complete literature-evidence boundary.
- Follow `prompts/workflow/citation_rules.md` exactly for every line's citation disposition.
- Keep card-level evidence granularity: cite every evidence card that directly supports the answer using its exact runtime `card_tag`.
- Use only tags copied exactly from `evidence.md`; never infer, reconstruct, shorten, or invent a tag.
- Use `(no citation required)` for patient-specific result facts that do not themselves require literature support.
- A line without a terminal citation disposition is invalid. Never leave the citation state implicit.
- Card markers are allowed only as the terminal citation suffix. Do not place `[card:...]` inside answer prose.
- Do not repeat the same card marker on one rule.



## Validation repair

If deterministic validation reports a citation-tag failure:

- repair only the affected rule(s);
- inspect/edit the current `report-draft.md`;
- re-read `prompts/workflow/citation_rules.md` before repairing the citation defect;
- `evidence.md` is the only evidentiary/source-content file you may read or re-read during citation repair;
- locate the supporting statement in `evidence.md` and copy its exact runtime `card_tag`;
- do not read or re-read `case.md`, `rules/agreed_reporting_rules.md`, `card-tags.json`, `bundle.json`, `diagnostic_evidence.md`, `adjudication.json`, `cards/`, the corpus/index, the original case document, or any other source file;
- never derive a runtime tag from a stable card ID or from `card-tags.json`.

Do not change unaffected rule answers merely because validation failed elsewhere.

## Output contract

Return Markdown only in this exact line grammar:

```text
R1.1 REPORT: Patient-specific conclusion. [card:a1b2c3]
R1.2 REPORT: Patient-specific conclusion supported by two cards. [card:a1b2c3][card:d4e5f6]
R1.3 OMIT: This topic has no reportable implication. (no citation required)
```

Continue in exact source order through `R5.9`.

## Final check

Before returning, verify privately that there is exactly one line for every rule; every line follows `citation_rules.md`; every card tag is copied exactly from `evidence.md`; every rule has exactly one `REPORT:` or `OMIT:` classification; every non-reportable rule outcome uses `OMIT:`; `REPORT:` lines contain report-ready clinical prose rather than report-construction instructions; and reportable negative findings have not been converted into omission directives.
