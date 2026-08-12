# Evidence bundle rules

Every card must have exactly one evidence bundle. The bundle must directly support every material assertion in the interpretation using source-verbatim fragments from the paper. A locator is navigation metadata, not evidence.

Preserve every qualifier needed to determine where the claim applies or to prevent clinical misapplication. Do not include methodological detail unless it changes the clinical meaning or strength of the claim. Do not use a bibliographic reference-list entry, a heading alone, unsupported nearby text, or model knowledge as substantive evidence.

For germline content, distinguish established inherited or constitutional status from possible constitutional origin and from a recommendation or indication for germline work-up; a work-up recommendation supports only a conditional interpretation.

Use `contiguous_text` when one coherent contiguous passage is sufficient. Its sole fragment has role `claim` and may contain multiple contiguous sentences. Expand around the explicit role claim only as needed to capture antecedents, scope, population, treatment, comparator, analysis, thresholds, exclusions, direction, or clinical consequence. Stop only when the fragment supports every material element of the interpretation without relying on unquoted context.

Use `composite_text` only when no single coherent passage contains the minimal sufficient evidence. Use two to six independently verbatim fragments. One or more `claim` fragments may jointly support one source assertion; add `scope_heading`, `legend`, or `footnote` fragments only when they provide necessary governing context. Every fragment must contribute material support recorded in `support_map`, and all fragments must have compatible scope. Do not combine separate findings, populations, analyses, classifier branches, or independently useful conclusions. If a fragment is unnecessary, use `contiguous_text`, narrow the interpretation, split the card, or omit it.

A `scope_heading` is valid only when the substantive passage occurs within that heading's section and no intervening heading changes scope. A heading supplies context; it does not establish a role claim by itself.

Use `table_relation` when a table value cannot be interpreted defensibly without its governing labels. Quote each required `column_header`, `row_header`, `cell`, `legend`, and `footnote` as a separate fragment. Preserve all applicable row and column headers, spanning or multi-level headers, and marked legends or footnotes. Omit the card when extraction damage or missing structure leaves the relation ambiguous. Do not replace source labels with model-authored key/value facts.

Map every material assertion in the interpretation to explicit supporting source text in `support_map`. If any assertion is unsupported, expand the bundle, narrow the interpretation, split the card, or omit it. Once sufficient evidence is assembled, do not shorten it merely for concision.
