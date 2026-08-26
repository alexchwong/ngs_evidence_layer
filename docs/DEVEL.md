# Developer guide

This file is for repository maintenance. End-user reporting is documented in `../README.md`;
paper ingestion is documented in `docs/ingest.md`.

## Quick start

From the repository root, create the local environment once:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```

Activate it in each new shell, then use the relevant maintenance commands:

```bash
. .env/bin/activate

# Regenerate any prompt affected by canonical template, asset, rule, vocabulary, or schema changes.
python scripts/build_prompts.py --phase <1|2|3|4>

# Regenerate runtime JSON after editing output/corpus/blacklist.yaml.
python scripts/build_blacklist.py

# Run the full test suite.
python -m unittest discover -s tests -v 2>&1

# Build and verify a provisional skill ZIP.
python scripts/build_skill_zip.py
```

Before release, update `NEWS.md`, synchronize `docs/corpus.md`,
set `release/VERSION`, review `release/skill.txt`, and confirm that no private ingestion
files are staged. See [Pre-release housekeeping](#pre-release-housekeeping).

## Contents

- [Reporting workflow architecture](#reporting-workflow-architecture)
- [Regenerate ingestion prompts](#regenerate-ingestion-prompts)
- [Regenerate the blacklist](#regenerate-the-blacklist)
- [Run tests](#run-tests)
- [Release configuration](#release-configuration)
- [Release documentation format](#release-documentation-format)
- [Pre-release housekeeping](#pre-release-housekeeping)
- [Post-release check](#post-release-check)
- [Documentation ownership](#documentation-ownership)

## Reporting workflow architecture

See [`workflows.md`](workflows.md) for the full workflow-separation contract, cloning
procedure, modification boundaries, validation, and promotion/removal steps.

**Default workflow:** `terraced-v6` — Uses isolated WHO5/ICC/WHO5 diagnostic passes, combined downstream domain reasoning, and audited evidence resolution before final synthesis.

**Diagnosis-first compatibility workflow:** `diagnosis-first-v1` — Answers diagnostic rules first to establish
the integrated diagnosis, then passes that diagnosis into a second pass over the remaining
agreed reporting rules.

**Alternate workflows:**

- `legacy-v1` — Adjudicates and appends the integrated diagnosis before a single later
  pass evaluates the complete case against all agreed reporting rules.

Create an isolated experimental workflow with:

```bash
python scripts/devel_workflow.py new --from terraced-v6 --name <new-workflow-id>
python scripts/devel_workflow.py check <new-workflow-id>
```

The helper clones only the workflow-owned tree, updates its identifiers/import paths,
registers it without changing the default, and leaves shared contracts referenced in
place. Promotion to default remains a deliberate edit of `workflows/registry.json`.

Reporting runtime code has three dependency layers. Stable CLIs in `scripts/` resolve the
workflow from `<work-dir>/workflow.json` and dispatch only to entrypoints declared by the
workflow metadata. Policy-neutral mechanics live in `scripts/core/`; they must not import,
name, or branch on a workflow. Retrieval, rendering, adjudication, report-audit policy and
other behaviour that can differ between pipelines belongs in `workflows/<workflow>/`.
This keeps workflow changes isolated while retaining one implementation of corpus, tag,
citation and provenance invariants.

## Regenerate ingestion prompts

The committed Phase 1–4 prompts are generated artefacts.

Edit phase-specific prose under:

```text
prompts/templates/
```

Shared prompt prose lives under `prompts/assets/`. `prompts/assets/manifest.json` maps
each `{{ASSET_KEY}}` used by a template to either one complete canonical file or a
bundle of complete files. `scripts/build_prompts.py` is a generic renderer: adding or
moving a prompt asset should require a manifest edit and template marker, not new
phase-specific Python dispatch.

Cross-phase ingestion semantics are deliberately single-source assets. Phases 1–4 share
clinical relevance, source-bounded reasoning, category semantics, atomicity, and the
geneless-claim policy. Phases 2–4 additionally share interpretation and source-support
principles. Phase templates retain workflow mechanics and phase-specific calibration; do
not copy an authoritative semantic definition back into a template. The marker-matrix and
golden-invariant tests protect this injection graph.

Edit rules, vocabularies, schemas, executable validation code, and other canonical
sources only at their owning paths. In particular, canonical disease names, source
aliases, taxonomic parents, and retrieval relationships live together in
`schema/disease_vocabulary.json`; publication-type taxonomy lives in
`schema/publication_type_vocabulary.json`; Phase 3-only publication-type audit policy
lives in `prompts/assets/publication_type_audit_policy.md`.

Phase-specific online validators live under `scripts/phase_validation/`: the prompt
manifest injects the relevant Phase 1, 2, or 4 validator, while Phase 3 has no
executable prompt validator and is checked by Phase 4 on entry. Phase 2R and Phase 4
share `scripts/phase_validation/card_deltas.py` plus `schema/card_decision_schema.json`
to enforce user-authorized card/evidence deltas. New workflow packages use schema 5.1. Normal Phase 2 schema-5.1 provisionals also carry
top-level `human_decisions`: the effective, approved human semantic-gate rulings with affected
card/claim IDs and human-supplied reasons. Human deletions define which cards are absent; surviving
human-added/edited/category-changed cards are still independently reviewable in Phase 3. Phase 3 receives
no census and does not audit census/card-set completeness. Normal Phase 2 now checkpoints **both**
completed semantic-census audits that return a Phase 1 critique and already-audited card candidates
that encounter a later census defect. Both use `paper.phase2-state-vNNN.json`;
`checkpoint_stage: "census_semantic_gate"` stores per-claim semantic pass/defect/out-of-scope state
without cards, while `checkpoint_stage: "authoring"` additionally stores candidate cards/evidence,
dispositions, human decisions, and card-ID allocation state. `schema/phase2_state_schema.json` owns
this transient contract and `scripts/phase_validation/phase2_state.py` validates checkpoint lineage,
deterministically diffs the source/repaired census, and returns the exact claim IDs requiring semantic
recheck. The complete repaired census still passes the Phase 1 deterministic validator every time;
unchanged previously-passed claims are not semantically re-reviewed. A still-defective repair reuses
the last valid checkpoint baseline rather than replacing it with partial state. Authoring checkpoints
preserve unaffected card state, while final package consistency and fresh human approval remain required. Phase 2R preserves `human_decisions` as historical provenance and continues to use
its separate decision ledger. Phase 4 must preserve them unchanged into the final package. Legacy
schema-5.0 and older schema-5.1 packages remain readable without this field.
`scripts/final_validation.py` remains the local compatibility CLI for Phases 1–4 and
dispatches to the canonical phase validators. File assets are injected in full; bundle
members are embedded verbatim in full. Read `prompts/meta_prompt.md` before changing
extraction rules or schemas.

Regenerate the affected prompt:

```bash
python scripts/build_prompts.py --phase 1
python scripts/build_prompts.py --phase 2
python scripts/build_prompts.py --phase 3
python scripts/build_prompts.py --phase 4
```

Do not edit generated phase prompts directly. Edit the corresponding template or other
canonical source, regenerate the prompt, inspect the diff, and commit the generated
prompt with its source change.

Any edit to `prompts/assets/clinical_assertion_policy.md`,
`prompts/assets/clinical_card_policy.md`, or `prompts/assets/source_fidelity_policy.md` is
behaviour-affecting. In addition to the unit tests, rerun the maintained accepted-paper semantic regression set
before promotion and compare card yield/changes by publication type and category. Build
that regression set deliberately against live-corpus publication-type/category coverage
and record any unrepresented strata. After promotion, manually review the Phase 2
validator's existing `cards`, `census_entries`, and ratio summary across the first defined
batch of live ingestions, with particular attention to unrepresented strata. This is an
observation signal, not a pass/fail threshold.

When promoting a changed interpretation standard, bump `release/VERSION` so
`accepted_in_version` provides the existing acceptance-provenance boundary between
pre- and post-standard acceptances. Bulk re-ingestion of older accepted papers remains a
separate migration decision.

## Regenerate the blacklist

`output/corpus/blacklist.yaml` is the human-edited canonical card eligibility policy.
Runtime retrieval does not parse YAML; it reads the committed generated artefact:

```text
output/corpus/blacklist.json
```

After every blacklist YAML edit, regenerate the JSON from the repository root:

```bash
python scripts/build_blacklist.py
```

Do not edit `blacklist.json` directly. Commit it with the corresponding YAML change and
inspect the generated diff before running tests. `--source` and `--output` are available
for development fixtures or alternate paths.

## Run tests

Run the full unittest suite:

```bash
python -m unittest discover -s tests -v 2>&1
```

Run this after code, schema, vocabulary, prompt-generation, retrieval, ingestion, or
release-workflow changes.

## Release configuration

Release configuration is intentionally small.

### Version

The release version is stored in:

```text
release/VERSION
```

It must contain exactly one semantic version in `X.Y.Z` form, for example:

```text
0.2.2
```

The release workflow uses this value to create the tag, release title, archive root, and
ZIP filename.

If the current version has already been released and the skill payload changes, bump
`release/VERSION` before merging the payload change to `master`.

### Skill release contents

The skill-only release payload is defined by:

```text
release/skill.txt
```

Each non-empty line is a tracked path or glob pattern. Globs are supported.

When `SKILL.md` gains a new runtime dependency, add that file or a suitable glob to
`release/skill.txt`. Remove entries that are no longer required.

The GitHub Action fails if a manifest pattern matches no tracked files and verifies that
the finished ZIP contains exactly the resolved manifest contents. Build and verify the
skill ZIP locally from the repository root with:

```bash
python scripts/build_skill_zip.py
```

Use `--output <path>` to choose a different output path.

### Release action

The release workflow is:

```text
.github/workflows/release.yml
```

It runs:

- automatically on pushes to `master`;
- manually via `workflow_dispatch`.

For a new version it builds the skill-only ZIP and creates the GitHub release. If the
version tag already exists, skill-payload changes require a version bump.

## Release documentation format

### NEWS entries

Add user-visible changes under the intended version heading in `NEWS.md`. Every new
bullet point must contain no more than 20 words. Use one concise change per bullet and
avoid implementation detail unless it affects users or operators.

### Corpus documentation

`docs/corpus.md` must use this structure:

1. Open with the current release version and total number of active publications.
2. State that publications are grouped by `latest_accepted_in_version` from
   `output/corpus/nel.index.json`.
3. Group active publications under `### Last modified in vX.Y.Z` headings, newest
   version first.
4. Under each version heading, use a four-column table in this exact order:
   `Publication key`, `DOI`, `Paper nickname`, `Contribution to corpus`.
5. List each active publication exactly once. Use publication/version/nickname metadata
   from `output/corpus/nel.index.json`, DOI from the matching citation in
   `output/corpus/nel.corpus.json`, and summarize its corpus contribution concisely.
6. After the active groups, add `### Incompatible papers pending re-ingestion` when the
   index contains rejected incompatible packages. Explain that these packages do not
   contribute evidence, then use a two-column `Publication key` and `Status` table with
   `Pending re-ingestion` as the status.

Keep the active and pending publication sets synchronized with `papers` and `rejected`
in `output/corpus/nel.index.json`.

## Pre-release housekeeping

Before merging a release to `master`:

1. Regenerate every affected generated prompt.
2. Inspect generated prompt diffs for unintended changes.
3. Run the full unittest suite.
4. Update `NEWS.md` with user-visible changes, keeping every new bullet to 20 words or fewer.
5. Synchronize `docs/corpus.md` with `output/corpus/nel.index.json`.
6. Check `README.md`, `docs/ingest.md`, and `docs/DEVEL.md` still match current user/developer commands.
7. Set `release/VERSION` to the intended release version.
8. Review `release/skill.txt` and ensure every file required by `SKILL.md` is included.
9. Optionally build and verify the skill ZIP with `python scripts/build_skill_zip.py`.
10. Check that no private files from `pdf/`, `input/`, `work/`, `quarantine/`, `accept/`,
    `archive/`, `curation/`, or `temp/` are staged.
11. Run the full unittest suite again after final release-file changes.
12. Merge to `master` or manually run the release workflow.

## Post-release check

After the release action completes:

1. Confirm the expected GitHub tag and release exist.
2. Confirm the ZIP filename and top-level directory use the intended version.
3. Confirm the release ZIP contains only the skill payload.
4. Extract the release ZIP and smoke-test at least one `ngs-report` or `nel-demo` workflow.

## Documentation ownership

Keep documentation separated by audience:

- `README.md` — end-user installation, configuration, run management, and reporting;
- `docs/corpus.md` — current corpus contents;
- `docs/ingest.md` — corpus-curation workflow;
- `docs/workflows.md` — reporting-workflow architecture, cloning, modification, and legacy context;
- `docs/DEVEL.md` — developer and release maintenance;
- `docs/validation.md` — validation-suite reference;
- `NEWS.md` — changelog.

Do not move implementation-level retrieval or schema commentary back into `README.md`
unless an end user needs it to operate the reporting workflow.
