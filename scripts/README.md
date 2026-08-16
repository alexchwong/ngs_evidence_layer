# Scripts

Scripts are grouped below by their primary role.

## Skill

- `append_integrated_diagnosis.py`
- `card_tags.py` — shared deterministic runtime card-tag assignment/deconvolution
- `package_run.py` — workflow-state-driven debug packaging
- `render.py` — shared evidence renderer
- `report_audit.py`
- `report_citations.py`
- `retrieval_core.py` — shared corpus, blacklist, validation, provenance and tag mechanics
- `retrieve.py` — workflow-state-driven retrieval dispatcher
- `run_case.py` — workflow-state-driven case-stage dispatcher
- `setup_workflow.py` — create/reuse a work directory and bind workflow identity
- `validate_adjudication.py`
- `workflow_registry.py` — workflow registry/state loader
- `workflow_runtime.py` — dispatch workflow-owned deterministic runtime helpers

## Ingest

- `apply_phase5.py`
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
- `prepare_redo.py`
- `quarantine.py`
- `render_corpus.py`
- `transport.py`
- `validate_phase5.py`
- `validate_review.py`
- `phase_validation/`
  - `__init__.py`
  - `phase1.py`
  - `phase2.py`
  - `phase4.py`
  - `phase5.py`

## Development

- `build_blacklist.py`
- `build_prompts.py`
- `build_skill_zip.py`
- `devel_workflow.py` — clone/check isolated workflow implementations

## Other

- `backfill_acceptance_version.py` — maintenance/migration utility
- `vocab.py` — shared vocabulary definitions
