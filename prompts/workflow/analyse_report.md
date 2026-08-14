# Analyse the case against all reporting rules

## Task

Answer every reporting rule using the integrated case and the retrieved evidence, assign the exact runtime evidence-card tags that directly support each answer, and explicitly classify every rule outcome as reportable or omitted.

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

## REPORT versus OMIT classification

- Use `REPORT:` when the patient-level conclusion is eligible to appear in the final report. The text after `REPORT:` must be report-ready clinical prose, not an instruction about what the report should say.
- Use `OMIT:` when the reporting rule concludes that the topic should not appear in the final report. The text after `OMIT:` should concisely identify the topic or commentary to suppress.
- `OMIT:` means that Step 6B must apply the instruction but must not reproduce, paraphrase, negate, or explain it in the final report.
- Canonicalise rule wording such as “omit”, “do not mention”, “do not state”, “do not discuss”, or “silence is appropriate” to `OMIT:` when the intended patient-level outcome is absence of that topic from the report.
- Do not turn an omission instruction into negative clinical prose. For example, if the rule says an irrelevant MRD limitation should be omitted, write `OMIT: MRD commentary about that finding.` rather than a reportable sentence explaining that the finding is unsuitable for MRD.
- Do not use `OMIT:` merely because an answer contains a clinically meaningful negative finding. If an absent finding, limitation, uncertainty, or negative result materially affects diagnosis, classification, prognosis, treatment, MRD, or germline interpretation and the rule calls for it to be reported, write the self-contained reportable conclusion normally.
- `OMIT:` lines still require the terminal citation disposition required by `citation_rules.md`.
- Never write report-construction meta-language after `REPORT:`, including `The final report should ...`, `Report ...`, `Omit ...`, `Do not mention ...`, `Do not report ...`, or `Do not discuss ...`. Either convert the content to direct clinical prose or classify the rule as `OMIT:`.
- A clinically meaningful negative result may still be `REPORT:` when the negative itself changes diagnosis, classification, prognosis, treatment, MRD interpretation, or germline assessment. Do not convert such a finding to `OMIT:` merely because it contains words such as `not`, `no`, or `cannot`.

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
