# Diagnosis terrace lab

Diagnosis-only terraced-v1 development area with two entry points:

- `run.py` remains the standalone experimental fixture harness and is intentionally not a registered workflow.
- `workflow.py` is the complete diagnosis-only vertical slice, adding the terraced-v1 case-structure head, per-terrace deterministic retrieval, final citation rendering, logging, and packaging around the same diagnosis terrace logic.

Neither entry point replaces the full `terraced-v1` workflow. The lab remains suitable for rapid prompt/model experimentation with LM Studio, OpenRouter, or another OpenAI-compatible endpoint.


## Complete diagnosis-only workflow

`workflow.py` wraps the existing experimental diagnosis terrace with the terraced-v1 head and a diagnosis-only tail. The original `run.py` remains the fixture-based laboratory harness.

The complete wrapper:

- accepts an authoritative `case.md` directly and bypasses case capture/rewrite;
- supports `nel-demo`, `nel-validate`, `nel-validate-function`, and `nel-validate-brief`;
- structures the case with terraced-v1 Step 1b and fixes the reported gene list at that point;
- initializes a deterministic 12-hex identity plus content SHA-256 for **every corpus card before blacklist/retrieval filtering**;
- performs a fresh deterministic diagnosis/germline draw at the start of every non-final diagnosis terrace using fixed genes + the last accepted CMCs + terrace category;
- does **not** repeat the same terrace after a CMC change: the changed CMC controls the next terrace draw;
- keeps gene-matched germline cards available during diagnosis;
- writes timestamp-named run directories, elapsed-time `workflow.log`, diagnosis-only `report-final.md`, and a debug ZIP;
- for validation modes, writes the standard external marking ZIP and **does not perform marking**.

Arbitrary case:

```bash
python workflows/terraced_v1/diagnosis_lab/workflow.py \
  --mode ngs-report \
  --case-file case.md \
  --profile balanced
```

Demo case:

```bash
python workflows/terraced_v1/diagnosis_lab/workflow.py \
  --mode nel-demo --example 1 --profile balanced
```

Validation case (package only; no marking call):

```bash
python workflows/terraced_v1/diagnosis_lab/workflow.py \
  --mode nel-validate --case-id 1C --profile balanced
```

The canonical user output is `report-final.md`. `evidence/card-identity-manifest.json` freezes the run-global corpus identity, `evidence/diagnosis-card-draws.json` audits each terrace's CMC-controlled draw, and validation runs additionally contain `nel-validation-<case>.zip` for external marking.

The case-structure head uses a direct terraced-v1 model profile. With `--provider lmstudio` or `--provider openrouter`, the matching terraced profile is selected automatically; a generic `--provider openai-compatible` run must also supply `--model-profile`.

## What it tests

The lab applies the terrace questions declared in `questions.yaml` to one evolving state, followed by one mandatory terminal synthesis question and the report connector:

1. independently derive paired WHO5 and ICC outcomes for each disease process;
2. challenge for a competing diagnosis or true concurrent pathology;
3. distinguish overt disease, precursor clonal states and germline predisposition;
4. adversarially review criteria, exclusions, assumptions, contradictions and uncertainty;
5. the configured `kind: final` question performs card-free synthesis of the paired diagnostic state, supporting facts and material uncertainty;
6. post-final diagnostic report synthesis, immutable sentence-to-fact conversion, source grounding, and evidence alignment.

`DX-final` receives **only the original case notes and protected pre-final state**. It receives no diagnosis cards and no prior terrace transcript. The paired WHO5/ICC state is protected, each synthesized fact maps to `PRE-FINAL-F*` source IDs, explicit `PRE-FINAL-U*` uncertainties are deletion-resistant, and final synthesis cannot introduce a new numeric token.

## Question-driven execution

`questions.yaml` is authoritative for question count and order. Each question declares `kind: terrace` or `kind: final`; exactly one final question is required and it must be last. Execution profiles define only `terrace_groups`. The runtime automatically appends the final question as a dedicated one-question pass, so profiles do not repeat `[DX-final]` and Python does not encode a fixed number of diagnosis questions.

The final question also declares its context, output keys, and deterministic invariants. Its model prompt is generated from that configuration and guidance; there is no separate numbered final-prompt file.

Each diagnosis row represents one disease process and contains separate WHO5 and ICC outcomes with explicit `established`, `indeterminate`, `not_established`, or `not_applicable` status. Different classifier labels for the same process remain in one row; separate rows represent possible or established concurrent pathologies. `schema_disease` remains the WHO5-controlled downstream routing key.

Negative NGS is explicitly supported but is independent of a no-pathology conclusion.

## Example inputs

`fixtures/example-01` through `fixtures/example-06` are generated from the repository's six demo cases. Each `input.json` contains the complete expected initial diagnosis-terrace context:

- original case notes;
- a deterministic structured-case extraction;
- NGS panel scope;
- allowed provisional CMC values;
- allowed final `schema_disease` values;
- diagnosis/germline cards retrieved from the current corpus using the example's initial CMC(s) and genes;

The adjacent `expected.md` is generated from the centrally managed `nel-demo` marking criteria for fixture comparison and is **not supplied to the model**.

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

- `frontier` terrace groups: `[DX1-DX3] [DX4]`
- `balanced` terrace groups: `[DX1] [DX2-DX3] [DX4]`
- `deliberate`: one model call per terrace question.

Every profile then runs the configured `DX-final` question automatically as its own pass.

## Deterministic validation repair

Every model output boundary—the terrace groups, final synthesis, report synthesis, reason grounding, and evidence alignment—uses the same bounded deterministic repair loop. A failed parser or validator returns location-specific `Problem` and `Required fix` feedback to the model together with its complete failed output. The model must fix only the reported defects and return the complete artifact again.

The default bound is 10 attempts, matching terraced-v1. Override it with `--structural-attempts N`. Provider/network errors are not deterministic output defects and are not retried as syntax repairs.

Each model-call directory retains every attempt:

```text
attempt_01/
├── INPUT_messages.json
├── INPUT_messages_readable.md
├── OUTPUT_raw.txt
└── OUTPUT_validation.json
```

Call-level `INPUT_messages*`, `OUTPUT_raw.txt`, and `OUTPUT_validation.json` mirror the latest attempt. Accepted artifacts such as `OUTPUT_state.yaml` are written only after deterministic validation passes.

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
├── call_01_DX1/
├── call_02_DX2-DX3/
├── call_03_DX4/
├── call_04_DX-final/
└── FINAL_OUTPUT.yaml
```

The intent is that you can inspect the workflow one model call at a time. Every `call_*` directory is self-contained and uses explicit `INPUT_*` and `OUTPUT_*` filenames.

Typical pre-finalization call:

```text
call_03_DX4/
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

The configured final pass is deliberately different:

```text
call_04_DX-final/
├── CALL_metadata.json
├── INPUT_overview.md
├── INPUT_questions.md
├── INPUT_case_notes.md
├── INPUT_previous_state.yaml   # protected pre-final state with source IDs
├── INPUT_prior_transcript.json # always []
├── INPUT_messages.json
├── INPUT_messages_readable.md
├── OUTPUT_raw.txt
├── OUTPUT_state.yaml
└── OUTPUT_validation.json
```

There is intentionally **no `INPUT_evidence_cards.json` in the final pass**, because diagnosis cards are not supplied to that call. The earlier terrace transcript is also withheld.

At run root, `RUN_INPUT_fixture.json` records the source fixture, `RUN_metadata.json` records provider/model/profile and call status, and `FINAL_OUTPUT.yaml` duplicates the accepted final state.

After final synthesis, the report connector receives the initial case stem/structured case and accepted final state. It does not force an assigned diagnosis when the state contains only a candidate. Machine status tokens such as `indeterminate` are not printed; the prose instead states what is supported, why firmer classification is limited, and which broad designation remains current.

The connector writes:

```text
REPORT_INPUT_SOURCES.yaml     # initial case plus deterministic IDs on final sources
FINAL_REPORT_DRAFT.md         # uncited diagnosis prose, one sentence per line
REPORT_IMMUTABLE_FACTS.yaml   # deterministic byte-for-byte sentence-to-fact conversion
FINAL_FACTS.yaml              # immutable facts plus reasons and source mappings
FINAL_ALIGNED.yaml            # same facts with permitted runtime card tags or null
FINAL_REPORT.md               # deterministically rendered cited prose
connector_01_synthesis/       # exact synthesis call and validation
connector_02_reasons/         # exact reason/source-mapping call and validation
connector_03_alignment/       # exact card-alignment call and validation
```

Only the first connector call writes prose. Code assigns ordered `diagnosis-summary-N` fact IDs and later validators prohibit changes to sentence text. The reason pass has no cards and must map every fact to supplied case or diagnostic-state IDs. The alignment pass may add only a permitted citation disposition. Final report rendering is deterministic and has no further generative rewrite.

With `--dry-run`, only `call_01_*` is created because later exact inputs depend on earlier model outputs. `OUTPUT_not_run.txt` explains this; later prompts are not fabricated.

## Safety boundaries deliberately tested here

- Every diagnosis row must contain explicit paired WHO5 and ICC outcomes.
- WHO5 may be a defined diagnosis, concurrent diagnoses, or supported no pathology and alone controls routing.
- ICC is diagnostic-labelling only and cannot be detached from its disease process.
- The configured final pass must copy protected diagnosis/CMC fields exactly from the pre-final state.
- The final pass has no diagnosis cards or prior transcript.
- Every final fact maps to one or more pre-final facts.
- Every explicit pre-final uncertainty must be represented in the final state.
- Final synthesis cannot introduce a numeric token absent from the pre-final state.
- Report synthesis cannot expose internal machine-status vocabulary or emit citations.
- Every report sentence is copied deterministically into one immutable fact.
- Reason grounding is closed to supplied case and reviewed-diagnostic source IDs.
- Evidence alignment cannot change a fact or reason and can add only permitted runtime card tags.
- Final cited prose is rendered by code rather than rewritten by a model.

These are experimental guards, not proof of clinical correctness. A wrong pre-final conclusion can still be faithfully preserved by final synthesis; the lab is intended to make that failure visible rather than hide it.
