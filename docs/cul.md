# Corpus user layer (CUL)

The CUL customises the corpus for a user or a run **without editing it**. It never
writes `accept/`, `archive/` or `output/corpus/`. Profiles live in
`config/cul/<name>.json`, are user-owned, and are resolved and frozen at run
setup.

It replaces the standalone `output/corpus/blacklist.json`, which is now a
deprecated fallback.

## Quick start

```bash
# See what exists.
python scripts/cul.py list

# Create a profile seeded from the default retrieval scope.
python scripts/cul.py new --cul alice-mds --description "MDS reporting"

# Review and edit cards, then download the profile from the browser.
python scripts/build_card_browser.py --cul alice-mds
open output/reports/card-browser.html      # switch to Edit, then Download profile

# Install the downloaded profile and inspect what it changes.
python scripts/cul.py apply --from ~/Downloads/alice-mds.json
python scripts/cul.py diff --cul alice-mds

# Run against it.
python nel.py setup --mode ngs-report --case case.md --cul alice-mds
python nel.py run --run-id <id>
```

## What a profile may change

| Class | Fields | Effect | Disclosed in the report |
|---|---|---|---|
| Reachability (`scope`) | paper / category / gene / card include and exclude | which cards retrieval can reach | no |
| Classification (`amendments`) | `category`, `evidence_tier`, `genes`, `diseases` | which cases a card is reached for | no |
| Assertion (`amendments`) | `interpretation` | what the card states | **yes** |

`card_id`, `publication_key`, `locator` and every citation field are not
editable. They bind a card to its source.

**A profile cannot create cards.** An amendment must name a card that already
exists in the corpus. An invented card would render under a real citation with no
locator and no evidence behind it. New evidence is ingestion's job: see
[`ingest.md`](ingest.md).

`category`, `evidence_tier` and `diseases` are closed value sets, validated
against `schema/ingestion_package_schema.json` and
`schema/disease_vocabulary.json`. Evidence tiers, strongest first, are
`guideline criterion`, `multivariable-adjusted`, `univariable or descriptive` and
`restated secondary`. `disease_ancestors` is recomputed from the vocabulary
automatically. Unrecognised genes are allowed, because gene lists are
legitimately open.

The browser's edit controls read the same value sets from the build payload, so
an edit that `cul.py` would reject cannot be composed in the browser.

## Disclosure

Only an amended `interpretation` appears in the report. The reference entry for
the affected paper names the amended cards and the profile:

```text
References:
1. Weeks LD, Niroula A, Neuberg D, et al. Prediction of Risk for Myeloid
   Malignancy in Clonal Hematopoiesis. NEJM Evidence. 2023 May;2(5).
   (NB: custom corpus edit used — profile "alice-mds": C0001)
```

A reference commonly backs several cards from the same paper. Naming the amended
ones stops the note from reading as an objection to the whole citation.

Scope and classification changes are not disclosed per statement: they alter which
cards are reached, never what a card says. The active profile and its digest are
recorded in the run manifest.

## Staleness

Each amendment records `base_sha256`, the digest of the corpus card it was
authored against. When a redo changes that card, the amendment goes **stale**: it
stops applying, and `nel.py setup` refuses to start.

```bash
python scripts/cul.py check --cul alice-mds
```

Re-edit the card in the browser against its new text, or remove the amendment.
This is deliberate. An amendment written against text that no longer exists is
not safe to reapply silently.

## Freezing and runs

`nel.py setup --cul <name>` resolves the profile and writes
`runs/<id>/run-config/cul.json`, recording `cul_profile` and `cul_sha256` in the
run manifest. Every `nel.py run` re-verifies that frozen layer, so editing a
profile mid-run cannot change what an in-flight run retrieves.

To change a run's layer deliberately:

```bash
python nel.py run --run-id <id> --cul other-profile
```

The swap is appended to `cul_history` in the manifest and announced. Earlier
stages keep evidence drawn under the previous layer, so prefer a new run.

Workflow executors accept the same selector directly:

```bash
python workflows/proforma_v1/self.py run --work-dir <dir> --cul alice-mds
```

## Card browser

```bash
python scripts/build_card_browser.py                  # corpus-only
python scripts/build_card_browser.py --cul alice-mds  # preload a profile for editing
python scripts/build_card_browser.py --full           # add accepted evidence where available
```

The browser is built from `output/corpus/` alone and needs no `accept/` or
`archive/`. `--full` adds the accepted evidence block **per paper**: a paper
without an accepted package renders corpus-only and quietly; a paper whose
accepted package disagrees with the incorporated corpus renders corpus-only with
a warning badge, because that is a real sync defect and should not look like a
clean release checkout. Re-run `incorporate.py` when that appears.

Search accepts free text, not just keywords:

```text
adverse prognosis          all terms, ranked by closeness
"clonal hematopoiesis"     literal phrase
prognosis -germline        exclude a term
gene:TP53 cat:treatment    field-scoped; also disease: paper: tier: id: locator:
```

Edit mode uses three panes: filters on the left, the editor in the centre, the
card list on the right. Each row in the card list has a tickbox controlling
whether retrieval can reach that card, and clicking the row opens it in the
editor. Browse mode is unchanged.

**Scope is a hybrid model.** Paper and category rules stay rules: they are
compact and they keep applying to cards a later redo adds. Tickboxes only ever
write card-level `exclude` entries on top of those rules. A card suppressed by a
rule is shown ticked-off and locked, naming the rule, so a three-rule profile can
never be silently expanded into a hundred card IDs.

Filter on the left, then use "Exclude N shown" to remove the filtered set. The
button states how many cards it will affect. When the filtered set happens to be
exactly one paper, or one category within a paper, the browser offers to write a
rule instead, which stays compact and covers cards added later.

"Review changes" opens a summary in three parts: retrieval rules, individually
excluded cards, and card amendments, with a reminder that only interpretation
amendments reach the report.

Within the editor, interpretation sits on the left and classification on the
right:
`category` and `evidence_tier` as dropdowns of their closed vocabularies,
`diseases` as a filtering token field over the 162-term vocabulary, and `genes`
as free text. The corpus value is shown beneath any field that differs from it,
so an amendment always displays what it replaced. Amended and stale cards are
marked, and each offers a per-card revert. Every profile in `config/cul/` is embedded at build time, so the profile
dropdown switches between them without a rebuild. **Open file** loads a profile
from anywhere on disk.

Saving is download-only. A page opened from `file://` is not a secure context, so
no browser API can overwrite a file in place, and whether a download replaces
`alice-mds.json` or becomes `alice-mds (1).json` is the browser's decision.
`cul.py apply --from <file>` is the write path: it validates the profile, refuses
stale amendments, and replaces the named profile atomically.

When no `--cul` is given, the browser preloads the `default` profile if one
exists, so downloading from a fresh page cannot silently drop the shipped
retrieval rules.

## Promotion to the accepted corpus

A CUL amendment is a user layer, not a corpus correction. When an amended
interpretation should become the accepted text, take it through the normal
accepted-card review — `prepare_redo.py cards` and Phase 2R → 3 → 4 — and remove
the amendment once the paper is re-accepted. A profile that permanently
contradicts `accept/` means the audited corpus is drifting out of use.

## Migrating from blacklist.json

`config/cul/default.json` ships with the historical `blacklist.json` scope, so
retrieval behaviour is unchanged. If no profile is named, the default profile
applies. An installation with neither falls back to `blacklist.json` and warns.
`blacklist.json` and `scripts/build_blacklist.py` are deprecated and will be
removed.
