# Report sentence omit / split / merge plan

Review ALL supplied reportable sentences in one pass.

For every statement choose exactly one disposition:
- `include`: retain the statement as one semantic part;
- `omit`: omit only when its material information is safely redundant elsewhere; give a reason;
- `split`: divide a sentence that contains multiple independently reportable propositions into two or more semantic parts.

Diagnostic classification statements must not be omitted.

Use the same `group` label for parts that can safely be merged into one final report sentence. Combine only statements from the same domain. Different group labels mean separate final sentences. The group labels are temporary; Python will deterministically reorder groups into canonical report blocks.

For `include`, return exactly one part with `split_text: null`.
For `split`, return two or more parts for that statement, each with a non-empty `split_text` that faithfully contains only that part of the original statement.
For `omit`, return no part for that statement.

Do not write final combined prose. Do not reason about citations.

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
