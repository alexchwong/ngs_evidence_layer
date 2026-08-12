# Developer guide

This file is for repository maintenance. User reporting is documented in `README.md`;
paper ingestion is documented in `INGEST.md`.

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

# Run the full test suite.
python -m unittest discover -s tests -v 2>&1
# Build a provisional skill zip package for testing
python scripts/build_skill_zip.py
```

Before release, also update `NEWS.md`, verify the documentation and corpus tables, set
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
sources only at their owning paths. In particular, source disease aliases live in
`schema/source_disease_aliases.json`; publication-type taxonomy lives in
`schema/publication_type_vocabulary.json`; Phase 3-only publication-type audit policy
lives in `prompts/assets/publication_type_audit_policy.md`. File assets are injected in
full; bundle members are embedded verbatim in full. Read `prompts/meta_prompt.md`
before changing extraction rules or schemas.

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
## Pre-release housekeeping

Before merging a release to `master`:
1. Regenerate every affected generated prompt.
2. Inspect generated prompt diffs for unintended changes.
3. Run the full unittest suite.
4. Update `NEWS.md` with the user-visible changes for the release.
5. Update the `README.md` corpus tables if corpus contents changed.
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
