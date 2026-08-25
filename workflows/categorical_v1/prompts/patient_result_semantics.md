# Patient-result semantics and encoding

These invariants apply to every model step in this workflow. They were previously
carried forward by a single session model having read them once; under a profile
where different models execute different steps nothing carries forward, so they
travel with each step.

## Test-result semantics

- Treat a test explicitly stated to be complete as complete **within its stated scope**.
- Do not assume that a test which is not mentioned was performed.
- If conventional cytogenetics are absent, a normal cytogenetic result may be used
  only as an explicit workflow assumption. It must never be stated or cited as a
  performed negative test.

## Gene-level negative inference and assay scope

`ngs-panel-scope.md` in the work directory is the complete assay-scope boundary for
gene-level NGS negative inference.

- When the patient NGS result is complete, a gene listed in that file but absent
  from the detected-variant list is negative **only for the variant classes stated
  in the panel-scope file**.
- Use that negative result to resolve reporting-rule criteria and exclusions. Do not
  treat such a gene as unresolved merely because it is not individually listed in
  the case.
- Do not describe the gene as whole-gene biological wild type, and do not extend the
  negative inference to variant classes the panel-scope file does not cover.
- A gene absent from the panel-scope file is not addressed by the assay. No negative
  inference of any kind may be drawn about it.

## REPORT/OMIT encoding

The workflow-local REPORT/OMIT taxonomy is encoded in YAML as:

- REPORT -> `omit: false` or `omit: No`;
- OMIT -> `omit: true` or `omit: Yes`.

Every rule must still contain at least one atomic statement. Omission controls
downstream inclusion only; it is not a licence to leave a rule unanswered.

## YAML output format

When the output file is YAML, it must parse. Clinical text routinely contains
characters that YAML treats as structure, so:

- Wrap every free-text value in double quotes whenever it contains a colon
  followed by a space, or begins with `-`, `?`, `*`, `&`, `{`, `[`, `%`, `@` or
  a backtick. Diagnostic wording such as `WHO-5 diagnosis: AML with NPM1
  mutation` is a mapping value to YAML unless it is quoted.
- Escape any double quote inside a quoted value as `\"`.
- Quoting is always safe. When in doubt, quote.
- Preserve the deterministic template's keys, rule IDs and ordering exactly.
  Add no keys, remove none, and reorder nothing.

## File access

The files supplied in this step are the complete permitted set. Do not request,
assume, reconstruct, or invent the contents of any other file. In particular, do
not attempt to reason about private deterministic artefacts, corpus files,
validator source, or validation marking material.
