# Terraced-v3

Terraced-v3 is an experimental NGS evidence workflow in which a **pipeline** chooses the model/provider configuration and connects diagnosis, PTBG, immutable statement-ledger collection, summarization and rendering modules.

## Quick start

List shipped pipelines:

```bash
python workflows/terraced_v3/step.py pipelines
```

Validate a pipeline before running it:

```bash
python workflows/terraced_v3/step.py pipeline-check --pipeline self
```

Run validation brief case 1 with the self pipeline:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief \
  --case-id 1 \
  --pipeline self
```

Then continue the scripted run:

```bash
python workflows/terraced_v3/step.py run --work-dir <run-directory>
```

For `self`, the CLI emits model handoffs to be completed by the session model. LM Studio and OpenRouter pipelines call their configured OpenAI-compatible endpoints directly.

## Shipped pipelines

```text
self
lmstudio
openrouter
```

Each pipeline YAML defines:

- provider;
- ordered module graph;
- diagnosis scheduler;
- PTBG scheduler;
- summarization scheduler;
- model name, temperature and token cap for each model role.

Inspect the full graph:

```bash
python workflows/terraced_v3/step.py pipeline-plan --pipeline self
```

## Scheduler overrides

The shipped pipelines contain exactly one diagnosis, PTBG and summarization scheduler, so these can be overridden for development:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 \
  --pipeline self \
  --diagnosis-scheduler minimal-diagnosis \
  --ptbg-scheduler evidence-first \
  --summarization-scheduler minimal-summarization
```

List schedulers with:

```bash
python workflows/terraced_v3/step.py schedulers --phase diagnosis
python workflows/terraced_v3/step.py schedulers --phase ptbg
python workflows/terraced_v3/step.py schedulers --phase summarization
```

## Run directory

The run root contains the true input and genuine outputs. Generated audit/state artifacts are separated:

```text
<run>/
├── case.md
├── model_steps/
│   ├── 001_...
│   └── ...
├── intermediates/
│   ├── 001_setup/
│   │   ├── pipeline-resolved.yaml
│   │   └── pipeline-compiled.md
│   └── ...
├── report-final.md
├── workflow.log
├── terraced-v3-debug.zip
└── <validation-marking-package>.zip
```

The report always begins with the invariant source-faithful NGS variant sentence containing detected gene/HGVS/VAF information supplied in the case.

## What is configurable?

Pipelines and schedulers are declarative YAML assets. Structured inputs/outputs are documented in Markdown contract assets rather than being hidden as Python templates. Pipeline setup validates that each downstream required input is compatible with the connected upstream output before any model call is made.

For architecture, contract lookup rules, writing custom schedulers/pipelines and adapters, see [`DEVEL.md`](DEVEL.md).

## Evidence guarantees

Regardless of scheduler topology:

- CMC routing is derived deterministically from validated WHO5 diagnosis state;
- ICC is independently reasoned and does not control CMC;
- diagnosis may retain historical CMC evidence while stabilising;
- downstream retrieval uses the final CMC set;
- diagnosis evidence is authority-filtered by `corpus_filters.yaml` (WHO5 → Khoury 2022; ICC → Arber 2022 by default);
- diagnosis uses three-pass evidence resolution: line-number relevance selection, statement/local-card pairing over the reduced bundle, then deterministic ID resolution plus binary reasonable-support audit;
- diagnosis models never generate immutable runtime card IDs during relevance selection or pairing; Python resolves local `CARD nn` labels to final `card_tags`;
- PTBG clinical reasoning produces reportable `statement + reason + case_refs` with empty card fields; publication then performs line-number evidence reduction, local-card pairing, deterministic ID resolution and binary support audit;
- accepted statement text, reason, patient provenance and card attribution are immutable together; replacements receive a new statement ID;
- summarization explicitly decides include/omit, sentence order, merge and split using immutable statement IDs; diagnosis statements cannot be omitted;
- paraphrasing cannot change provenance and is followed by a reject-only semantic-preservation check;
- sentence citations are inherited deterministically as the union of the sentence's `source_statement_ids`;
- no final semantic evidence-alignment or sentence-to-statement matching model call is used;
- `sentence-card-interpretations.yaml` is generated deterministically from final sentence/statement/card-tag provenance.
