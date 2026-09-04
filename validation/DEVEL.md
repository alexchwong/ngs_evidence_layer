# Validation development guide

Validation suites are repository-owned executable test specifications. A suite is registered by placing one canonical Markdown file in `validation/`; no Python mapping, workflow edit, UI edit, or registration step is required.

`validation/case_registry.py` is the single source of truth for validation-suite discovery, parsing, case retrieval, marking-criteria retrieval, and structural validation. Runtime code must not parse validation Markdown or hard-code validation suite filenames.

## Canonical validation Markdown format

Every registered validation file must use schema version 1 and exactly this structure:

```markdown
---
schema_version: 1
suite: nel-validate-example
title: Example validation suite
---

# Example validation suite

## Case 1 — Optional human-readable case title

### Case summary

Complete standalone clinical case supplied to the reporting workflow.

### Marking criteria

#### R1 — Diagnosis and classification

- **R1C1.** One independently testable reporting requirement.
- **R1C2.** Another independently testable reporting requirement.

#### R5 — Possible germline flagging

- **R5C1.** One independently testable germline-reporting requirement.
```

The front matter has exactly three keys:

- `schema_version`: currently `1`.
- `suite`: stable public mode matching `nel-validate` or `nel-validate-<suffix>` using lowercase letters, digits and hyphens.
- `title`: non-empty human-readable suite title; the single H1 heading must match it exactly.

Each case must:

- use a unique `## Case <id>` heading; an optional title follows ` — `;
- contain exactly one `### Case summary` followed by exactly one `### Marking criteria`;
- be fully standalone; shared stems, inherited case fragments, and cross-case references are prohibited;
- contain only information that the report-generation workflow is allowed to see in `Case summary`;
- contain no `NEL task`, `Trap`, `Differences from stem`, hidden answer, author note, or evaluator hint.

The only allowed marking-rubric headings are, in this order when present:

```text
#### R1 — Diagnosis and classification
#### R2 — Prognostic interpretation
#### R3 — Clinical actionability
#### R4 — MRD interpretation
#### R5 — Possible germline flagging
```

Omit a rubric entirely when it has no case-specific criteria. Do not add `No case-specific criteria` placeholders.

Criteria under each rubric must use sequential identifiers beginning at C1:

```markdown
- **R2C1.** ...
- **R2C2.** ...
```

The criterion identifier must match its rubric. Functional-test tags, weights, annotations, alternate identifier syntax, and free-form lines within the marking section are not part of schema version 1.

## Fair marking-scheme rules

Structural validity is necessary but not sufficient. A case is suitable for merge only when its marking scheme is fair.

Every criterion must be **atomic**. It must test one independently assessable clinical proposition or reporting obligation. Apply this test:

> If a report could satisfy one part while independently omitting or contradicting another part, split the criterion.

For example, this is compound and prohibited:

```markdown
- **R5C1.** Flag possible germline RUNX1, recommend constitutional confirmation, and recommend genetic counselling.
```

Write instead:

```markdown
- **R5C1.** Flag possible germline RUNX1 predisposition.
- **R5C2.** Recommend constitutional confirmation using an appropriate non-haematopoietic specimen.
- **R5C3.** Recommend genetic counselling.
```

Each criterion must also be:

- **observable**: assess something present or absent in the final report, not hidden model reasoning;
- **testable**: a marker can unambiguously judge it as met, omitted, or contradicted;
- **clinically material**: it represents information that belongs in a concise clinical NGS report, not merely something scientifically true;
- **available**: it can be supported from the supplied case and/or evidence available to the configured workflow;
- **achievable**: it does not require information absent from the case or permitted evidence;
- **non-duplicative**: the same proposition is not scored twice under different wording or rubrics;
- **wording-neutral**: equivalent clinically correct wording must satisfy it;
- **output-focused**: it must not require the model to "understand", "consider", or expose chain-of-thought reasoning.

Do not add defensive criteria solely for plausible model errors that are already handled as commission errors by the marking framework. Every case-specific criterion must test an intended clinical capability of that case.

Do not create criteria solely to reward repetition of supplied values. Do not score formatting, sentence order, verbosity, exact phrases, or stylistic preferences unless the validation suite explicitly tests a report-format contract.

Negative criteria are appropriate only when the absence or limitation itself is a clinically material reporting requirement. Do not create hidden "trap" criteria merely to punish an anticipated error; material false statements are already commission errors under the marking framework.

WHO-5 remains the primary classifier. Add an ICC criterion only where the ICC result is materially different for the supplied case. Apply the same principle to competing prognostic frameworks: require a framework only when clinically applicable and enough information is supplied for the requested conclusion.

Tumour-only sequencing must not be scored as establishing definitive germline status. Criteria may require a germline suspicion flag, appropriate correlation, genetic counselling, or constitutional confirmation when supported, but must distinguish those actions from proof of constitutional origin.

## Structural validation

Run from the repository root:

```bash
python validation/case_registry.py check
```

The check fails for malformed front matter, duplicate suite or case IDs, non-canonical case sections, unknown or out-of-order rubric headings, malformed or non-sequential RnCm identifiers, empty summaries, empty criteria, and legacy executable sections.

The registry deliberately does **not** pretend that punctuation or regex rules can prove semantic atomicity or clinical fairness. Those requirements are code-review responsibilities governed by the section above.

To inspect discovery or one resolved case:

```bash
python validation/case_registry.py list
python validation/case_registry.py get nel-validate-example 1
```

Evaluator-only criteria may be inspected explicitly during development:

```bash
python validation/case_registry.py get nel-validate-example 1 --criteria
```

Never expose that criteria output to a report-generation model before `report-final.md` is complete.

## Add a validation suite

1. Add one `.md` file directly under `validation/` using the canonical schema above.
2. Give the file a unique `suite` value; the filename itself has no runtime meaning.
3. Make every case summary standalone.
4. Review every marking criterion against the atomicity and fairness rules.
5. Run `python validation/case_registry.py check`.
6. Run the focused validation tests.

No Python registry edit, workflow metadata edit, UI edit, SKILL edit, or registration script is required. A valid dropped-in suite becomes discoverable by the proforma-v1 workflow, root `nel.py`, and UI through the registry.

## Modify an existing suite

Treat case text and marking criteria as benchmark behaviour. Preserve case IDs unless deliberately making a breaking benchmark change. When changing criteria, review whether the change alters the clinical expectation rather than merely making an existing expectation atomic.

Do not add backwards-compatible parsing for obsolete Markdown shapes. Migrate the asset to the current schema instead.

## Marking and leakage boundary

`validation/scripts/package_marking.py` remains the deterministic post-report packaging and marking-contract utility. It obtains cases and criteria through the central registry interface; it does not own case discovery or model/provider execution.

Before report completion, runtime code may retrieve only the selected case summary. Marking criteria are evaluator-only and must remain unavailable to report-generation prompts. `nel-demo` remains a separate bundled demonstration asset and is not part of the validation case registry.

Automatic validation marking is a post-report sidecar. Its validation-layer responsibilities are limited to rendering the canonical evaluator prompt, validating the R1-R5/RxCy response contract, binding results to the SHA-256 of `report-final.md`, persisting `marking.md`/`marking.json`, and deterministic Dublin `functional.json` translation. Provider and native-self execution belong to `workflows/proforma_v1/automatic_marking.py`.

Clinical completion and marking completion are independent. Marker failure does not invalidate `report-final.md`. A later `nel.py run` may retry failed or stale marking without regenerating the clinical report. Fresh retries must preserve prior `model_steps` attempt history rather than overwrite it.

For Dublin, the marking model evaluates RxCy only. F1-F9 are calculated deterministically from `validation/docs/dublin_functional_criteria.md`; do not duplicate that mapping in prompts, Python constants, or validation case metadata.

## Focused tests

Run:

```bash
python -m unittest tests.test_validation_cases tests.test_package_marking
python -m pytest tests/test_automatic_marking.py tests/test_automatic_marking_execution.py tests/test_automatic_marking_ui.py
```

The registry test suite must include a temporary arbitrary canonical Markdown suite and prove that discovery works without changing production mappings.
