# Prompt maintenance contract

The uploadable phase prompts are generated artefacts. Edit prose in
`prompts/templates/phaseN_prompt.md`; edit rules, vocabulary, and schemas only at
their canonical source paths. Then regenerate one prompt at a time with
`python scripts/build_prompts.py --phase N`.

Changing reporting rules, vocabulary, or extraction schemas changes the meaning of
existing omissions and therefore requires re-ingestion of affected publications.
A mechanical field migration cannot recover a card that was never extracted.

Phase 3 must remain deliberately context-starved: never inject reporting rules,
disease vocabulary, schemas, census data, or another publication. An auditor with
authoring context starts improving cards instead of judging them.

Every prompt edit must preserve these invariants:

- no model knowledge enters output;
- one source-verbatim quote per card and one card per quote;
- cards are gene-indexed and independently useful;
- diseases use the closed vocabulary with required umbrella tags;
- only source-stated major-category reassignment populates `escalates_to`;
- Phase 3 never repairs extraction content.