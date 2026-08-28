# Proforma v1 developer notes

`workflow/default.yaml` is the canonical logical workflow. `step.py` and `self.py` are execution adapters over the same compiled definition; intentional executor differences must be declared in YAML. See `workflow/README.md` for workflow authoring.


## Workflow-specific unittest suite

Run this before and after changes to `proforma_v1`:

```bash
python -m unittest discover -s workflows/proforma_v1/tests -p "test_*.py"
python workflows/proforma_v1/step.py workflow-check
```

Custom workflow authoring and `--workflow` examples are documented in `workflow/README.md`.

## `workflow/default.yaml` term reference

This section is the developer-facing reference for every mapping term used by the
shipped `workflow/default.yaml`.  The compiler schema is authoritative for syntax;
these notes explain what each term means operationally.  When a new YAML key is
added to the default workflow, document it here in the same change.  A unit test
checks that coverage.

### Root structure and named registries

- `version` — workflow-file schema version. The shipped format is version 1.
- `workflow_id` — stable logical workflow identity written into run state and traces.
- `self_groups` — named native-self batching groups. Membership is declared by each
  step's `self_group`; the group does not create logical dependencies.
- `ptbg` — the shipped self-group name used by prognosis, treatment, biomarker and
  germline. It is also the PTBG model `role`/self handler name where shown below.
- `strategy` — batching strategy for a self group.
- `batch_ready` — batch every simultaneously runnable member of that self group;
  the compiler rejects members that depend on one another.
- `evidence_policies` — registry of evidence-policy prompt/role bundles.
- `literature_support` — ordinary reportable-claim evidence policy.
- `diagnosis_complete_support` — stricter WHO1 routing-change evidence policy.
- `assignment` — matcher configuration inside an evidence policy.
- `audit` — auditor configuration inside an evidence policy.
- `adjudication` — adjudicator configuration inside an evidence policy.
- `steps` — mapping of logical step IDs to step definitions.

### Shipped logical step IDs

- `structure` — structure the source case and establish source-case variant IDs.
- `corpus` — deterministic corpus/card preparation and card-identity manifest.
- `diagnosis.who1` — first WHO5 diagnosis proposal.
- `diagnosis.who1.routing_change` — deterministically assess whether WHO1 would
  materially change schema disease/diagnosis/routing CMCs.
- `diagnosis.who1.evidence.assignment` — blocking diagnostic evidence matching for
  a routing-changing WHO1 proposal.
- `diagnosis.who1.evidence.audit` — blocking audit of WHO1's positively assigned
  diagnostic cards.
- `diagnosis.who1.evidence.adjudication` — blocking, cropped adjudication of
  unresolved WHO1 evidence disagreements.
- `diagnosis.who1.commit` — commit the supported WHO1 routing state, or deterministic
  fallback when the routing-changing proposal is unsupported.
- `diagnosis.who2` — optional WHO5 reconsideration pass, gated by the Phase 3
  `reconsider_after_cmc_expansion` setting and routing state.
- `diagnosis.icc` — ICC diagnosis using the accepted WHO routing context.
- `diagnosis.other` — independent/concurrent-diagnosis model operation.
- `diagnosis.finalize` — deterministic final diagnosis/routing artifact assembly.
- `prognosis` — prognosis owner proforma plus initial owner evidence assignment.
- `treatment` — treatment owner proforma plus initial owner evidence assignment.
- `biomarker` — MRD/biomarker owner proforma plus initial owner evidence assignment.
- `germline` — germline owner proforma plus initial owner evidence assignment.
- `evidence.assignment` — canonicalise owner assignments and rescue still-uncarded
  facts with dedicated evidence matching.
- `evidence.audit` — audit only currently assigned cards; rejected cards may trigger
  rescue matching on the remaining candidate set.
- `evidence.adjudication` — deferred cropped adjudication of unresolved downstream
  fact/card disputes.
- `evidence.finalize` — deterministically accept/suppress evidence-backed reportable
  elements and emit evidence metrics/dissent.
- `report.blocks` — deterministic report-block construction.
- `report.write` — model rendering of deterministic blocks into report prose.
- `report.preservation` — provider-side semantic preservation audit of report prose;
  disabled for native-self execution by the YAML.
- `report.finalize` — deterministic final report assembly.

### Common step-definition terms

- `type` — logical operation class interpreted by the generic runner.
- `model` — a normal model-owned operation.
- `transform` — a deterministic allow-listed Python transform operation; when used
  as a value it selects this step type, and when used as a key it names the handler.
- `evidence_review` — matcher/auditor-style evidence operation.
- `evidence_adjudication` — adjudicator-style evidence operation.
- `render/report` — report-rendering operation class.
- `needs` — true logical/data dependencies. It is not a provider-call ordering hint.
- `role` — model role resolved through the selected pipeline.
- `stage` — declarative stage/proforma validation asset name.
- `prompt` — prompt asset path under the selected workflow asset root.
- `output` — declared output contract for a step.
- `artifact` — logical artifact name committed by the operation.
- `format` — structured model-output format where applicable.
- `json` — JSON structured output.
- `yaml` — YAML structured output.
- `schema` — JSON Schema asset used to validate structured output.
- `barrier_for` — declares logical operations whose deferred evidence disputes must
  be resolved at this barrier before later consumers can proceed.

### Inputs and binding terms

- `inputs` — named runtime values exposed to the step/prompt.
- `from` — bounded runtime source binding; no expressions or arbitrary code.
- `optional` — when true, absence of the bound input is allowed.
- `case_text` — input alias for the raw case text supplied to `structure`.
- `panel_scope` — input alias for the configured NGS panel-scope asset.
- `audit_feedback` — feedback alias exposed to rescue evidence matching after an
  audit-rejected assignment.
- `run.case_text` — built-in binding for the current run's raw case text.
- `assets.ngs_panel_scope` — built-in binding for the canonical setup copy of
  `config/ngs-panel-scope.md`.
- `feedback.evidence.audit` — persisted review feedback from the evidence audit.
- `artifacts.evidence_audits` — committed audit artifact used as feedback payload.
- `owner.cards` — immutable card envelope supplied to the owner/evidence operation.

### Checks and deterministic form validation

- `checks` — ordered generic runtime checks applied after schema parsing.
- `rule` — registered generic/custom check name.
- `sequential_ids` — require monotonically sequential source IDs; without an
  explicit width the shipped convention is unpadded (`V1`, `V2`, ...).
- `path` — artifact path selected by a check/verdict definition.
- `field` — field within each selected row used by a check.
- `prefix` — identifier prefix expected by `sequential_ids`.
- `variants` — structure-artifact row collection checked for sequential source IDs.
- `variant_id` — source-case variant ID field checked by the structure rule.
- `V` — shipped source-case variant-ID prefix.

### Execution-adapter terms

- `execution` — physical execution metadata; it must not redefine clinical ordering.
- `provider_handler` — allow-listed provider-side handler implementing the logical
  operation's physical mechanics.
- `self_handler` — allow-listed native-self handler implementing the same logical
  operation or a batching mechanism.
- `self_mode` — whether native self requires a host-model handoff or can complete
  deterministically.
- `handoff` — native-self step requires host-model output.
- `deterministic` — native-self step can execute without a model handoff.
- `self_group` — named `self_groups` membership for safe physical batching.
- `self` — executor-specific override block for native self.
- `enabled` — enable/disable this logical operation for that executor. The default
  workflow sets `report.preservation` to false for native self only.
- `provider` / handler names such as `domain`, `evidence_assignment`,
  `evidence_audit`, `evidence_adjudication`, `report_write`, `report_preservation`,
  `report_finalize`, `diagnosis_who1`, `diagnosis_who2`, `diagnosis_icc`,
  `diagnosis_other`, `diagnosis_finalize`, `who1_routing_change`,
  `who1_evidence_assignment`, `who1_evidence_audit`,
  `who1_evidence_adjudication`, `who1_commit`, `evidence_finalize`,
  `report_blocks`, `corpus`, and `structure` are allow-listed physical handler
  identifiers; changing them requires a corresponding registered implementation.

### Conditions and bounded review feedback

- `when` — condition block controlling whether a logical operation is required.
- `predicate` — allow-listed runtime boolean predicate name.
- `who1_routing_changed` — true when the WHO1 proposal materially changes routing;
  gates the blocking WHO1 evidence triplet.
- `who2_required` — true only when WHO2 reconsideration is enabled and required by
  the accepted routing/CMC state.
- `review` — bounded semantic feedback policy attached to an audit/review step.
- `target` — upstream logical operation to retry when the semantic review fails.
- `verdict` — definition of how the review result is classified.
- `evidence_audit_resolved` — predicate that passes when no evidence fact still
  requires rescue after processing the current audit.
- `on_pass` — action block when the review verdict passes.
- `continue` — continue normal workflow execution after a passing review.
- `on_fail` — action block when the review verdict fails.
- `retry_target` — invalidate/re-run the declared review target.
- `feedback` — payload passed into the retried target.
- `as` — input alias under which feedback is injected.
- `max_cycles` — finite bound on semantic target→review retry cycles.
- `exhausted` — action to take after `max_cycles` has been consumed.
- `action` — selected exhausted-policy action.
- `continue_with_dissent` — continue after recording unresolved evidence dissent;
  unsupported items remain subject to deterministic reportability policy.

### Evidence-policy and evidence-step terms

- `evidence` — per-step evidence ownership/timing configuration.
- `policy` — selected named entry from `evidence_policies`.
- `timing` — whether evidence resolution is a blocking dependency or may be deferred.
- `blocking` — evidence-approved state must be resolved before dependent routing.
- `deferred` — review/adjudication may be postponed until a declared safe barrier.
- `cards` — evidence-card source definition for this owner/review step.
- `match_passes` — number of matcher passes available to the WHO1 diagnostic gate;
  later passes run only for still-uncarded diagnostic facts.
- `owner_assignment` — when true, the owner PTBG proforma may make the initial card
  assignment from its own frozen envelope. Out-of-envelope tags reject that owner
  artifact and are fed back to the same PTBG step for repair.
- `rescue_match_passes` — number of dedicated downstream matcher passes available
  after owner assignment for still-uncarded or audit-rejected facts.
- `evidence_match` — matcher model role.
- `evidence_audit` — independent auditor model role.
- `evidence_adjudication` — independent adjudicator model role; the same spelling
  is also the evidence-adjudication step type, distinguished by context.
- `diagnosis` — model role used by WHO/ICC/concurrent-diagnosis operations.
- `ptbg` — model role used by prognosis/treatment/biomarker/germline operations.
- `report_write` — report-writer model role.
- `preservation_check` — report-preservation model role.

### Registered deterministic transforms used by the default workflow

- `load_corpus` — load/filter corpus cards and create the runtime card manifest.
- `assess_who1_routing_change` — compare WHO1 proposal with the pre-WHO1 routing
  state and write the deterministic routing-change artifact.
- `commit_who1_routing` — accept supported WHO1 routing or apply deterministic
  fallback without leaking rejected routing state downstream.
- `finalize_diagnosis` — assemble the authoritative diagnosis artifact.
- `finalize_evidence` — commit evidence outcomes, suppression/dissent and metrics.
- `report_blocks` — build deterministic report blocks from accepted clinical facts.
- `finalize_report` — assemble final report artifacts.

### Default artifact names

The following `artifact` values are stable logical names used by bindings/traces:
`structured_case`, `corpus_state`, `diagnosis_who1`, `who1_routing_change`,
`who1_evidence_assignments`, `who1_evidence_audits`,
`who1_evidence_adjudication`, `who1_commit`, `diagnosis_who2`, `diagnosis_icc`,
`diagnosis_other`, `diagnosis`, `prognosis`, `treatment`, `biomarker`, `germline`,
`evidence_assignments`, `evidence_audits`, `evidence_adjudication`,
`evidence_enriched`, `report_blocks`, `report_draft`, `report_preservation`, and
`final_report`. These names are workflow-facing identities; persisted filenames are
owned by the artifact/layout adapters.

## Core assets

- `step.py` — orchestration, evidence model calls, reportability, deterministic block assembly, dissent.
- `evidence_resolution.py` — pure shared policy for cumulative semantic evidence retries, rejected-card exclusion, and diagnosis/PTBG exhaustion behavior.
- `prognosis_report.py` — pure deterministic post-evidence prognosis aggregation. It groups same-framework/same-direction findings for report composition and suppresses only fully overlapping accepted-card restatements; it never changes the owner proforma or performs clinical inference.
- `model_context.py` — canonical downstream model context. Owns the rule that model prompts expose only `v01`-style IDs, and the per-stage projections that decide how much of the case/diagnosis each stage reads.
- `runtime.py` — case/setup validation and small deterministic helpers.
- `schema_validation.py` — accumulating validators for diagnosis, evidence and writer artifacts.
- `domain_contract.py` — the four PTBG proforma contracts: bucket vocabulary, model-facing skeleton, validator, and the pivot back to the stored bucket-list artifact.
- `issues.py` — shared `ValidationIssue` builders, so identical defects read identically whichever stage found them.
- `stage_checks.py` — stage registry backing `check-stage`, `show-prompt` and the fixture tests.
- `stages/*.yaml` — declarative stage assets: prompt, inputs, output schema, buckets, rules, transforms, retries, reportability.
- `schemas/*.json` — real JSON Schema (Draft 2020-12) for each artifact's structure.
- `stage_spec.py` — loads and validates stage assets against `stages/_stage.schema.json`.
- `schema_engine.py` — maps `jsonschema` errors onto `ValidationIssue`.
- `rules.py` — the named relational rules a stage asset may reference.
- `stage_validation.py` — schema + rules, ordered by document position.
- `settings.json.template` — canonical default retry, authority, retrieval, reportability, and model-facing card-rendering policy. `evidence_resolution_attempts` counts semantic match→audit attempts and is separate from per-model syntax/content retries.
- `prompts/` — only active model tasks. There are no statement-generation, summary-plan, or paraphrase prompts.
- `pipelines/` — canonical shipped model/provider defaults for self, LM Studio, and OpenRouter. Pipeline identity is the YAML filename stem; `pipeline.id` is intentionally absent.
- `devel_sync.py` — validates proforma-v1 local settings/pipeline defaults. It intentionally refuses to write root `config/` while `terraced-v6` remains the promoted default workflow.

Clinical interpretation belongs to the owner call. Downstream code must not re-diagnose or repair owner clinical reasoning.
Prognosis report aggregation is therefore deliberately downstream of evidence resolution: it may compress surviving supported propositions, but it must not create a new effect, framework, direction, disease scope, or evidence relationship.

## Validate workflow-local defaults

`proforma_v1` is not yet the promoted root workflow. Root `config/` therefore remains owned by `terraced-v6`; changes to proforma-v1 settings or pipeline defaults must remain under `workflows/proforma_v1/`.

Validate the workflow-local defaults with:

```bash
python workflows/proforma_v1/devel_sync.py --check
```

Running `devel_sync.py` without `--check` deliberately refuses to modify root `config/`. Root defaults should be changed only as part of an explicit workflow-promotion decision.


## Model-facing card rendering

Every prompt that shows evidence cards must call `rendering.render_prompt_cards()` or its diagnosis-specific boundary, `rendering.render_diagnostic_prompt_cards()`. Compact mode is the default and groups `source_hint -> category -> diseases`, with exactly one card per line. The model sees only `[card:<12-hex-tag>]`; canonical corpus `card_id` values remain internal/persisted provenance. Evidence matching therefore returns `card_tag`, which Python resolves back to the canonical ID before audit and report construction. Diagnosis retrieval is `diagnosis AND (CMC OR gene)` plus the framework authority filter. WHO5/ICC authority filtering retains `included_publication_keys` (or all retrieved publications when that list is empty) and then removes `excluded_publication_keys`, so exclusion always wins. Prompt rendering, finite-membership context, and Stage 8 must reuse that resolved pool; Stage 8 must not apply a second diagnosis gene filter.

## Model-facing identifier rule

`structure_case` produces source-case IDs (`V1`, `V2`, ...). `stage_structure`
maps them to canonical workflow IDs (`v01`, `v02`, ...) in
`intermediates/variant_registry/variants.yaml`, which keeps `variant_id` for
provenance.

**No model prompt may contain a source-case ID.** The deterministic validators
accept canonical IDs only, so exposing both namespaces asks the model to choose
between two names for the same object and makes correct validation feedback look
arbitrary. Build model-facing blocks with `model_context.registry_context()`,
`model_context.case_context()` and `model_context.diagnosis_context()` rather
than dumping an artifact, and assert the invariant at each prompt site:

```python
model_context.assert_canonical(prompt, source_ids=model_context.source_ids(reg))
```

## Per-stage projections

`model_context` defines what each stage family reads. Widening a projection is a
one-line change to the tuples at the top of that module:

- `DIAGNOSIS_CASE_FIELDS` — case fields sent to WHO5/ICC/second-diagnosis.
- `DOMAIN_CASE_FIELDS` — case fields sent to the four PTBG proformas.
- `DOMAIN_DIAGNOSIS_FIELDS` — diagnosis fields sent to the PTBG proformas.
  Currently excludes the free-text `reason` paragraphs: a domain stage needs to
  know what the disease was called, not the argument for it.

`case_projection()` never emits `variants`; variant identity always comes from
the canonical registry block instead.

`structure_case` also records `ngs_result_completeness`. The model always leaves
`ngs_no_variants_detected` empty; core deterministically materializes that list
from `config/ngs-panel-scope.md` minus the detected variant genes when the result
is complete. Diagnosis and PTBG projections expose both fields. The negative list
is assay-scope evidence only, not whole-gene biological wild type and not evidence
against copy-number, rearrangement, structural, or other unassayed variant classes.

## Validation feedback

Validators accumulate: they collect every deterministic defect and raise once, so
one repair turn carries the complete list. Build issues with `issues.py` rather
than by hand — that is what keeps the wording consistent between stages.

Two rules matter more than they look:

- **Never enumerate a large closed vocabulary back to the model.** `issues.enum_field`
  lists the allowed set only when it is short; above `MAX_LISTED_ENUM_VALUES` it
  reports the nearest legal values to what the model actually said. The WHO5
  schema-disease vocabulary is ~160 entries, and dumping it cost more tokens than
  the artifact under repair while burying the one useful fact.
- **Cap the list.** `render_issues` shows at most `MAX_RENDERED_ISSUES` and says how
  many were withheld. A model asked to fix forty defects fixes a prefix.

## Testing a stage on its own

Every validated stage is registered in `stage_checks.py` and has fixtures under
`tests/fixtures/<stage>/`:

```text
tests/fixtures/prognosis/
├── context.yaml                              runtime state the validator needs
├── valid.yaml                                must pass
├── invalid_missing_variant.yaml              must fail
└── invalid_missing_variant.yaml.expected.txt exact feedback the model receives
```

The fixture test asserts that feedback character-for-character, which makes the
model-facing wording a reviewed artifact rather than an accident of how someone
phrased a `ValueError`. Adding a stage means adding a directory; no test code
changes. To re-record after a deliberate wording change, delete the
`.expected.txt` files and re-run the capture snippet in `NEWS`-style commit notes.

No model, corpus or run directory is needed:

```bash
python workflows/proforma_v1/step.py stages
python workflows/proforma_v1/step.py check-stage --stage prognosis --file candidate.yaml
python workflows/proforma_v1/step.py show-prompt --stage prognosis
```

`check-stage` exits non-zero and prints exactly what the model would be told.

## PTBG proforma contract

Owner outputs are variant-centric. Python owns deterministic identity: the authoritative WHO5 disease is injected into prognosis/treatment/MRD and canonical `gene` is injected from each `variant` ID before validation/persistence. Clinical classifications remain model decisions.

Prognosis may identify zero, one, or multiple frameworks:

```yaml
applicable_disease: CMML
prognostic_frameworks:
  - name: CPSS-Mol
    tier: null
    reason: "CPSS-Mol is the relevant CMML prognostic framework."
classification:
  - variant: v01
    gene: ASXL1
    framework_effects:
      - framework: CPSS-Mol
        effect: adverse
        reason: "ASXL1 has an adverse effect within CPSS-Mol."
    other_evidence_effect: adverse
    other_evidence_reason: "Independent CMML evidence also supports an adverse effect."
```

Framework selection is not hard-coded. `tier` is populated only when the model can assign that framework entirely from supplied genetic/cytogenetic findings. Other prognostic evidence may classify genes outside the framework, but it must apply to the authoritative disease.

Treatment keeps one-or-more rows per variant but names the category `treatment_category`; MRD uses `mrd_status`; germline retains `bucket`. `domain_contract.pivot()` projects these accepted owner artifacts into bucketed internal rows for consolidation/reportability/evidence resolution.

PTBG owner passes may assign initial evidence from their frozen card envelope. The dedicated evidence matcher is a rescue operation for still-uncarded or audit-rejected facts, and each rescue item is rendered with only its own deterministic candidate-card set. Audit sees only positively assigned cards. This preserves WHO5/ICC authority filtering and PTBG disease/gene cropping at the model boundary while preventing cross-fact card leakage.

## Retry hygiene

`step._apply_stagnation` fingerprints each rejected artifact and its feedback in
the retry entry that already survives self handoffs. An identical repeat appends
an escalation instruction; a second identical repeat stops the stage rather than
spending the remaining budget on an unchanged retry.

Every deterministic change to an accepted model artifact is recorded in
`logs/transforms.yaml`, so a developer can always tell model output from Python
normalisation.

## Declarative stage assets

**The selected workflow YAML declares logical ordering, dependencies, conditions and execution metadata. Python implements only generic execution mechanisms and allow-listed deterministic extensions.**

Stage composition is repetitive and gets customised, so it lives in
`stages/<stage>.yaml`. Logical ordering, dependencies, conditions, bounded review
routing, evidence barriers and executor metadata live in the selected
`workflow/*.yaml`; neither `step.py` nor `self.py` owns a second clinical sequence.
The workflow vocabulary remains deliberately bounded: complex clinical conditions
or transforms are calculated by allow-listed deterministic Python handlers and then
referenced by name rather than expressed as arbitrary YAML code.

`stages/_stage.schema.json` validates the assets themselves, and every `type`,
`rule` and `transform` name must resolve against a registry at load time, so a
typo fails at `step.py stages` rather than at model-call time.

Adding a PTBG domain requires no Python: one `stages/<name>.yaml`, one
`prompts/<name>.md`, one fixture directory, one entry in the stage sequence.
A test proves this by driving a fictional domain end to end.

Structure is expressed in real JSON Schema. `jsonschema>=4.0` is already a
dependency; do not hand-roll `$ref`/`oneOf` resolution. But never surface
`jsonschema`'s own messages — they are written for developers and, for `enum`,
embed the whole vocabulary. `schema_engine` maps every error onto an `issues.py`
builder instead.

## The shared runner

Retry, repair, budgets and suspension live in
`scripts/core/validated_model_task.run()`. `step.py` only binds this workflow's
prompts, paths and provider bindings to it via `TaskIO`.

Three behaviours are load-bearing and must survive any future change:

1. **Suspension.** On the `self` pipeline a model call does not return — the
   process exits and a later invocation resumes. All loop state is in
   `load_state`/`save_state`; the runner raises `Suspend`, which `step.py`
   translates to `Handoff`.
2. **Nested budgets.** A serialization budget sits inside a rewrite budget, with
   two restart modes: `fresh` (regenerate from the original task) and `repair`
   (replay the artifact with feedback).
3. **Serialization/content routing.** Issues classed `serialization` go to the
   syntax model; only content issues return to the originating task.

`tests/test_runner.py` pins all three. Test 8 drives a three-invocation
self-handoff, which is the only test that reaches the process boundary where
resume bugs actually appear. Run it before trusting any change to the runner.

## Syntax repair and the preservation check

Two deterministic behaviours were blocking run completion and are now fixed:

- `deterministic_cleanup` extracts a fenced block from surrounding prose, and
  trims non-structural leading/trailing lines. Previously a fence was only
  stripped when it wrapped the entire response, so the common
  "Here is the YAML: ```...``` Let me know" shape stayed unparsable.
- `preservation_error` allows *removal* of non-protected lexemes by default.
  A correct repair that strips conversational prose used to be rejected as
  content loss, so the budget burned out rejecting good answers. Additions and
  changes are still hard failures, and every protected token — IDs, numbers,
  percentages, card tags — must still survive, so dropping a real value is
  still caught. Pass `allow_prose_removal=False` for a strict comparison.
