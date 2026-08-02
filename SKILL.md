---
name: ngs_evidence_layer
description: Corpus-grounded evidence layer for myeloid NGS interpretation. Ingests one publication per session into gene-based evidence cards with verbatim quotes held separately, then retrieves and renders a deterministically ordered, citable evidence block for a case. It collates; it does not synthesise, reconcile or conclude.
---

# NGS evidence layer

## What this is, and the downstream contract

This skill turns publications into evidence cards, and a case into a block of
evidence meanings with card IDs and numbered citations attached.

**It is an evidence layer, not a report writer.** It does not draft an
interpretative summary, decide which findings matter most, resolve two
classifiers that disagree, or say what should happen to the patient. Report
synthesis happens in a separate step, downstream, which receives the rendered
block as context. If you find yourself weighing one card against another, you
have left this skill's job.

The rule the whole design rests on: **no model haematology knowledge enters the
output.** Everything the layer asserts came out of an ingested publication and
carries a card ID back to a quote. A statement you know to be true, that no card
supports, does not go in. A gene the corpus cannot address is named as
unaddressed rather than answered from memory — a silently absent gene is
indistinguishable from a gene that was considered and cleared, and those are very
different things.

`rules/agreed_reporting_rules.md` is injected into ingestion and retrieval
prompts. It is not background reading. It is the checklist that drives what gets
extracted, and its rule IDs (R1.3, R2.7, R4.4 and so on) are citable in output.

## Session isolation

**One publication per session, no exceptions.** A carder that has seen how
another paper was carded starts pattern-matching to it instead of reading the
document in front of it. That is the exact failure this build exists to remove.

Load only what the session type calls for:

| Session | Load | Do not load |
|---|---|---|
| Phase 1 census | the source Markdown and generated Phase 1 context | any other publication, the corpus, retrieval scripts |
| Phase 2 carding | the source Markdown and generated Phase 2 context | any other publication's extraction |
| Phase 3 audit | the source Markdown and generated Phase 3 context | the reporting rules, the schemas, the census |
| Retrieval | the free-text case, `SKILL.md`, `rules/agreed_reporting_rules.md`, the built corpus | individual publications' cards or quotes |

For ingestion operations, `scripts/ingest.py pre-phase1`, `pre-phase2`, and
`pre-phase3` now package the permitted non-paper material into one portable
context file. Supply that context plus the source Markdown to either a local
agent or an external chat. Each phase returns one JSON file. A model must not
declare a phase complete merely because it authored JSON: completion occurs only
after the deterministic command validates and accepts the response and prints
`PHASE N COMPLETE — VALIDATION PASS`.

The audit session is deliberately starved of context. An auditor holding the
rules and the schema starts improving cards instead of judging them, and an
auditor that improves cards is not an auditor.

Run `scripts/next_paper.py` to be told which publication is due and which phase
it is at. Do not choose one yourself.

## Disease vocabulary

Closed and categorical. No free-text subtypes, no modifiers. The canonical list
lives in `schema/disease_vocabulary.json`:

```
CHIP · CCUS · MDS · MDS/AML · AML · APL · MDS/MPN-U · CMML · aCML ·
MDS/MPN-SF3B1-T · JMML · MPN-U · PV · ET · PMF · post-PV/post-ET MF · CML ·
CNL · CEL · mastocytosis ·
myeloid/lymphoid neoplasm with eosinophilia and TK fusion · BPDCN ·
germline predisposition syndrome · myeloid neoplasm, unspecified ·
lymphoid neoplasm
```

**Umbrella tagging.** Where the source is specific, tag the specific entity *and*
its umbrella, so a query on either sees the card. APL is also tagged AML. PV, ET,
PMF, post-PV/post-ET MF, CNL and CEL are also tagged MPN-U. The validator
enforces this, because a card tagged APL alone is not a visible error — it is a
silent retrieval hole.

**A genuinely disease-agnostic claim leaves the array empty** rather than
guessing. Do not tag a disease the source did not name.

Dropping modifiers has a deliberate consequence: therapy-related,
post-cytotoxic and paediatric contexts **cannot be tagged**. They must be stated
in the interpretation prose, which the authoring rule below already requires.

---

# Phase 1 — Census

Walk the document once, from the top, section by section, including every table
and every table footnote. Do not skip to the parts that look relevant; the point
of the census is that it is not driven by a question anyone thought to ask.

Return one Phase 1 JSON census against the schema embedded in the generated
context. After deterministic acceptance its stable path is
`output/phase1/<stem>.phase1.json`:

- **every gene about which the publication makes a claim**, with the sections and
  tables where each claim appears;
- **for each gene, which of the five categories** the publication touches:
  `diagnosis`, `prognosis`, `treatment`, `biomarker`, `germline`;
- **every rule-relevant statement with no gene attached**, recorded under
  `geneless_statements` for visibility. These are not carded — cards are
  gene-based — but a census that omits them hides what the corpus is missing.

Only intact Markdown tables are interpreted. A table that has lost its structure
in extraction is reported, not guessed at.

If critical values — model weights, thresholds, complete gene lists — are
referenced but live in supplementary material, record them under
`supplement_flags`. **Do not refuse.** The operator may later supply a
concatenated Markdown of main text plus supplement and re-ingest, which removes
the original cards for that publication first.

The census is the completeness contract. It is what makes under-extraction
countable.

---

# Phase 2 — Carding

Walk the census. For each entry, write a card or record why not.

## What to look for, per gene

The reporting rules drive the search. Within each gene, ask whether the source
states:

- an entity-defining criterion, with its blast range, morphology, cytogenetics,
  variant class, VAF threshold and exclusions (R1.3)
- a diagnostic precedence relationship (R1.4)
- a CHIP/CCUS versus neoplasm distinction (R1.5)
- a diagnostically informative *negative* finding (R1.7)
- an allelic-state rule, TP53 or otherwise (R1.9)
- a prognostic effect, with the disease, the framework, the treatment context and
  whether the association was univariable or multivariable-adjusted (R2.1, R2.5)
- a prohibition on transferring a model between diseases (R2.4)
- a treatment implication, with its phase and whether it is established, optional
  or investigational (R3.2, R3.3)
- a variant-class-specific treatment logic (R3.8)
- an MRD validation status, positive or negative (R4.1, R4.3, R4.7)
- a germline architecture, phenotype pairing or confirmation requirement
  (R5.1, R5.3, R5.4)

A card is written when the source *states* something. Silence is not a finding.
But the gate is not "is this important" — comprehensiveness is the goal, and a
low card-to-census ratio is a signal that the gate was applied too tightly, not a
sign of a clean run.

Statements that mix karyotype and sequence variants **are carded**. Cytogenetics
and fusions are not excluded, provided the card names at least one gene.

## Card fields

In the portable workflow, cards and quotes are written together in
`output/phase2/<stem>.phase2.json` against
`schema/ingestion_package_schema.json`, with `audited: false` and `audit: null`.
The scripts generate compatibility card and quote files for deterministic corpus
building; these are private build views, not phase interfaces, and models do not
author or edit them.

- **`card_id`** — begins with `publication_key` plus `-`. Derive the key with
  `scripts/make_key.py`; never hand-build it.
- **`locator`** — section heading, table number, figure number or page.
- **`genes`** — at least one HGNC symbol. A rule statement with no gene is out of
  scope for the corpus and belongs in the census's `geneless_statements`.
- **`diseases`** — from the closed vocabulary, umbrella-tagged, possibly empty.
  `diagnosis` cards may be disease-agnostic; `germline` cards usually are.
  `prognosis`, `treatment` and `biomarker` cards should name a disease.
- **`category`** — exactly one of `diagnosis`, `prognosis`, `treatment`,
  `biomarker`, `germline`. These are not the R1–R5 rule IDs and do not map to
  them one to one.
- **`evidence_tier`** — **the strength of the analysis behind this claim**, read
  off the quote, independent of what kind of document it appeared in. Strongest
  first: `guideline criterion`, `multivariable-adjusted`,
  `univariable or descriptive`, `restated secondary`. A review restating a trial
  result is not automatically the weakest tier; a guideline reporting an
  unadjusted association is not automatically the strongest.
- **`escalates_to`** — see below. Null on all non-diagnosis cards.
- **`secondary_citation`** — where the card rests on an upstream source, a full
  citation object built by `make_key.py --secondary` from what the publication's
  reference list supplies, carrying `citation_incomplete` for whatever it does
  not. Null where the card rests on the publication's own analysis.

**Quotes do not live on the card.** They go to
the package's top-level `quotes` array, keyed by `card_id`, cap 400 words, and the
quote must be the minimum needed to substantiate the interpretation. Quote files
are never distributed and are never returned by retrieval; they exist for audit
and hallucination checking. One quote per card, one card per quote.

The same minimal source passage may support more than one card. Identical quote
text is therefore a review signal, not proof of duplication: one sentence can,
for example, state both a diagnostic criterion and an independent treatment
implication. Do not manufacture different quote boundaries merely to make quote
text unique. Each card must still express an independently useful claim that its
quote supports.

## The authoring rule for `interpretation`

This is the single most important thing in the skill.

> Where the source specifies them, the interpretation must state the population,
> the treatment context, any co-mutation or allelic-state dependency including
> variant-level qualifiers, and whether an association was univariable or
> multivariable-adjusted. **Where the source does not specify one of these, say so
> explicitly.**

A silent omission reads to any downstream reader as generality. "GENEX is
adverse" and "GENEX is adverse in intensively treated patients; the source does
not state whether this held after adjustment" are different claims, and only one
of them is honest.

Because there are **no typed criteria fields** — no `criteria`, `threshold`,
`conditional`, `classifier` or `entity` — the rule extends to criteria. Where the
source states any of the following, the interpretation must state it:

- the classifier and edition under which the statement holds;
- the entity name as that classifier writes it;
- any numeric cut-off, with its variable and its unit;
- any conditional branch, **including what the alternative branch assigns**;
- any exclusion that defeats the criterion.

Where the source does not state one of these, the interpretation says so.

**The test:** does a reader who sees only the interpretation string reach the
same conclusion as one who read the source paragraph? If not, the interpretation
is not finished.

A disease label does not imply a threshold and must not be relied on to carry
one. The closed vocabulary collapses MDS-IB1 and MDS-IB2 into `MDS`, and a
classifier's NPM1 rule may branch to two different entities on blast count.
Thresholds that matter live in the prose or they are lost.

This is also how variant-level granularity survives gene-level indexing.
FLT3-ITD versus TKD, IDH1 R132 versus IDH2 R140/R172, CEBPA bZIP in-frame, TP53
allelic state — all of it lives in prose, because the card is indexed only on
`FLT3`, `IDH1`, `IDH2`, `CEBPA`, `TP53`.

**Negative and exclusion cards are first-class.** The evidence layer emits them;
removing them is the downstream formatter's job. Where a card is a negative fact,
end the interpretation with its disposition, citing the rule ID:

```
GENEX does not confer adverse prognosis in CCUS
(negative fact; remove in final pass per R2.7)
```

## `escalates_to`

The only mechanism by which retrieval changes the major diagnostic category.

Set it **only** on a `diagnosis` card, and only where the source states that the
gene alteration determines the major diagnostic category irrespective of the
standing diagnosis. It is populated from what a classifier states during
ingestion of that classifier — never pre-populated from anyone's memory,
including yours and the operator's.

Two things that are easy to get wrong:

- **Entity refinement within a category leaves `escalates_to` null.** A variant
  that refines MDS-LB to a named MDS subtype has not moved the major category.
  The refinement goes in the prose.
- **Do not assume a gene escalates because it is famous.** FLT3-ITD is not
  entity-defining in either WHO-5 or ICC 2022; it is prognostic and therapeutic.
  Whether any given gene gets a non-null `escalates_to` is a question for the
  source in front of you, at the moment you are reading it.

## Supersession and coexistence

Supersession applies **only between versions of the same publication**. Different
publications coexist: WHO-5 and ICC, ELN 2022 and ELN 2024-LI, MRD 2021 and 2025.
They are distinguished by stating the edition in the interpretation. Two
classifiers disagreeing about a blast threshold is two cards, not a problem to be
solved. Duplicate facts across publications are permitted; deduplication is
deferred.

## Mandatory Phase 2 self-audit — simulate Phase 3 before submission

After drafting the complete package, stop authoring and audit it as though you
were the independent Phase 3 auditor. This is a separate review pass over the
complete package, not a continuation of drafting.

For **every card**, inspect only that card's `interpretation` and its exactly
paired quote first. Assign an internal `pass` or `fail` on both questions:

1. **Quote support:** Does the paired quote carry every material assertion in
   the interpretation?
2. **Independent utility:** Is the card independently useful rather than a
   materially redundant restatement elsewhere in the complete package?

On quote support, fail your draft card internally if the interpretation:

- asserts a fact, marker list, threshold, blast range, exclusion, hierarchy,
  precedence rule or conditional branch absent from the paired quote;
- generalises beyond the population, disease, classifier, treatment context,
  variant class, allelic state or analysis type named by the quote;
- states that a qualifier is absent when the paired quote supplies it;
- contradicts the paired quote or its source context; or
- requires nearby text, a table footnote or another passage to be true but does
  not include that material in the paired quote.

For every `diagnosis` card, also audit **metadata fidelity**: compare the paired
quote and interpretation with `escalates_to`. If the source says that the gene
alteration assigns a different major diagnostic category irrespective of the
standing diagnosis, `escalates_to` must name that category. If the source only
refines an entity within the same major category, it must remain null. Treat a
missing, incorrect or over-inferred value as an internal failure. Wording such as
"irrespective of blast count" is a review trigger, not an automatic rule: decide
from the complete paired passage and do not infer beyond it.

Do not pass a card merely because the interpretation is true somewhere else in
the publication. The **paired quote itself** must support the complete
interpretation. If the source supports the claim outside the current quote,
replace the quote with the minimum verbatim passage that carries the claim. If no
single quote within the 400-word limit carries it, narrow, split or delete the
card as appropriate.

On independent utility, compare the card across the complete package. Fail it
internally if another card already expresses the same claim in the same role and
context, or if it merely assigns another category without a distinct
role-specific assertion. A single card may list multiple genes when the source
makes one joint claim about them. Identical quote text alone is not a failure
when it supports genuinely distinct claims in different categories or contexts.
Never alter or truncate a quote solely to evade an identical-quote warning.

**Repair every internal failure before submission:** rewrite or narrow the
interpretation, select a better minimal quote, merge redundant cards, or delete
unsupported cards. After any repair, rerun the self-audit over the **entire
package**, because changed quotes, merges and deletions may alter support,
coverage or redundancy relationships.

Continue the draft → audit → repair cycle until every card receives an internal
pass on both questions. Then repeat schema, card/quote pairing, ID, vocabulary,
umbrella-tag and census reconciliation checks. Completeness means every supported
gene/category claim is represented, not that every census pair mechanically
receives a card.

Return only the final complete Phase 2 package with `audited: false` and
`audit: null`. Do not include the internal verdicts or claim that independent
audit has occurred. Phase 3 remains mandatory and must be performed by a
different model in a fresh session.

## Run report

State, at the end of the session:

- census entries;
- cards written;
- the ratio;
- **every census entry that produced no card, with the reason.**

Then validate:

```bash
python scripts/ingest.py validate-phase2 --id <input-id> \
    --response exchange/ingest/phase2/inbox/<stem>.phase2.json
```

The validator checks schema, vocabulary, umbrella tagging, ID discipline,
card-to-quote pairing, the verbatim presence of every quote in the source, and
the reconciliation against the census. It cannot check whether an interpretation
says more than its quote supports. That is Phase 3.

If the publication cannot be carded at all, write
`output/reports/<stem>.skipped.md` with `input_id`, `markdown_path`, `date` and a
non-empty `reason`. Do not leave silence.

---

# Phase 3 — Audit

**A different model from the one that carded, in a fresh session.** Record both in
the artefact metadata; deterministic Phase 3 validation refuses a package where
they match.

The portable Phase 3 response has the same complete package shape as Phase 2.
It preserves all extraction content, changes `audited` to `true`, and replaces
`audit: null` with audit metadata and one result per card. Deterministic
validation rejects any other Phase 2-to-Phase 3 change.

Ingestion hallucination is the fatal failure mode. Mechanical checking catches a
misquote. Only this phase catches an interpretation that drifted beyond its
quote.

## Audit instruction — paste this verbatim into the audit session

> You are auditing an evidence package extracted from the publication below. You
> have the source Markdown and the complete accepted Phase 2 package. Each card has
> exactly one quote in the package's `quotes` array, matched by `card_id`.
>
> Answer two questions per card: **(1) is this interpretation supported by this
> quote in this source, and (2) is this card independently useful rather than a
> redundant restatement of another card in this package?**
>
> Do not improve, rewrite, extend or re-scope any card. Do not suggest additional
> cards. Do not comment on what the publication should have said. If an
> interpretation is supported but you would have worded it differently, it passes.
>
> Fail a card where the interpretation asserts something the quote does not carry;
> where it generalises beyond the population, disease or treatment context the
> quote names; where it states a threshold, exclusion or conditional the quote
> does not contain; or where it contradicts the source.
>
> Also fail a card that states a qualifier as absent from the source when the
> quoted passage supplies it.
>
> For every `diagnosis` card, also compare the paired quote and interpretation
> with `escalates_to`. Fail the card if the source says the gene alteration assigns
> a different major diagnostic category irrespective of the standing diagnosis
> but `escalates_to` is null or names the wrong category. Also fail if
> `escalates_to` is non-null when the source only refines an entity within the same
> major category or does not support category reassignment. Wording such as
> "irrespective of blast count" is a review trigger, not an automatic rule; judge
> the complete paired passage and do not infer beyond it.
>
> Also fail materially redundant carding. A card is redundant when another card
> already expresses the same claim in the same role and context, or when it merely
> assigns another category to the same evidence without a distinct role-specific
> assertion in the source. Compare cards across the complete package, especially
> cards with identical or overlapping quotes and generic template interpretations.
> A single joint claim about several genes ordinarily belongs on one multi-gene
> card rather than one cloned card per gene.
>
> Do not fail cards merely because their quote text is identical. Keep separate
> cards when the shared passage supports independently useful claims in different
> categories or contexts—for example, a diagnostic criterion and a treatment
> implication. Explain the redundancy, not just the shared text, in every failure
> reason.
>
> Return the complete accepted Phase 2 package as one JSON object. Do not change
> extraction content. Change only `audited` from `false` to `true` and `audit`
> from `null` to:
>
> ```json
> {
>   "audited": true,
>   "audit": {
>     "audit_date": "YYYY-MM-DD",
>     "audit_model": "<the model you are>",
>     "extraction_model_reviewed": "<from extraction_model>",
>     "results": [
>       {"card_id": "...", "verdict": "pass"},
>       {"card_id": "...", "verdict": "fail", "reason": "..."}
>     ]
>   }
> }
> ```
>
> Do not repair failed cards in Phase 3. Give a precise reason that identifies the
> unsupported assertion or material redundancy. Failed verdicts intentionally
> block acceptance and return the publication to a separate Phase 2 rework
> session. The complete corrected package will require a fresh independent Phase
> 3 audit; never flip a verdict merely to clear the gate.
>
> Every card gets a verdict. A failed card needs a reason.

Do not repair failed cards in Phase 3. Give a precise reason that identifies the
unsupported assertion or material redundancy. A failed audit intentionally blocks
acceptance and returns the publication to Phase 2 rework. In that separate rework
session, verify every failure against the source and rewrite, requote, merge or
delete cards as needed. The complete corrected package then receives a fresh
independent Phase 3 audit; failed verdicts are never flipped merely to clear the
gate.

A failed card is rewritten or deleted during Phase 2 rework. It is not built
around.

---

# Corpus build

Quotes are not copied into the corpus or index. Phase 2 incorporation is
explicitly provisional; Phase 3 incorporation is audited. The ingestion command
revalidates every accepted package before building.

```bash
python scripts/ingest.py incorporate --after-phase 2  # provisional
python scripts/ingest.py incorporate --after-phase 3  # audited
```

Corpus versioning and sealing is a separate, later step, once the intended
publication set is in.

---

# Retrieval

Deterministic by construction. Every step is a script except two bounded model
decisions, and both are bounded by a script afterwards.

## Step 1 — model: minimal extraction from the free-text case

Case intake is free text and will be incomplete, as real reporting is. Emit only:

```json
{"provisional_disease": "MDS", "genes": ["NPM1", "SRSF2", "DNMT3A"]}
```

- Genes come **strictly from the NGS result block**, never from elsewhere in the
  clinical narrative. A gene named in a family history or a differential is not a
  detected variant.
- `provisional_disease` comes from the closed vocabulary. Where the case does not
  commit, use `myeloid neoplasm, unspecified`. Do not upgrade the marrow report's
  label because the genotype looks suggestive; that is what step 3 is for, and it
  is bounded.

Nothing else. No interpretation, no ranking, no commentary.

## Step 2 — script: diagnosis retrieval

```
python3 scripts/retrieve.py diagnosis --genes NPM1 SRSF2 DNMT3A \
    --provisional-disease MDS --output step2.json
```

Every `diagnosis` card for those genes, disease-agnostic and disease-tagged
alike, **with no disease filter at all** — a gene may point toward a diagnosis
other than the one the marrow proposed. Also emits `escalation_candidates`: the
distinct non-null `escalates_to` values found, each with the card IDs asserting
them.

## Step 3 — model: bounded refinement

Choose `refined_disease` from `{provisional_disease} ∪ escalation_candidates`
**only**. Any other value is rejected by the script. Name the card IDs that drove
a change with `--driven-by`; the script requires them when the disease moves.

In most cases there are no candidates and the provisional disease stands
unchanged. That is the normal outcome, not a failure to find something.

## Step 4 — script: full retrieval

```
python3 scripts/retrieve.py full --diagnosis-result step2.json \
    --refined-disease AML --driven-by <card-id> --output bundle.json
```

`prognosis`, `treatment` and `biomarker`: gene match **and** (disease match OR
empty disease array). `germline`: gene match only, no disease filter.

Four blocks come back:

- `retrieved` — the cards, including the step 2 diagnosis cards;
- `suppressed` — gene-matched cards excluded by the disease filter, counted by
  disease. Nothing is silently dropped, and a persistently empty block here is
  evidence that branching retrieval was never needed;
- `not_assessed` — submitted genes with no card in any category, **named
  individually**;
- provenance — corpus version and hash, card IDs, timestamp.

## Step 5 — script: render

```
python3 scripts/render.py --bundle bundle.json --output block.md
```

Interpretation strings only. **Quotes are never rendered.** Order is category,
then gene, then evidence tier strongest first, then publication year descending,
then card ID. Every line carries its card ID, so any downstream statement can be
audited back to a card and from there to a quote.

Citation numbering is scripted, never modelled: numbers assigned in order of
first appearance, one per distinct publication, a secondary citation taking its
own number in the same sequence with both appearing in the marker, primary
first. Byte-identical interpretations collapse and the surviving line carries the
union of the numbers.

If the 120k budget binds, truncation drops the weakest tier first — `restated
secondary` before `univariable or descriptive` — states what it dropped, removes
orphaned references and renumbers. Guideline criteria and multivariable-adjusted
findings are never dropped; an over-budget block warns instead.

## Missing information

Flag it only where it dictates a conclusion — for instance where a variant's
prognostic meaning depends on the disease category and the case does not
establish whether the marrow is diagnostic of MDS. Do not flag missing fields
that change nothing.

---

# What this skill does not do

- **No live sources.** CIViC and ClinicalTrials.gov are out. The corpus is the
  sole evidence source, and whatever is in it is treated as current.
- **No approval-status or jurisdiction modelling.** No fields for it, no
  reasoning about it.
- **No meta-evidence.** ACMG, ClinGen, VICC and nomenclature standards are out of
  scope; the agreed reporting rules already cover that ground.
- **No deduplication across publications.** Deferred by decision.
- **No clinical decision.** No report, no recommendation, no ranking of one
  card's importance against another's.
- **No PDFs.** Ingestion input is Markdown only.
- **No verification layer for report drafts, and no gold-standard test cases.**
  Prototype scope. `examples/expected/` is a diff target and must not be
  described as a gold standard.
