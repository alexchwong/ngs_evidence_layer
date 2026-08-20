# Diagnosis terrace lab

Standalone experimental harness for the terraced-v1 **diagnosis terrace only**.

It is intentionally **not registered as a workflow**, does not replace `terraced-v1`, and does not write to normal terraced-v1 work directories. It is designed for rapid prompt/model experimentation with LM Studio, OpenRouter, or another OpenAI-compatible endpoint.

## What it tests

The lab uses seven diagnosis challenges applied to one evolving state:

1. whole-case provisional disease process;
2. alternative/concurrent pathology challenge;
3. overt neoplasm vs CHIP/CCUS vs germline predisposition/syndrome;
4. authoritative WHO5 diagnosis, including supported `No pathology identified`;
5. ICC diagnostic label only when materially different;
6. adversarial contradiction/uncertainty review;
7. card-free synthesis of WHO5/ICC state, supporting facts and material uncertainty.

DX7 receives **only the original case notes and DX6 state**. It receives no diagnosis cards and no prior terrace transcript. WHO5 and material ICC state are protected, each synthesized fact maps to DX6 source fact IDs, explicit DX6 uncertainties are deletion-resistant, and DX7 cannot introduce a new numeric token.

Negative NGS is explicitly supported but is independent of a no-pathology conclusion.

## Example inputs

`fixtures/example-01` through `fixtures/example-06` are generated from the repository's six demo cases. Each `input.json` contains the complete expected initial diagnosis-terrace context:

- original case notes;
- a deterministic structured-case extraction;
- NGS panel scope;
- allowed provisional CMC values;
- allowed final `schema_disease` values;
- diagnosis/germline cards retrieved from the current corpus using the example's initial CMC(s) and genes;

The adjacent `expected.md` is copied from `examples/expected/` for human comparison and is **not supplied to the model**.

Regenerate the fixture inputs after corpus changes:

```bash
python workflows/terraced_v1/diagnosis_lab/fixture_builder.py
```

## LM Studio

Start an OpenAI-compatible LM Studio server, then:

```bash
python workflows/terraced_v1/diagnosis_lab/run.py \
  --example 1 \
  --profile balanced \
  --provider lmstudio \
  --model qwen3-coder-next
```

Default endpoint is `http://localhost:1234/v1`. Override with:

```bash
export NEL_LMSTUDIO_BASE_URL=http://localhost:1234/v1
```

or `--base-url`.

## OpenRouter

```bash
export OPENROUTER_API_KEY='...'
python workflows/terraced_v1/diagnosis_lab/run.py \
  --example 1 \
  --profile balanced \
  --provider openrouter \
  --model qwen/qwen3-coder-next
```

OpenRouter defaults to `https://openrouter.ai/api/v1`.

## Generic OpenAI-compatible endpoint

```bash
python workflows/terraced_v1/diagnosis_lab/run.py \
  --example 1 \
  --provider openai-compatible \
  --base-url http://127.0.0.1:8000/v1 \
  --model my-model
```

## Profiles

- `frontier`: `[DX1-DX5] [DX6] [DX7]`
- `balanced`: `[DX1-DX3] [DX4-DX5] [DX6] [DX7]`
- `deliberate`: one model call per question.

## Inspect prompts without spending tokens

```bash
python workflows/terraced_v1/diagnosis_lab/run.py --example 1 --profile balanced --dry-run
```

The run directory contains `call_01_*` with the exact first-call payload in `INPUT_messages.json` and a readable rendering in `INPUT_messages_readable.md`. Later prompts depend on earlier model output, so dry-run records their planned groups in `RUN_metadata.json` rather than fabricating payloads.

## Run artifacts

Each real model pass gets its own directory. A balanced run therefore looks like:

```text
example-01-balanced-<timestamp>/
├── RUN_INPUT_fixture.json
├── RUN_metadata.json
├── call_01_DX1-DX3/
├── call_02_DX4-DX5/
├── call_03_DX6/
├── call_04_DX7/
└── FINAL_OUTPUT.yaml
```

The intent is that you can inspect the workflow one model call at a time. Every `call_*` directory is self-contained and uses explicit `INPUT_*` and `OUTPUT_*` filenames.

Typical pre-DX7 call:

```text
call_02_DX4-DX5/
├── CALL_metadata.json
├── INPUT_overview.md
├── INPUT_questions.md
├── INPUT_case_notes.md
├── INPUT_previous_state.yaml
├── INPUT_prior_transcript.json
├── INPUT_evidence_cards.json
├── INPUT_messages.json
├── INPUT_messages_readable.md
├── OUTPUT_raw.txt
├── OUTPUT_state.yaml
└── OUTPUT_validation.json
```

`INPUT_messages.json` is the exact OpenAI-compatible messages payload sent to the model. `INPUT_messages_readable.md` contains the same message sequence rendered with SYSTEM/USER/ASSISTANT headings for easy inspection.

`INPUT_previous_state.yaml` shows the validated state entering the call. `INPUT_prior_transcript.json` shows the earlier terrace turns included in context. `INPUT_evidence_cards.json` shows the diagnosis/germline cards visible to that pass. `INPUT_questions.md` isolates the question or question group being asked.

`OUTPUT_raw.txt` is the model response before parsing or validation. `OUTPUT_state.yaml` is the accepted structured state after validation. `OUTPUT_validation.json` records whether the pass satisfied the relevant deterministic guards. If the API itself fails, the call directory instead records `OUTPUT_api_error.txt`; if validation fails, the raw response and failed `OUTPUT_validation.json` remain for debugging.

DX7 is deliberately different:

```text
call_04_DX7/
├── CALL_metadata.json
├── INPUT_overview.md
├── INPUT_questions.md
├── INPUT_case_notes.md
├── INPUT_previous_state.yaml   # protected DX6 state with source IDs
├── INPUT_prior_transcript.json # always []
├── INPUT_messages.json
├── INPUT_messages_readable.md
├── OUTPUT_raw.txt
├── OUTPUT_state.yaml
└── OUTPUT_validation.json
```

There is intentionally **no `INPUT_evidence_cards.json` in DX7**, because diagnosis cards are not supplied to that call. The earlier terrace transcript is also withheld.

At run root, `RUN_INPUT_fixture.json` records the source fixture, `RUN_metadata.json` records provider/model/profile and call status, and `FINAL_OUTPUT.yaml` duplicates the last accepted state for convenience.

With `--dry-run`, only `call_01_*` is created because later exact inputs depend on earlier model outputs. `OUTPUT_not_run.txt` explains this; later prompts are not fabricated.

## Safety boundaries deliberately tested here

- DX4 onward must retain an explicit WHO5 state.
- WHO5 may be a defined diagnosis, concurrent diagnoses, or supported no pathology.
- ICC is diagnostic-labelling only.
- DX6 cannot erase WHO5 or silently erase a previously material ICC comparator.
- DX7 must copy WHO5/ICC/CMC state exactly from DX6.
- DX7 has no diagnosis cards or prior transcript.
- Every DX7 fact maps to one or more DX6 facts.
- Every explicit DX6 uncertainty must be represented in DX7.
- DX7 cannot introduce a numeric token absent from DX6.

These are experimental guards, not proof of clinical correctness. A wrong DX6 conclusion can still be faithfully preserved by DX7; the lab is intended to make that failure visible rather than hide it.
