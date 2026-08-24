# Report sentence omit / split / merge plan

Review ALL evidence-resolved atomic reportable statements in one pass.

Goal:
- retain every clinically material proposition;
- remove clinically irrelevant content;
- use the fewest clinically readable sentences;
- preserve scope, polarity, framework, treatment context, qualifiers, and uncertainty.

For every statement choose exactly one disposition:
- `include`: retain as one semantic part;
- `omit`: remove under the omission rules;
- `split`: divide under the split rules.

## Omission

Omit when:
- fully redundant with retained material; or
- lacking useful patient-level reporting consequence.

Retain when the proposition:
- establishes, changes, qualifies, or distinguishes diagnosis or classification;
- defines or changes prognosis or risk classification;
- identifies a treatment implication;
- changes MRD interpretation;
- raises a clinically meaningful germline consideration;
- states a necessary condition, threshold, exclusion, limitation, or uncertainty.

For negative, unavailable, uncertain, non-applicable, or non-calculable findings:
- omit when they do not change clinical interpretation;
- retain when omission could make the report misleading.

Do not omit a material proposition merely to shorten the report.

## Split

Split only when a statement contains propositions that:
- require different dispositions or groups; or
- differ materially in scope, polarity, framework, context, qualifiers, or uncertainty.

Do not split:
- one coherent clinical proposition;
- parallel gene or variant findings with the same clinical meaning.

Each split part must remain faithful to its source statement.

## Merge

Merge when statements:
- are in the same report category;
- are clinically equivalent apart from gene or variant identity; and
- have compatible scope, polarity, framework, treatment context, qualifiers, and uncertainty.

Parallel statements meeting these conditions MUST use the same `group`.

Keep separate when merging would:
- change meaning;
- obscure a clinically meaningful distinction;
- broaden or narrow scope;
- combine different polarity, framework, context, qualifiers, or uncertainty;
- combine statements with different `summary_role` values.

`summary_role` is a deterministic merge boundary. Statements with different `summary_role` values MUST use different groups.
`summary_merge_key` is a deterministic mandatory-merge instruction. Statements carrying the same `summary_merge_key` MUST use the same group.

Before returning:
- compare all retained statements within each category;
- identify parallel propositions;
- use the fewest groups possible without semantic loss.

Use the same `group` label for parts to be merged. Do not merge across categories unless workflow policy explicitly permits it. Do not write final prose or reason about citations.

Return YAML only:
```yaml
dispositions:
  - statement_id: S0001
    decision: include
    reason: null
parts:
  - statement_id: S0001
    group: G01
    split_text: null
```
