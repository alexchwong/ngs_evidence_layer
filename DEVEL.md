# Developer guide

This file is for repository maintenance. User reporting is documented in `README.md`;
paper ingestion is documented in `INGEST.md`.


## Reporting workflow architecture

Phase 2 promotes `diagnosis-first-v1` as the default workflow while retaining `legacy-v1` as an explicit selectable pipeline. Root `SKILL.md` is a router backed by `workflows/registry.json`; the work directory is bound once through `scripts/setup_workflow.py`, which writes `<work-dir>/workflow.json`. Subsequent deterministic commands read that state rather than inferring workflow identity from evidence files.

Workflow-owned strategy lives under `workflows/diagnosis_first_v1/` and `workflows/legacy_v1/`, including orchestration prompts and retrieval selection policy. Canonical reporting/citation prompts, corpus/blacklist/tag mechanics, rendering, validation, and packaging infrastructure remain shared. `scripts/retrieval_core.py` contains shared retrieval mechanics; each workflow's `retrieval.py` owns its selection algorithm.

Create an isolated experimental workflow with:

```bash
python scripts/devel_workflow.py new --from diagnosis-first-v1 --name <new-workflow-id>
python scripts/devel_workflow.py check <new-workflow-id>
```

The helper clones only the workflow-owned tree, updates its identifiers/import paths, registers it without changing the default, and leaves shared contracts referenced in place. Promotion to default remains a deliberate edit of `workflows/registry.json`.

## Quick start

From the repository root, create the local environment once:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```

Activate it in each new shell, then run the normal development checks:

```bash
. .env/bin/activate
# Regenerate any prompt affected by canonical template, asset, rule, vocabulary, or schema changes.
python scripts/build_prompts.py --phase <1|2|3|4|5>
python scripts/build_prompts.py --phase5-review

# Regenerate runtime JSON after editing output/corpus/blacklist.yaml.
python scripts/build_blacklist.py

# Run the full test suite.
python -m unittest discover -s tests -v 2>&1

# Build a provisional skill zip package for testing
python scripts/build_skill_zip.py
```

Before release, also update `NEWS.md`, verify the documentation and current-corpus
summary, set
`release/VERSION`, review `release/skill.txt`, and confirm that no private ingestion files
are staged. See [Pre-release housekeeping](#pre-release-housekeeping) for the complete
checklist.
## Development setup

From the repository root:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```
## Regenerate ingestion prompts

The committed Phase 1–5 prompts are generated artefacts.

Edit phase-specific prose under:

```text
prompts/templates/
```

Shared prompt prose lives under `prompts/assets/`. `prompts/assets/manifest.json` maps
each `{{ASSET_KEY}}` used by a template to either one complete canonical file or a
bundle of complete files. `scripts/build_prompts.py` is a generic renderer: adding or
moving a prompt asset should require a manifest edit and template marker, not new
phase-specific Python dispatch.

Edit rules, vocabularies, schemas, executable validation code, and other canonical
sources only at their owning paths. In particular, canonical disease names, source aliases, taxonomic parents, and
retrieval relationships live together in `schema/disease_vocabulary.json`;
publication-type taxonomy lives in
`schema/publication_type_vocabulary.json`; Phase 3-only publication-type audit policy
lives in `prompts/assets/publication_type_audit_policy.md`. Phase-specific online
validators live under `scripts/phase_validation/`: the prompt manifest injects the
relevant Phase 1, 2, 4, or 5 validator, while Phase 3 has no executable prompt validator
and is checked by Phase 4 on entry. `scripts/final_validation.py` remains the local
compatibility CLI for Phases 1–4 and dispatches to the canonical phase validators. File
assets are injected in full; bundle members are embedded verbatim in full. Read
`prompts/meta_prompt.md` before changing extraction rules or schemas.

Regenerate the affected prompt:
```bash
python scripts/build_prompts.py --phase 1
python scripts/build_prompts.py --phase 2
python scripts/build_prompts.py --phase 3
python scripts/build_prompts.py --phase 4
python scripts/build_prompts.py --phase 5
python scripts/build_prompts.py --phase5-review
```

The canonical Phase 5 sources are:

```text
prompts/templates/phase5_prompt.md
prompts/templates/phase5_review_prompt.md
```

The generated committed outputs are:

```text
prompts/phase5_prompt.md
prompts/phase5_review_prompt.md
```
Do not edit generated phase prompts directly. Edit the corresponding template or other
canonical source, regenerate the prompt, inspect the diff, and commit the generated
prompt with its source change.

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
0.1.6
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
the finished ZIP contains exactly the resolved manifest contents.
Build and verify the skill ZIP locally from the repository root with:

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

### README current-corpus listing

The `README.md` `Current corpus` section must use this structure:

1. Open with the current release version and total number of active publications.
2. State that publications are grouped by `latest_accepted_in_version` from
   `output/corpus/nel.index.json`.
3. Group active publications under `### Last modified in vX.Y.Z` headings, newest
   version first.
4. Under each version heading, use a four-column table in this exact order:
   `Publication key`, `DOI`, `Paper nickname`, `Contribution to corpus`.
5. List each active publication exactly once. Use the publication key and metadata from
   `output/corpus/nel.index.json`, and summarize its corpus contribution concisely.
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
4. Update `NEWS.md` with the user-visible changes for the release, keeping every new
   bullet point to 20 words or fewer.
5. Update the `README.md` current-corpus summary and listing if corpus contents changed,
   following the format above.
6. Check `README.md`, `INGEST.md`, and `DEVEL.md` still match current user/developer commands.
7. Set `release/VERSION` to the intended release version.
8. Review `release/skill.txt` and ensure every file required by `SKILL.md` is included.
9. (Optional) Build and verify the skill ZIP with `python scripts/build_skill_zip.py`. Test this locally or via Claude/ChatGPT
10. Check that no private files from `pdf/`, `input/`, `work/`, `quarantine/`, `accept/`,
    `archive/`, `curation/`, or `temp/` are staged.
11. Run the full unittest suite again after final release-file changes.
12. Merge to `master` or manually run the release workflow.
## Post-release check

After the release action completes:

1. confirm the expected GitHub tag and release exist;
2. confirm the ZIP filename and top-level directory use the intended version;
3. confirm the release ZIP contains only the skill payload;
4. extract the release ZIP and smoke-test at least one `ngs-report` or `nel-demo` workflow.
## Documentation ownership

Keep documentation separated by audience:

- `README.md` — end-user NGS reporting and current corpus contents;
- `INGEST.md` — corpus-curation workflow;
- `DEVEL.md` — developer and release maintenance;
- `NEWS.md` — changelog.

Do not move implementation-level retrieval or schema commentary back into `README.md`
unless an end user needs it to operate the reporting workflow.
