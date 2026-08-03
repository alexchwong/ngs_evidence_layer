# Expected outputs

This directory is empty on purpose.

An expected output is a rendered block captured from a real corpus at the moment
a human last reviewed it. It is a diff target for catching unintended changes to
ordering, collapse or citation numbering — **not** a gold standard. Section 9 of
the build spec records that gold-standard cases were declined, and nothing in
this directory should be described as one.

Files here cannot be written before the pilot ingestion, because a rendered block
generated against an empty corpus would consist of nothing but `not_assessed`
lines, and a rendered block generated against invented cards would be fabricated
evidence wearing the format of real evidence. Either would be worse than an empty
directory.

## How to populate it

After WHO-5 is ingested and the corpus is built, for each case in
`examples/cases/`:

1. Run step 1 by hand or with a model: read the case and emit
   `provisional_disease`, NGS `genes`, and structured `case_facts` with unique
   `fact_id` values. Genes come strictly from the NGS result block; facts preserve
   only supplied case information.
2. Save the facts array in `case-facts.json`, then run
   `scripts/retrieve.py diagnosis --genes ... --provisional-disease ... --case-facts case-facts.json --output step2.json`.
3. In a fresh model session, apply `prompts/diagnostic_adjudication_prompt.md` to
   `step2.json` and save the JSON result as `adjudication.json`. The adjudicated
   `refined_disease` is the major category used for downstream card calling; a more
   specific source-supported entity belongs in `diagnostic_label`.
4. `scripts/retrieve.py full --diagnosis-result step2.json --adjudication-result adjudication.json --output bundle.json`
5. `scripts/render.py --bundle bundle.json --output examples/expected/<case>.md`
6. **Read it.** Commit it only once a human has looked at it and agreed it is
   what the corpus should be saying. Committing an unreviewed block turns a diff
   target into a record of a mistake.

Re-capture after any deliberate change to ordering, collapse or numbering, and
say so in the commit message. An unexplained diff here means something moved that
nobody meant to move.
