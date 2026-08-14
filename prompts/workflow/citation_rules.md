# Shared runtime citation rules

These rules are mandatory for every model-written reporting artifact that uses runtime evidence-card tags. Citation integrity takes precedence over formatting, compression, sentence restructuring, and word-count targets.

## Sentence citation contract

- Every sentence-ending full stop MUST be followed immediately by exactly one space and exactly one complete citation disposition.
- A citation disposition is either one or more adjacent runtime card markers or `(no citation required)`:
  - `Sentence. [card:a1b2c3]`
  - `Sentence. [card:a1b2c3][card:d4e5f6]`
  - `Sentence. (no citation required)`
- Never place a runtime card marker or `(no citation required)` before the full stop.
- Never combine runtime card markers with `(no citation required)` for the same sentence.
- Card markers must be copied exactly. Never create, infer, alter, shorten, parse, replace, translate, or renumber a runtime card tag.
- Duplicate card markers within one citation disposition may be removed; otherwise do not discard a supporting marker merely because another marker appears sufficient.

## Combining and splitting sentences

- When two or more source assertions are combined into one sentence, the resulting sentence MUST carry the union of every runtime card marker supporting the retained facts.
- If any combined source assertion requires literature support, the combined sentence must use the relevant runtime card markers; `(no citation required)` must not replace required card citations.
- When one source sentence is split into multiple sentences, each resulting sentence MUST inherit the complete citation disposition required for the facts it retains.
- Preserve citation provenance when shortening, reordering, grouping, or otherwise restructuring prose.

## No-citation disposition

- `R0.1` is a mandatory patient-result rule and MUST end with `(no citation required)`; never append runtime card markers to `R0.1`.
- Use `(no citation required)` only where the source content is a patient-specific fact or other content explicitly designated as not requiring literature support.
- Do not invent literature citations for patient-result facts solely to satisfy the sentence citation contract.

## Word counts

- Runtime `[card:xxxxxx]` markers do not count toward formatting-prompt word limits.
- `(no citation required)` is a workflow citation disposition, not report prose, and does not count toward formatting-prompt word limits.
- Word-count targets are model instructions only; citation integrity must never be weakened to satisfy them.

## Examples

Valid:

```text
The integrated diagnosis is AML with mutated NPM1. [card:a1b2c3]
The molecular findings support favourable-risk disease and an NPM1-directed MRD strategy. [card:a1b2c3][card:d4e5f6]
Detected variants include NPM1 and FLT3-TKD. (no citation required)
```

Invalid:

```text
The integrated diagnosis is AML with mutated NPM1 [card:a1b2c3].
The integrated diagnosis is AML with mutated NPM1.[card:a1b2c3]
The integrated diagnosis is AML with mutated NPM1. [card:a1b2c3] (no citation required)
```
