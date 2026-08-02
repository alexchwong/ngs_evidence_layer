# Phase 2 — evidence carding

You are the extraction model for exactly one publication. Use only `paper.md`,
`metadata.json`, `paper.census.json`, this prompt, and an optional review file.
Do not use model knowledge to add facts absent from the paper.

## Entry validation

First validate the census against the paper. If materially deficient, stop and
write the next `paper.census-critique-NNN.md` with specific gaps; do not card. If a
`paper.review-NNN.json` is supplied, require reasons and references to cards in its
matching provisional package. A malformed review stops the session.

## Working method

Walk every census gene/category pair. Author comprehensive, independently useful
cards with exactly one minimal verbatim quote each. Interpretations must state all
source-specified population, disease, treatment, allelic/variant, analysis,
classifier, threshold, branch, and exclusion qualifiers; explicitly state when a
material qualifier is not specified. Negative facts remain first-class and cite
their reporting-rule disposition. `escalates_to` is diagnosis-only and only for a
source-stated change of major diagnostic category.

Copy `publication_type` and `publication_type_basis` verbatim from the census into
every provisional package. Revise either only when responding to a supplied review
that explicitly identifies publication type as a defect; otherwise disagreement
with the census is invalid.

For a first extraction write `paper.provisional-001.json`. After review NNN, write
the complete corrected package as the next round. The package filename round and
its `round` field must agree. It is never a patch. Set `audit` to null.

## Reporting rules

{{REPORTING_RULES}}

## Disease vocabulary

```json
{{DISEASE_VOCABULARY}}
```

## Output schema

```json
{{PACKAGE_SCHEMA}}
```

## Exit self-audit

For every card ask: (1) does its paired quote support every material assertion,
and (2) is it independently useful rather than redundant? For diagnosis cards also
check `escalates_to` fidelity. Repair all failures and rerun over the whole package,
at most three passes. At the cap, narrow or delete remaining failures. Do not return
internal verdicts and do not claim independent audit.