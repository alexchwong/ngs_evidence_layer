# `default_reviewed_v2` — bounded clinical-owner correction

`default_reviewed_v2.yaml` is a clone of **`default.yaml`**, not of `default_reviewed.yaml`.
Every clinical owner keeps its role, stage, schema, handlers and evidence policy; the
three-stage evidence chain and the report pipeline are carried over unchanged. What the
overlay adds is an immediate reasoning audit for each clinical owner and a bounded route
back to that same owner when the audit finds a defect.

```text
structure → corpus
diagnosis.who1  → audit.who1.{packet,coherence,gate} → [owner correction ×2] ┐
  → diagnosis.who1.routing_change → who1 evidence chain → who1.commit        │
diagnosis.who2  → audit.who2.{packet,coherence,gate} → [owner correction ×2] │
diagnosis.icc   → audit.icc.{packet,coherence,gate}  → [owner correction ×2] │
  → audit.diagnosis.terminal → diagnosis.finalize → audit.diagnosis.provenance
prognosis / treatment / biomarker / germline
  each → audit.<domain>.{packet,coherence,gate} → [owner correction ×2]
  → audit.ptbg.terminal
evidence.assignment → audit → adjudication → finalize   (unchanged)
report.blocks → write → preservation → finalize          (unchanged)
```

## The failure this exists to catch

```text
conclusion: MDS with biallelic TP53 inactivation
patient_findings: one TP53 variant; FISH negative for 17p; no cnLOH detected
stated_reason: no evidence of wild-type allele retention, so biallelic is satisfied
```

Every clause is individually citable, so evidence review returns `supported`. The defect
is that the derivation refutes its own label, and no amount of evidence machinery can see
it. The diagnosis coherence audit is therefore **unconditional**: gating it on evidence
verdicts would drop precisely the case it exists for.

## Ownership

> Clinical conclusions and the reasoning that supports them belong to the clinical owner
> that produced them. Deterministic Python routes, validates structure, preserves
> provenance and enforces retry limits. It does not make or substitute clinical decisions.

This has three concrete consequences.

**Any clinical reasoning defect goes back to the owner.** The overlay contains no generic
reason-rewriter. Earlier designs split defects into "reason wrong but conclusion safe →
generic rewrite" and "conclusion wrong → owner retry"; that split is unsound, because only
the clinical decision-maker can tell whether a conclusion still stands once one of its
reasons has been shown to be wrong. Serialisation and schema repair remain deterministic
and are isolated behind the existing `syntax_repair` role with its own budget.

**The correcting owner performs the whole task again.** It receives its normal proforma,
the original structured case, the same cards and context, its own previous output, and the
plain-English `correction_brief`. It is told not to repeat the identified error and not to
rewrite wording while leaving the conclusion standing. It is not told what to conclude.

**The auditor's verdict never reaches the owner.** `conclusion_supported` and
`reason_defective` are routing fields; they are written to the audit side record, and the
review's `feedback.path` sends only `correction`. Telling an owner that a reviewer rejected
its conclusion is functionally an instruction to change it, which is the anchoring failure
the design is trying to avoid.

## The audit contract

The former `scope: reason | conclusion` enum forced a choice between two compound claims —
"the conclusion is right AND the derivation is wrong" versus its converse. An assessment
whose conclusion and derivation are *both* defective had no truthful value available. In
the case above the auditor correctly detected the problem, was forced to pick `reason`, and
the wrong label survived a "successful" repair. Two independent judgements remove the
choice:

```yaml
conclusion_supported: false
reason_defective: true
correction_brief: >
  The reasoning treats the absence of 17p deletion and copy-neutral loss of
  heterozygosity as evidence that the wild-type allele has been lost...
```

Either judgement being defective routes to the owner. A defect reported without a brief, or
a malformed verdict, is `audit_failed`: it is surfaced, and the owner is not disturbed on
the strength of an unreadable review.

## Audit placement

Each audit sits immediately after the owner it audits and before anything consumes that
owner's result. `test_no_step_consumes_an_owner_before_its_gate` enforces this. The point
is cost: in the original layout the diagnosis audit ran after the WHO1 evidence gate and
ICC had already committed, so a WHO1 correction would have invalidated roughly eleven
downstream model calls. Auditing locally means a correction invalidates nothing, and a
large generic dependency-invalidation engine is unnecessary.

Relocating the PTBG audits costs something real and this is stated rather than papered
over. The previous PTBG audit was *gated* on downstream evidence verdicts, which no longer
exist when the audit runs, so the four domain audits are now unconditional and cannot see
which propositions ended without card support. That signal belongs to the evidence chain,
which still runs; the PTBG audit instead checks each proposition against the patient
findings and the authoritative diagnosis — the check nothing else performs, and the one
that catches a prognosis statement asserting an allelic state the case excludes.

## Bounded correction

```text
maximum owner invocations per clinical object = 3   (original + 2 corrections)
maximum coherence assessments per object      = 3
```

The bound is the runner's `review.on_fail.max_cycles`, whose counter is keyed on the
reviewing step id and persisted in control state. It is deliberately **not** keyed on the
emitted conclusion: a correction that changes the diagnosis must consume the same budget,
or the bound silently disappears. There is no correction retry 3, and a correction step can
never itself become a correction target — `test_a_correction_step_is_never_itself_a_correction_target`
fails the build if one does.

The re-run audit *is* the verification step. When an owner is corrected the runner
invalidates its descendants, so the packet and coherence call re-run against the new output.
No separate verification step exists, and none is needed.

The old `at most one added review block` assertion has been replaced. It encoded an
implementation choice rather than the property that matters, and it would have forbidden
this architecture. The replacements assert bounded owner invocation, exactly one added
review per owner, no recursive correction chains, and that `default`'s single inherited
evidence audit-resolution loop is retained byte-identical.

## Terminal policy

After three owner attempts a configured policy applies, read from
`config/settings.json` and frozen into run provenance:

```json
"reviewed_v2_terminal_policy": {
  "diagnosis": "withhold_affected_output",
  "ptbg": "withhold_affected_output",
  "surface_dissent": true,
  "fail_run_on_unresolved": false
}
```

An unsupported or misspelled value fails configuration validation rather than silently
falling back, because the setting governs what reaches a clinical report.

For **PTBG**, `withhold_affected_output` clears the affected domain's propositions before
the evidence chain consumes them, so a disputed claim is never treated downstream as
accepted clinical truth.

For **diagnosis** the same word must mean something different, and this is the one place
the overlay touches a clinical conclusion. WHO5 routing selects the candidate card pool for
ICC and every PTBG owner, so an absent diagnosis leaves nothing to route on and the run
cannot continue. `withhold_affected_output` therefore withholds the *unverified
re-classification*: the supplied morphologic diagnosis is restored, `diagnostic_effect`
becomes `unchanged`, and the withheld label is recorded. That is a refusal to apply a change
the owner proposed and could not defend, not a selection of a different diagnosis — the
state the run would have been in had the owner proposed nothing. It happens only after three
attempts, only under explicit configuration, and always with dissent raised. `fail_run` and
`issue_with_dissent` remain available for sites that prefer stopping or shipping the dispute.

## Dissent

Unresolved findings reach the canonical ledger, not an intermediate file. The ledger moved
out of `step.py` into `engine/dissent.py` for exactly this reason: the previous overlay
wrote its unresolved findings to `audit_v2/dx-audit-commit.yaml`, which nothing human-facing
ever read. `step.py` now delegates to the shared ledger and registers its `dissent.md`
renderer through a hook, so an overlay can raise dissent without importing an executor.

## Provenance

`audit.diagnosis.provenance` runs between `diagnosis.finalize` and the PTBG owners and
proves, deterministically, that the finalized diagnosis is the latest accepted owner
artifact. It records the routing source, both artifact digests, and whether a terminal
policy was invoked. This is identity checking only; it makes no judgement about whether the
conclusion is clinically correct.

It exists because a stale snapshot silently discarded a successful repair. `finalize_diagnosis`
preferred the `accepted_who1` snapshot frozen at the WHO1 routing gate over the live WHO
artifact, so anything that legitimately amended the artifact afterwards vanished. Fixing
the precedence alone would not prevent the next bug of that class.

## Deterministic input fixes

Three defects meant the audit was judging conclusions against a case it could not see.

`_patient_findings` read a `fact` key from structured case facts, which are stored under
`value`, so every morphology, cytogenetic, FISH, LOH and blast finding was silently
dropped. It also appended "No reportable variants were detected on the assayed panel"
whenever `ngs_no_variants_detected` was non-empty — that key is the list of genes *without*
a variant, not a null result, so the sentence flatly contradicted any variant listed above
it. Both are fixed and regression-tested.

The variant registry discarded `event_type` and `vaf` at construction, which also made
`model_context.GERMLINE_REGISTRY_FIELDS` unsatisfiable. The registry now carries what
`structure_case` captured, and `DIAGNOSIS_REGISTRY_FIELDS` exposes VAF to WHO and ICC owners,
which is what makes the multi-hit TP53 VAF criterion usable at all.

## Cost

| Added call | Count | Condition |
|---|---|---|
| owner coherence audit | 6 | always, one per clinical owner |
| owner correction | 0–2 per owner | only when that owner's audit reports a defect |

Baseline goes from one diagnosis coherence call (plus an occasional PTBG one) to six
always-on audits. Coherence calls carry no corpus and no card text, so the token delta is
small, but the call delta is real and intentional: more small local audits, fewer expensive
downstream cascades, and errors attributable to the owner that made them. Against
`default_reviewed` — 32 model steps with up to two redo cycles each and cascade
invalidation — this remains far cheaper.

**These are structural estimates.** Run artefacts persist per-call token use, cost, retries
and runtime. Measure the real delta on the validation set before tuning anything, and
inspect cases where the auditor disagrees with a correct owner: false-positive corrections
are the main risk this design carries and they cannot be estimated from the workflow shape.

## Known limitation: prognosis evidence-context split is annotation only

`evidence_context()` derives a routing label from `schema_id` alone and distinguishes
`prognosis_framework` from `prognosis_other`. It is recorded in the audit record but is
**not** used to narrow candidate card pools. Enforcing the split requires framework
attribution on prognosis cards, which the accepted corpus does not carry — cards expose only
`card_id`, `locator`, `interpretation`, `genes`, `diseases`, `disease_ancestors`, `category`,
`evidence_tier`, `secondary_citation`. Splitting the pool without that field would mean
string-matching framework names against card interpretations, which is exactly the semantic
linkage this workflow forbids.

**Prerequisite for enforcement:** add a `frameworks` array to prognosis cards at ingestion.
Until then this is a live provenance weakness in `default` as well as here.

## Also deferred

**Opaque per-call handles.** Replacing `E0001` / `[card:…]` in model context with random
per-call tokens is not implemented. It touches the prompts and validators of the retained
three-stage chain and carries the highest regression risk of the planned changes.

The original proposal's remedy — local `A`/`B`/`C` selectors resolved positionally — should
not be adopted as-is. Today the echoed `evidence_id` is not a join Python must resolve; it is
a checksum Python asserts. Positional resolution plus a cardinality check detects a dropped
answer but not a permuted one, and three well-formed reviews returned in the wrong order
would pass every check while binding the wrong paper to the wrong claim. If this is
implemented, the acceptance test is that a deliberately permuted response is *rejected*.

**Owner reason formatting.** `_reasons()` splits on explicit line breaks only, so an owner
that writes several claims in one sentence yields a single-element `stated_reasons` list —
which is what happened in the case above, and it is why the worked example in the old prompt
described a shape that could not occur. Deterministic sentence-level atomisation is the wrong
fix. The safer change is a one-line owner-prompt instruction to put each distinct clinical
claim on its own line. Optional, not a prerequisite.

## Running it

```bash
python workflows/proforma_v1/step.py workflow-check --workflow workflow/default_reviewed_v2.yaml
python nel.py setup --mode nel-validate-dublin --case-id <id> --workflow default_reviewed_v2
python nel.py run --run-id <id>
```

The workflow path and SHA-256 are frozen into run state at setup; resume refuses a workflow
that changed underneath an incomplete run.
