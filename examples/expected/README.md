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

1. Run step 1 by hand or with a model: read the case, emit
   `{"provisional_disease": ..., "genes": [...]}`. Genes come strictly from the
   NGS result block.
2. `scripts/retrieve.py diagnosis --genes ... --provisional-disease ... --output step2.json`
3. Run step 3: choose `refined_disease` from the provisional disease and the
   escalation candidates only.
4. `scripts/retrieve.py full --diagnosis-result step2.json --refined-disease ... --output bundle.json`
5. `scripts/render.py --bundle bundle.json --output examples/expected/<case>.md`
6. **Read it.** Commit it only once a human has looked at it and agreed it is
   what the corpus should be saying. Committing an unreviewed block turns a diff
   target into a record of a mistake.

Re-capture after any deliberate change to ordering, collapse or numbering, and
say so in the commit message. An unexplained diff here means something moved that
nobody meant to move.
