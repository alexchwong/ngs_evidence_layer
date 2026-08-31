# Scripts

Runtime code uses a three-layer boundary: stable CLI dispatchers in `scripts/`, policy-neutral mechanics in `scripts/core/`, and workflow behaviour in `workflows/<workflow>/`. Shared core code must not branch on workflow identity.

## Skill runtime dispatchers

- `run_case.py` — dispatch a case-pipeline stage to the workflow bound to the work directory.
- `retrieve.py` — dispatch retrieval to the bound workflow.
- `render.py` — dispatch evidence rendering to the bound workflow.
- `report_audit.py` — dispatch report-draft audit policy to the bound workflow.
- `report_citations.py` — stable CLI over shared citation mechanics.
- `package_run.py` — package workflow-declared debug artifacts.
- `setup_workflow.py` — create/reuse a work directory and bind workflow identity.
- `workflow_registry.py` — resolve workflow metadata, state and declared entrypoints.
- `workflow_runtime.py` — dispatch optional workflow-owned runtime commands.

## Shared skill core (`scripts/core/`)

- `corpus.py` — load, validate, flatten and blacklist corpus cards.
- `retrieval.py` — policy-neutral case validation and retrieval helper primitives.
- `rendering.py` — policy-neutral evidence rendering primitives parameterised by workflow callbacks.
- `card_tags.py` — deterministic runtime card-tag assignment and deconvolution.
- `citations.py` — citation marker validation, normalisation and final reference rendering.
- `provenance.py` — construct deterministic corpus provenance metadata.

Workflow-specific retrieval, rendering, adjudication, audit and report policy belongs under `workflows/<workflow>/`, not in `scripts/core/`.

## Ingest

- `build_secondary_source_backlog.py`
- `citations.py`
- `confirm.py`
- `fanout.py`
- `final_validation.py`
- `incorporate.py`
- `index_store.py`
- `make_key.py`
- `package_validation.py`
- `parse_pdfs.py`
- `prepare_redo.py` — restore accepted or archive-only state for census, provisional, or card Phase 2 review.
- `ingest_artifacts.py` — versioned/legacy ingestion filename resolver.
- `quarantine.py`
- `render_corpus.py`
- `transport.py`
- `validate_review.py`
- `phase_validation/`
  - `__init__.py`
  - `phase1.py`
  - `phase2.py`
  - `phase2_state.py` — validate/resume Phase 2 semantic-gate or authoring checkpoints, deterministically diff repaired censuses, and report the exact semantic recheck claim set.
  - `phase4.py`


## Corpus browser and Corpus User Layer

These are deliberately separate HTML artefacts:

- `python scripts/build_card_browser.py` builds the read-only corpus browser at
  `output/reports/card-browser.html`. It reads `output/corpus/` only.
- `python scripts/build_card_browser.py --full` builds the same read-only browser
  with accepted evidence, support mapping and provenance at
  `evidence/card-browser-full.html`. It requires matching `accept/*.final.json`
  packages and does not require `archive/`.
- `python scripts/cul.py --edit` builds/opens the editable Corpus User Layer at
  `config/cul/corpus-user-layer.html`. This is a different, gitignored artefact
  owned by `cul.py`; it does not overwrite `output/reports/card-browser.html`.
  `python scripts/cul.py edit` is retained as an alias.

Both read-only browser modes provide a per-card `Copy citation` control. Editing
profiles and retrieval scope belongs only to the Corpus User Layer interface.

## Development

- `build_blacklist.py`
- `build_prompts.py`
- `build_skill_zip.py`
- `devel_workflow.py` — clone/check isolated workflow implementations and declared entrypoints.

## Other

- `backfill_acceptance_version.py` — maintenance/migration utility.
- `vocab.py` — shared vocabulary definitions.
