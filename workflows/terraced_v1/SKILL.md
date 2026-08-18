---
name: ngs-evidence-layer-terraced-v1
description: Progressive terraced-question workflow with delayed evidence alignment and single-pass final synthesis.
---
# NGS evidence layer — terraced-v1

## Scope

Supported modes:

- `ngs-report`
- `nel-demo example <N>`
- `nel-validate <case-id>`
- `nel-validate-function <case-id>`

This workflow uses the CLI as the authoritative orchestrator. The master clinical questions and their call-grouping profiles live together in `workflows/terraced_v1/questions.yaml`.

A terrace is one ordered reporting question. Later terraces reconsider the complete current category state and may revise earlier conclusions. The number of terraces is not fixed. Execution profiles only change how consecutive questions are grouped into calls; they do not change the clinical question sequence.

The clinical pipeline is:

0. setup;
1. capture and structure the case, allowing one or more provisional CMCs;
2. retrieve broad diagnosis plus gene-matched germline evidence;
3. run terraced diagnosis, allowing additional CMCs/evidence to be introduced, and finish with one or more accepted WHO5 diagnoses;
4. independently review the diagnosis at a high semantic threshold, then align each fact/reason pair to directly supporting cards where available;
5. for prognosis, treatment, MRD and germline in order: retrieve evidence by the accepted narrow WHO5 routing diagnosis(es), run the configured terraces, review, and align evidence;
6. strip reasons/citations, perform one facts-only report synthesis, then semantically map each final sentence back to accepted facts to inherit citations and render deterministically;
7. use the existing delivery/validation packaging behaviour.

## Global model/file rules

File access is deny-by-default. The CLI packages every permitted model input into `<work-dir>/.model-steps/<operation>/prompt.md`.

For the frontier/session-model execution path, use model profile `self`. When a command exits `10`, read only the printed `PROMPT=<path>` bundle, perform that model operation in the current session, write only the printed `OUTPUT=<path>`, then rerun the same workflow step. Do not inspect repository Python to infer missing inputs.

Direct CLI execution may instead use an explicit delegating model profile (`lmstudio`, `ollama`, or `openrouter`). The CLI then sends the same packaged conversation through the workflow's OpenAI-compatible client. Provider/model IDs remain configuration, not clinical workflow logic.

Within each terraced category, the CLI reconstructs a canonical conversation as:

```text
[case + current permitted cards + accepted upstream state]
Q/group 1 : A1
Q/group 2 : A2
...
```

The transcript is persisted in `conversation-<category>.json`. Provider-side hidden session state is not authoritative.

Clinical answering artifacts use only `fact` + `reason`. Citation selection is delayed until category completion. `citation: null` is valid where no card directly supports the stated reason and does not itself cause a repair loop.

WHO5 is authoritative for the accepted diagnosis and downstream routing. ICC may inform reasoning but must not replace the final WHO5 state. The ICC-only `MDS/AML` value is deterministically rejected as a final `schema_disease` routing diagnosis.

Concurrent pathology is first-class: diagnosis state may contain multiple accepted diagnoses. Downstream evidence is retrieved against each accepted narrow `schema_disease` rather than pooling generic CMC evidence. This prevents, for example, APL from inheriting undifferentiated AML treatment cards or CML from inheriting generic MPN treatment cards.

## Step 0 — Setup

At Step 0 only, prepare the repository-local environment:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Set `<python>` to `.env/bin/python`.

Choose `<setup-work-arg>` once:

- supplied directory: `--work-dir <supplied-directory>`;
- exact `->project` modifier: `--project`;
- otherwise empty.

Use the frontier/session-model defaults unless the user explicitly requested a direct-provider profile:

```bash
# ngs-report
<python> workflows/terraced_v1/step.py setup --mode ngs-report \
  --model-profile self --terrace-profile frontier <setup-work-arg>

# nel-demo example <N>
<python> workflows/terraced_v1/step.py setup --mode nel-demo --example <N> \
  --model-profile self --terrace-profile frontier <setup-work-arg>

# nel-validate <case-id>
<python> workflows/terraced_v1/step.py setup --mode nel-validate --case-id <case-id> \
  --model-profile self --terrace-profile frontier <setup-work-arg>

# nel-validate-function <case-id>
<python> workflows/terraced_v1/step.py setup --mode nel-validate-function --case-id <case-id> \
  --model-profile self --terrace-profile frontier <setup-work-arg>
```

Record output line 1 as `<work-dir>`. For `nel-demo`, record output lines 2 and 3 as the demo case and expected-behaviour paths; do not read them until delivery.

For interactive `ngs-report` under the frontier/session-model harness, write the user-supplied case source from the current request verbatim to `<work-dir>/case-source.md` before Step 1A. This is the only non-CLI source-ingest action: the subsequent capture prompt, model handoffs, validation, retrieval, reasoning, alignment, synthesis and packaging are all CLI-orchestrated. For direct CLI execution, supply the case with `setup --case-file <path>` instead.

Alternative terrace grouping profiles are `balanced` and `deliberate`. Direct-provider model profiles are `lmstudio`, `ollama`, and `openrouter` and can be selected at setup with `--model-profile`.

## Model-handoff procedure

For any Step 1, 3, 4, 5, or 6 command that exits `10`:

1. read only the printed `PROMPT=<path>`;
2. perform that bounded operation in the current session;
3. write only the exact `OUTPUT=<path>` artifact requested by the bundle;
4. rerun the same step command;
5. repeat until the command exits `0`.

A deterministic structural validator may return the same operation for repair. Fix the stated structural defect without changing unrelated clinical content.

## Step 1 — Capture and structure case

For validation modes, setup already writes `case.md`; skip Step 1A.

Otherwise run Step 1A until exit `0`:

```bash
<python> workflows/terraced_v1/step.py 1a --work-dir <work-dir>
```

Then run Step 1B until exit `0`:

```bash
<python> workflows/terraced_v1/step.py 1b --work-dir <work-dir>
```

`case-input.json` contains provisional plural CMCs, the supplied provisional disease wording, detected genes and preserved case facts. These CMCs are retrieval scaffolding only.

## Step 2 — Broad diagnostic evidence

Run once:

```bash
<python> workflows/terraced_v1/step.py 2 --work-dir <work-dir>
```

This retrieves diagnosis cards matching any provisional CMC or detected gene, plus gene-matched germline cards, and writes `evidence-diagnosis.{json,md}`.

## Step 3 — Terraced diagnosis

Run until exit `0`:

```bash
<python> workflows/terraced_v1/step.py 3 --work-dir <work-dir>
```

Diagnosis begins with the mandatory leading-diagnosis and differential/concurrent-pathology questions from the master config. If a terrace adds a credible CMC, the CLI expands diagnostic retrieval before the next group while preserving prior conversation answers.

The final diagnostic state must contain one or more accepted WHO5 diagnoses:

```yaml
diagnoses:
  - schema_disease: CML
    narrow_diagnosis: CML, BCR::ABL1-positive
facts:
  - fact: "..."
    reason: "..."
```

Multiple diagnoses are allowed for supported concurrent pathology.

## Step 4 — Diagnosis review and evidence alignment

Run until exit `0`:

```bash
<python> workflows/terraced_v1/step.py 4 --work-dir <work-dir>
```

A fresh semantic reviewer uses a deliberately high threshold: only material contradictions, wrong disease/framework application, unmet premises or major evidence misinterpretation trigger reconsideration. Citation absence and minor wording do not.

The owning diagnosis conversation repairs material defects when required. A subsequent evidence-alignment pass preserves each `fact` and `reason` exactly and adds only `citation`, using exact runtime card tags where a card directly supports the reason; otherwise `citation: null`.

`category-diagnosis.yaml` is then the accepted downstream routing state.

## Step 5 — Downstream terraced categories

Run until exit `0`:

```bash
<python> workflows/terraced_v1/step.py 5 --work-dir <work-dir>
```

The CLI processes, in order:

1. prognosis;
2. treatment;
3. MRD;
4. germline.

For each category it performs narrow retrieval against every accepted diagnosis, runs the configured terraced conversation using accepted upstream clinical state, performs the same high-threshold semantic review/repair loop, and finally aligns fact/reason pairs to direct card support.

Accepted artifacts are `category-prognosis.yaml`, `category-treatment.yaml`, `category-mrd.yaml`, and `category-germline.yaml`.

## Step 6 — Single synthesis, final citation alignment, render

Run until exit `0`:

```bash
<python> workflows/terraced_v1/step.py 6 --work-dir <work-dir>
```

The CLI deterministically creates `report-facts.yaml` by stripping every `reason` and `citation`. The model receives facts only and writes one uncited `report-draft.md`.

A separate final model pass receives the accepted category artifacts and semantically matches every final report sentence back to its source fact(s). It may only append inherited runtime card tags or `(no citation required)`; it cannot change prose or search for new evidence.

If a sentence cannot be matched to any accepted fact, summarisation is redrafted rather than reopening clinical terraces.

The CLI then builds combined citation evidence, validates runtime tags, renders Vancouver references deterministically, and writes `report-final.md`.

## Step 7 — Existing delivery behaviour

Run:

```bash
<python> workflows/terraced_v1/step.py 7 --work-dir <work-dir>
```

This writes `ngs-report-debug.zip` and, when model bundles exist, `ngs-report-model-steps.zip`.

Mode-specific delivery remains the same as the other `ngs-report` workflows:

- `ngs-report`: display `report-final.md` unchanged and return the debug ZIP.
- `nel-demo`: only now read the recorded demo case and expected-behaviour files; display case, generated report and expected behaviour, and return the debug ZIP.
- `nel-validate`: do not run a marking model. Run:

```bash
<python> validation/package_marking.py <validation-case> \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-<validation-case>.zip
```

- `nel-validate-function`: do not run a marking model. Run:

```bash
<python> validation/package_marking.py <validation-case> \
  --case-file validation/case_functional.md \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-function-<validation-case>.zip
```

Return the external-marking ZIP and debug ZIP for validation modes.

## Direct CLI execution

Outside the frontier skill harness, the entire workflow can be run against a configured provider profile:

```bash
<python> workflows/terraced_v1/step.py setup --mode ngs-report \
  --case-file case.md --model-profile lmstudio --terrace-profile balanced --project

<python> workflows/terraced_v1/step.py --all
```

Equivalent model profiles are available for `ollama` and `openrouter`. The provider endpoints and model IDs are configuration and may be overridden by the environment variables declared in `models.json`.
