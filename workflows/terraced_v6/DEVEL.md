# Terraced v6 developer notes

V6 is intentionally smaller than v5.

## Core assets

- `step.py` — orchestration, evidence model calls, reportability, deterministic block assembly, dissent.
- `evidence_resolution.py` — pure shared policy for cumulative semantic evidence retries, rejected-card exclusion, and diagnosis/PTBG exhaustion behavior.
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
- `settings.json.template` — retry, authority, retrieval, and reportability policy. `evidence_resolution_attempts` counts semantic match→audit attempts and is separate from per-model syntax/content retries.
- `prompts/` — only active model tasks. There are no statement-generation, summary-plan, or paraphrase prompts.
- `pipelines/` — model bindings for self, LM Studio, and OpenRouter.

Clinical interpretation belongs to the owner call. Downstream code must not re-diagnose or repair owner clinical reasoning.

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
python workflows/terraced_v6/step.py stages
python workflows/terraced_v6/step.py check-stage --stage prognosis --file candidate.yaml
python workflows/terraced_v6/step.py show-prompt --stage prognosis
```

`check-stage` exits non-zero and prints exactly what the model would be told.

## PTBG proforma contract

The owner model returns one row per variant:

```yaml
classification:
  - variant: v01
    bucket: adverse
    reason: "..."
```

It is handed that list with every `variant` pre-filled, as the **final** block of
the prompt. Coverage and exclusivity defects are then unrepresentable, and the
structural check is `one_row_per_id` — the same rule the batch and writer stages
already use.

Grouping variants that share a proposition is Python's job
(`step._consolidate_rows`), not the model's; it always was, the model's grouping
was simply being redone. `domain_contract.pivot()` converts the flat list back to
the bucket-list artifact before anything is written, so evidence selection,
reportability and block assembly are unchanged.

Bucket names are defined once, in `domain_contract.CONTRACTS`. Validators,
consolidation, element assembly and the reportability defaults all read them.

## Retry hygiene

`step._apply_stagnation` fingerprints each rejected artifact and its feedback in
the retry entry that already survives self handoffs. An identical repeat appends
an escalation instruction; a second identical repeat stops the stage rather than
spending the remaining budget on an unchanged retry.

Every deterministic change to an accepted model artifact is recorded in
`logs/transforms.yaml`, so a developer can always tell model output from Python
normalisation.

## Declarative stage assets

**YAML declares what a stage is made of. Python declares the order stages run in.**

Stage composition is repetitive and gets customised, so it lives in
`stages/<stage>.yaml`. The clinical stage sequence is a fixed dependency chain
read far more often than edited, so it stays as an ordered list in `step.py`.
A YAML vocabulary that can express control flow stops being configuration and
becomes a language with no debugger — `workflows/terraced_v3/` is this
repository's own record of that experiment.

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
