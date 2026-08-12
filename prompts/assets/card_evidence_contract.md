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
