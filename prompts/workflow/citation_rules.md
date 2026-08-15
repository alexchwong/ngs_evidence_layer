# Shared runtime citation rules

These rules are mandatory for every model-written reporting artifact that uses runtime evidence-card tags. Citation integrity takes precedence over formatting, compression, sentence restructuring, and word-count targets.

Use the citation contract that matches the artifact being written. Do not combine the two contracts.

## Rule-draft citation contract

This contract applies to `report-draft-dx.md`, `report-draft-remainder.md`, and `report-draft.md`.

- Each reporting-rule line is one citation unit, even when its answer prose contains more than one sentence.
- Each rule line MUST have exactly one terminal citation disposition after the final sentence-ending full stop.
- A terminal citation disposition is either one or more adjacent runtime card markers or `(no citation required)`:
  - `R1.1 REPORT: Patient-specific conclusion. [card:a1b2c3]`
  - `R1.2 REPORT: Patient-specific conclusion with two directly supporting cards. [card:a1b2c3][card:d4e5f6]`
  - `R1.3 OMIT: This topic has no reportable implication. (no citation required)`
- Do not place `[card:...]` or `(no citation required)` inside the answer prose. Intermediate sentences on a rule line do not receive their own citation disposition.
- Cite **every evidence card directly supporting the answer** and preserve card-level granularity.
- When different cards support different clauses or sentences within one rule answer, the terminal citation disposition MUST contain the union of all directly supporting runtime card markers.
- Do not discard a directly supporting card merely because another cited card appears sufficient.
- Use only runtime card tags exposed in the evidence file permitted for that model step. Never create, infer, alter, shorten, parse, replace, translate, or renumber a runtime card tag.
- Never combine runtime card markers with `(no citation required)` on the same rule line.
- `R0.1` is mandatory patient-result content and MUST end with `(no citation required)`; never append runtime card markers to `R0.1`.
- Use `(no citation required)` only when the complete rule answer is patient-specific result content or other content explicitly designated as not requiring literature support.

Valid:

```text
R1.1 REPORT: The integrated diagnosis is AML with mutated NPM1. [card:a1b2c3]
R2.1 REPORT: The available findings support intermediate risk. A missing qualifier would modify this assignment. [card:a1b2c3][card:d4e5f6]
R5.1 OMIT: Germline predisposition is not supported by the detected findings. (no citation required)
```

Invalid:

```text
R2.1 REPORT: The available findings support intermediate risk. [card:a1b2c3] A missing qualifier would modify this assignment. [card:d4e5f6]
R1.1 REPORT: The integrated diagnosis is AML with mutated NPM1 [card:a1b2c3].
R1.1 REPORT: The integrated diagnosis is AML with mutated NPM1. [card:a1b2c3] (no citation required)
```

## Final-report sentence citation contract

This contract applies to `report-final.md` before deterministic citation rendering.

- Every sentence-ending full stop MUST be followed immediately by exactly one space and exactly one complete citation disposition.
- A citation disposition is either one or more adjacent runtime card markers or `(no citation required)`:
  - `Sentence. [card:a1b2c3]`
  - `Sentence. [card:a1b2c3][card:d4e5f6]`
  - `Sentence. (no citation required)`
- Never place a runtime card marker or `(no citation required)` before the full stop.
- Never combine runtime card markers with `(no citation required)` for the same sentence.
- Card markers must be copied exactly. Never create, infer, alter, shorten, parse, replace, translate, or renumber a runtime card tag.
- Duplicate card markers within one citation disposition may be removed; otherwise do not discard a supporting marker merely because another marker appears sufficient.

## Combining and splitting final-report sentences

- When two or more source assertions are combined into one sentence, the resulting sentence MUST carry the union of every runtime card marker supporting the retained facts.
- If any combined source assertion requires literature support, the combined sentence must use the relevant runtime card markers; `(no citation required)` must not replace required card citations.
- When one source sentence is split into multiple sentences, each resulting sentence MUST inherit the complete citation disposition required for the facts it retains.
- Preserve citation provenance when shortening, reordering, grouping, or otherwise restructuring prose.

## No-citation disposition

- `R0.1` is a mandatory patient-result rule and MUST end with `(no citation required)` in rule drafts; never append runtime card markers to `R0.1`.
- Use `(no citation required)` only where the source content is a patient-specific fact or other content explicitly designated as not requiring literature support.
- Do not invent literature citations for patient-result facts solely to satisfy a citation contract.

## Word counts

- Runtime `[card:xxxxxx]` markers do not count toward formatting-prompt word limits.
- `(no citation required)` is a workflow citation disposition, not report prose, and does not count toward formatting-prompt word limits.
- Word-count targets are model instructions only; citation integrity must never be weakened to satisfy them.
