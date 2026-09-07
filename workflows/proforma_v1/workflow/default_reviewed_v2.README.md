# `default_reviewed_v2` — claim-addressed audit overlay

`default_reviewed_v2.yaml` is a clone of **`default.yaml`**, not of `default_reviewed.yaml`.
Every clinical owner step, the whole three-stage evidence chain, and the entire report
pipeline are carried over byte-identical. The overlay adds twelve steps, of which at
most four ever reach a model.

```text
… default clinical owners (unchanged) …
diagnosis.icc
  → audit.dx.packet        deterministic   conclusion and reasons as separate fields
  → audit.dx.coherence     model           ALWAYS (one call, all authorities)
  → audit.dx.validate      deterministic   the single review block: 1 clean regeneration
  → audit.dx.targets       deterministic   [] closes the gate
  → audit.dx.revise        model           only when a reason needs correcting
  → audit.dx.commit        deterministic   patch reason; surface everything else
diagnosis.finalize
… default PTBG owners (unchanged) …
… default evidence.assignment → audit → adjudication → finalize (unchanged) …
  → audit.ptbg.packet      deterministic   [] closes the gate
  → audit.ptbg.coherence   model           only when evidence left something unsupported
  → audit.ptbg.validate    deterministic   visible failure, no retry
  → audit.ptbg.targets     deterministic   [] closes the gate
  → audit.ptbg.revise      model           only when a reason needs rescoping
  → audit.ptbg.commit      deterministic   patch reason + reportable element; clear tags
report.blocks → report.write → report.preservation → report.finalize (unchanged)
```

## What this exists to catch

```text
conclusion: MDS with mutated TP53
stated_reasons:
  - one TP53 variant identified
  - no del(17p) or other TP53 copy loss
  - therefore not MDS with mutated TP53
```

Every reason is individually true and individually card-supportable, so evidence
review returns `supported` on all three. The defect is that the derivation refutes
its own label, and no amount of evidence machinery can see it.

`audit.dx.coherence` is therefore **unconditional**. Gating it on evidence verdicts
would drop precisely the case it exists for. The deterministic helper
`transforms._reviewed_text_coherence_flags` is passed to the prompt as a cheap prior,
never as a trigger: it fires on the literal wording above and not on a reworded
equivalent such as *"monoallelic TP53 does not meet the multi-hit requirement for that
entity"*.

For PTBG the conclusion is largely carried by the reason text itself, which evidence
review already covers, so that call is gated on `has_items`.

## What deliberately did not change

**The three-stage evidence chain is retained in full.** Merging match and audit into a
single call was in the original proposal and has been dropped. Matching over-reaches
and auditing over-rejects; a model that has just selected a card is the worst available
judge of that selection, and the disagreement rate between the two is itself signal that
adjudication consumes. Operational experience of evidence hallucination outranks the
call-count saving.

`diagnosis_complete_support` remains the stricter blocking policy for WHO1 routing
changes and is untouched.

## Repair-loop cap

`default_reviewed.yaml` declares 39 `review:` blocks, nearly all with `feedback:` and
`max_cycles: 2`, each invalidating descendants on failure. That is the repair spiral,
not syntax repair — serialisation repair is already isolated behind its own
`syntax_repair` role and its own attempt budget.

This workflow adds **exactly one** review block, and it declares **no `feedback:`**.
Omitting feedback makes `retry_target` a clean regeneration from the original inputs:
the model never sees its own malformed output. `max_cycles: 1`, then
`continue_with_dissent`.

`default`'s single inherited evidence audit-resolution loop is retained along with the
rest of the chain and is pinned byte-identical by test.

Three failure classes route differently and must never be conflated:

| Class | Route |
|---|---|
| Parse / serialisation | existing `syntax_repair` role, unchanged |
| Structural (unknown key, duplicate, wrong cardinality) | discard → one clean regeneration → visible `audit_failed` → continue |
| Semantic (`revision_required`) | **data**; flows to revision; never a retry |

`tests/test_default_reviewed_v2.py` fails the build if a second review block, any
feedback binding, or `max_cycles > 1` is introduced.

## Identity and addressing

Python owns every identity. `audit.dx.*` responses are filed against the authority
Python supplied; `audit.ptbg.*` responses are addressed by `schema_id`, resolved
positionally to `(domain, bucket, index)`. There is no fuzzy matching, no nearest-string
resolution, and no recovery of a target from model prose. A malformed address is refused,
not guessed.

Python patches `reason` only, plus the mechanically-required clearing of
`evidence_card_tags` when a proposition is removed. It never rewrites a diagnosis,
prognosis direction, framework selection, or any other clinical conclusion.

A coherence finding with `scope: conclusion` — the model asserting that the *label* is
wrong rather than the derivation — is recorded and surfaced in the audit record. It is
**not** applied automatically. An overlay that silently re-routes a diagnosis on a
coherence judgement would be worse than one that raises it.

## Executor neutrality

Every added step uses only `generic_transform`, `generic_model` or `reasoning_model`,
which are workflow-agnostic primitives already implemented once in each of
`executors/provider.py` and `executors/self_executor.py`.

**No lines were added to `step.py` or `self.py`.** This is what keeps the provider and
self paths from diverging; there is no duplicated adapter code for them to drift in.
A test asserts neither executor mentions this overlay.

## Cost

| Added call | Count | Condition |
|---|---|---|
| `audit.dx.coherence` | 1 | always (all authorities in one call) |
| `audit.dx.revise` | 0–1 | only when a diagnosis reason needs correcting |
| `audit.ptbg.coherence` | 0–1 | only when evidence left something unsupported |
| `audit.ptbg.revise` | 0–1 | only when a PTBG reason needs rescoping |

Typical **+1 to +2** calls over `default`; worst case +4. Coherence calls carry no
corpus and no card text, so the token delta is small. Against `default_reviewed` — 32
model steps with up to two redo cycles each and cascade invalidation — the reduction is
large.

These are structural estimates. Run artefacts already persist per-call token use, cost,
retries and runtime; measure the real delta before tuning the PTBG gate.

## Known limitation: prognosis evidence-context split is annotation only

`default_reviewed_v2.evidence_context()` derives a routing label from `schema_id` alone
and distinguishes `prognosis_framework` from `prognosis_other`. That label is surfaced to
the PTBG coherence step and recorded in the audit record, so a statement that borrows
framework authority for a non-framework claim is visible to the auditor.

It is **not** used to narrow candidate card pools, and `_candidate_cards()` is unchanged.
Enforcing the split requires framework attribution on prognosis cards, which the accepted
corpus does not carry — cards expose only `card_id`, `locator`, `interpretation`, `genes`,
`diseases`, `disease_ancestors`, `category`, `evidence_tier`, `secondary_citation`.
Splitting the pool without that field would mean string-matching framework names against
card interpretations, which is exactly the semantic linkage this workflow forbids, and it
would silently drop correct cards whose interpretation phrases the framework differently.

**Prerequisite for enforcement:** add a `frameworks` array to prognosis cards at
ingestion. Once present, `_candidate_cards()` can filter on it deterministically and the
annotation becomes a real envelope restriction. Until then this is a live provenance
weakness in `default` as well as here, and it should be stated as such rather than papered
over.

## Also deferred

**Opaque per-call handles.** Replacing `E0001` / `[card:…]` in model context with random
per-call tokens was specified but is not implemented here. It touches the prompts and
validators of the *retained* three-stage chain and so carries the highest regression risk
of the planned changes, while every benefit above lands without it.

Note that the original proposal's remedy — local `A`/`B`/`C` selectors resolved
positionally — should not be adopted as-is. Today the echoed `evidence_id` is not a join
Python must resolve; it is a checksum Python asserts. Positional resolution plus a
cardinality check detects a dropped answer but not a permuted one, and three well-formed
reviews returned in the wrong order would pass every check while binding the wrong paper
to the wrong claim. If this is implemented, the acceptance test is that a deliberately
permuted response is *rejected*. Without that, the status quo is safer.

## Running it

```bash
python workflows/proforma_v1/step.py workflow-check --workflow workflow/default_reviewed_v2.yaml
python nel.py setup --mode nel-validate-dublin --case-id <id> --workflow default_reviewed_v2
python nel.py run --run-id <id>
```

The workflow path and SHA-256 are frozen into run state at setup; resume refuses a
workflow that changed underneath an incomplete run.
