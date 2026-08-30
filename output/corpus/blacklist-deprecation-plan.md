# Proposed plan to deprecate the legacy blacklist

## Status

Proposed.

## Summary

The corpus user layer (CUL) supersedes the standalone blacklist as the source of
card-retrieval scope. The shipped `config/cul/default.json` profile preserves the
historical retrieval policy and also supports per-user scope and card amendments.

The legacy blacklist cannot yet be removed as a single, isolated file deletion.
Several workflows still call the legacy API directly, and a missing
`output/corpus/blacklist.json` is intentionally interpreted as an empty,
permissive policy. Removing the file before migrating those callers would
silently make every corpus card reachable. The deprecation must therefore happen
in stages, ending with removal of both the legacy assets and compatibility code.

## Goals

1. Make CUL profiles the sole source of retrieval scope for supported workflows.
2. Preserve the current default retrieval behavior during migration.
3. Remove the obsolete YAML-to-JSON blacklist authoring toolchain.
4. Remove the standalone blacklist runtime fallback after all callers migrate.
5. Make missing required CUL configuration fail clearly rather than silently
   broadening retrieval.
6. Retain and rename the generic scope-policy logic used by CUL.

## Non-goals

- Changing the scope encoded by `config/cul/default.json`.
- Changing corpus cards in `accept/`, `archive/`, or `output/corpus/`.
- Removing historical blacklist references from old run logs.
- Replacing CUL amendments or their staleness and disclosure behavior.

## Current state and risk

The same historical policy currently exists in two forms:

- `config/cul/default.json`, the new authoritative CUL profile;
- `output/corpus/blacklist.json`, the legacy runtime policy.

The legacy file is still read through `scripts/core/corpus.py` by direct callers
in historical and supported workflows. In particular, callers use
`corpus.blacklist_cards(cards, corpus.DEFAULT_BLACKLIST)`.

`load_blacklist()` treats a missing file as an enabled empty policy for backward
compatibility. Consequently, deleting `blacklist.json` before caller migration
does not fail loudly: legacy workflows allow all cards. A regression comparison
demonstrated the effect on the current corpus:

- default CUL profile: 672 of 789 cards reachable;
- missing legacy blacklist: 789 of 789 cards reachable.

This silent broadening of retrieval is the principal migration risk.

## Phase 1: retire the legacy authoring toolchain

The following files can be removed without removing the temporary runtime
compatibility policy:

- `output/corpus/blacklist.yaml`;
- `scripts/build_blacklist.py`;
- `tests/test_build_blacklist.py`;
- `output/corpus/prompts/modify_blacklist.md`.

Required follow-up changes:

- remove blacklist regeneration instructions from `docs/DEVEL.md`;
- remove `build_blacklist.py` from `scripts/README.md`;
- update `tests/test_workflow_prompts.py` so it no longer requires
  `modify_blacklist.md`;
- direct users to `scripts/cul.py` and the card browser for scope editing;
- retain `output/corpus/blacklist.json` temporarily as a read-only compatibility
  snapshot.

After this phase, `config/cul/default.json` is the editable source of default
scope. The legacy JSON must not be edited or regenerated.

## Phase 2: migrate runtime callers to CUL

Inventory every direct use of:

- `corpus.DEFAULT_BLACKLIST`;
- `corpus.load_blacklist()`;
- `corpus.blacklist_cards()`;
- direct reads of `output/corpus/blacklist.json`.

Known callers include terraced workflow versions and categorical retrieval. Each
supported workflow must resolve or load a CUL layer and use the active/frozen
layer during retrieval. The filtering path should be equivalent to:

```python
allowed, amended = cul_core.eligible_cards(cards, layer)
```

For run-based workflows, the layer must be resolved at setup, frozen into the run
configuration, included in the run manifest by profile and digest, and verified
on resume. A profile change must not silently alter an in-flight run.

For older workflows, choose and document one of two outcomes:

1. migrate the workflow to CUL; or
2. declare the workflow archived and outside the supported runtime surface.

At minimum, every currently supported entry point must be migrated before the
legacy JSON is removed. Tests and mocks that patch `blacklist_cards()` must be
updated to exercise the CUL path instead.

## Phase 3: remove the fallback

Once supported callers use CUL, remove the legacy fallback from `nel.py`.
Specifically:

- remove the branch in `_resolve_cul()` that constructs a compatibility layer
  from `blacklist.json`;
- remove `corpus_core_blacklist_path()`;
- make an explicitly requested unknown profile an error;
- make a missing shipped `default` profile an installation/configuration error.

The safe final behavior is:

- no `--cul` selection: load `config/cul/default.json`;
- explicit `--cul NAME`: load `config/cul/NAME.json`;
- required profile absent or invalid: stop with an actionable error;
- never substitute an empty permissive scope for missing configuration.

## Phase 4: simplify and rename policy code

After callers migrate, remove legacy file-specific interfaces from
`scripts/core/corpus.py`:

- `DEFAULT_BLACKLIST`;
- `load_blacklist()`;
- `blacklist_cards()`.

Do not remove the underlying policy engine used by CUL. Scope still requires
normalization and filtering by paper, category, gene, and card. Rename legacy
blacklist terminology to describe its current generic purpose, for example:

| Legacy name | Proposed name |
|---|---|
| `_normalise_blacklist_rule()` | `_normalise_scope_rule()` |
| `apply_blacklist()` | `apply_scope()` |
| blacklist validation labels | scope validation labels |

Keep generic helpers such as the empty policy, rule normalization, dimension
matching, and rule application. Update `cul_core.eligible_cards()` to call the
renamed scope API.

This refactor should be behavior-preserving and can be performed separately from
caller migration if that makes review safer.

## Phase 5: update the test strategy

The CUL test suite currently compares the shipped default profile with the
standalone blacklist file. That is useful during migration but cannot remain
after the legacy file is removed.

Replace the filesystem-dependent equivalence assertion with fixture-based tests
that verify default-scope behavior. The fixture should include representative
cards for the three historical paper rules:

- `d-hner-2022-blood-140-1345`: exclude `biomarker`;
- `khoury-2022-leukemia-36-1703`: include only `diagnosis`;
- `arber-2022-blood-140-1200`: include only `diagnosis`.

Do not rely only on a total such as 672 reachable cards, because normal corpus
growth can change that count. Assert representative included and excluded card
behavior or an explicit fixture card-ID set.

Additional test changes:

- remove `tests/test_build_blacklist.py` in Phase 1;
- migrate or rename `tests/test_retrieve_blacklist.py` to test generic CUL scope
  normalization and application;
- update workflow tests and mocks to provide a CUL layer rather than patching
  `blacklist_cards()`;
- test that a missing default profile fails loudly after fallback removal;
- test that the default CUL profile and a frozen copy produce identical results;
- retain tests for profile validation, amendment staleness, digest binding, and
  report disclosure.

All repository tests must pass with `output/corpus/blacklist.json` physically
absent before its deletion is committed.

## Phase 6: remove final legacy assets and update documentation

After runtime migration and fallback removal, delete:

- `output/corpus/blacklist.json`.

The other legacy files should already have been removed in Phase 1.

Update documentation and release notes:

- `docs/corpus.md`: remove `blacklist.json` from runtime corpus assets and name
  CUL as the retrieval-scope mechanism;
- `docs/cul.md`: replace fallback instructions with the final profile resolution
  and missing-profile behavior;
- `docs/DEVEL.md`: remove YAML generation instructions;
- `scripts/README.md`: remove the generator entry;
- `NEWS.md`: state whether the legacy files are deprecated or fully removed for
  the release being prepared.

Historical logs may retain their original blacklist messages because they record
past execution accurately.

## Validation gates

Each phase should satisfy the following gates before proceeding:

### Phase 1 gate

- CUL profile creation and editing are documented and usable.
- No test or documentation requires the YAML generator or modification prompt.
- The compatibility JSON remains present for unmigrated callers.

### Phase 2 gate

- All supported workflow entry points use active or frozen CUL layers.
- Repository search finds no supported runtime call to `blacklist_cards()`.
- Default-scope retrieval remains unchanged.
- Resume behavior verifies the frozen CUL digest.

### Phase 3 and 4 gate

- Missing default CUL configuration fails with an actionable error.
- No runtime code reads `output/corpus/blacklist.json`.
- Generic CUL scope tests cover include, exclude, global, and paper-specific
  semantics.

### Final removal gate

- Delete or temporarily move `output/corpus/blacklist.json` before testing.
- Run the complete unittest suite in the repository `.env` environment.
- Run supported workflow smoke tests with the default profile and at least one
  named profile.
- Confirm default reachability and report output are unchanged.
- Search the maintained source, tests, and documentation for remaining runtime
  blacklist dependencies.

## Rollback

Before final removal, rollback consists of retaining the read-only compatibility
JSON while fixing a missed caller. Do not restore the YAML authoring path unless
CUL itself is being abandoned.

After final removal, rollback should restore the previous release rather than
silently adding permissive behavior. Missing CUL configuration must remain a hard
error.

## Completion criteria

The legacy blacklist is fully retired when all of the following are true:

1. `config/cul/default.json` is the only shipped default retrieval-scope policy.
2. Supported workflows use CUL and bind runs to a profile digest.
3. No maintained runtime code reads `output/corpus/blacklist.json`.
4. The blacklist YAML, generator, modification prompt, JSON, and dedicated
   generator tests are removed.
5. Generic scope logic remains tested under CUL-neutral names.
6. Missing required profile configuration fails loudly.
7. The complete unittest suite and supported workflow smoke tests pass without
   any legacy blacklist file present.