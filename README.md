# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation. It converts
publications into gene-indexed evidence cards backed by private typed
evidence bundles of verbatim source fragments, then retrieves and renders a
deterministic, citable evidence block.

It collates what publications state. It does not reconcile classifiers, rank
findings, make clinical decisions, or draft a report. No model haematology knowledge
may enter evidence output.
## Setup

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
python scripts/vocab.py
python -m unittest discover -s tests -v
```
## Ingestion v0.1.3

Prompts are committed data under `prompts/`; private folder contents are workflow
state. Papers are independent and may be in flight concurrently.

```bash
# Convert queued PDFs to deterministic Markdown and resolve citations.
# Input PDFs live in `pdf/[corpus]`
# Output markdowns to `input/[corpus]`
python scripts/parse_pdfs.py --corpus <name> --mailto <email>

########
# DOI and citation retrieval
# Step 1 (DOI path): build a recovery request from citation-pending index records and
# parsed Markdown; outputs input/<name>/citations/request-<UTC>.md.
python scripts/citations.py request --corpus <name>

# Step 2 (DOI path): provide a JSON array of paper_id, title_seen, and doi entries;
# verifies each DOI via Crossref and updates valid records to ingested in the index.
python scripts/citations.py apply --corpus <name> --response <file>
# Alternative step 1 (manual path): export pending paper IDs to a citation worksheet;
# outputs input/<name>/citations/manual-<UTC>.csv for the operator to complete.
python scripts/citations.py manual-export --corpus <name>

# Alternative step 2 (manual path): provide the completed CSV worksheet;
# validates the entire batch, then stores citations and marks its records ingested.
python scripts/citations.py manual-apply --corpus <name> --csv <file>
######
# Create work/<publication-key>/paper.md and metadata.json.
python scripts/fanout.py --corpus <name>

# Run Phases 1–4 in fresh model sessions using prompts/phaseN_prompt.md,
# saving outputs directly in each paper's work folder.

# Deterministically accept one fully audited paper.
python scripts/confirm.py --key <publication-key>
# Build release artefacts from accept/ only.
python scripts/incorporate.py
```

The lifecycle is:

```text
pdf → parse/index → input → fanout → work → model phases → confirm → accept + archive → incorporate → output
```
### Pipeline directories
| Directory | Purpose |
|---|---|
| `pdf/` | Private incoming queue. Place source publications under `pdf/<corpus>/` before parsing. |
| `pdf/archive/` | Private storage for source PDFs moved after successful parsing. This leaves each incoming corpus folder containing only pending work. |
| `input/` | Private parsed corpus state under `input/<corpus>/`, including evidence Markdown, publication indexes, and citation-repair files. Model phases use the Markdown, not the original PDF. |
| `work/` | Private per-publication work in progress under `work/<publication-key>/`, including source Markdown, metadata, census, provisional packages, and independent audit files. The content-derived `paper_id` remains internal identity metadata. |
| `accept/` | Private, deterministically accepted packages. This is the only input from which `incorporate.py` builds release artefacts. |
| `archive/` | Private completed work folders retained with their source-aware model-phase files and audit trail after confirmation. |
| `output/corpus/` | Committed release corpus and index artefacts: `nel.corpus.json` and `nel.index.json`. |
| `output/reports/` | Committed incorporation reports, including `build-report.json` with accepted and rejected paper outcomes. |
The private runtime directories remain ignored by Git. Their tracked `.gitkeep` files
have no runtime meaning; they only ensure that a fresh clone contains the required
empty directory structure.

The content-derived `paper_id` provides stable internal identity from PDF checksum.
Once a citation is resolved, the human-readable `publication_key` identifies the work
folder and prefixes its card IDs. Fan-out recomputes the key and rejects index or
folder collisions before model work begins.
Each model phase has a strict, mutually exclusive output contract. Phase 1 alone
writes the census and assigns `publication_type` with a source-supported basis. Phase
2 either critiques a materially deficient census or writes the single complete
provisional package; it must preserve every source qualifier and maintain exactly one
typed evidence bundle per card. A bundle is `contiguous_text`, `composite_text`, or
`table_relation`; every fragment remains independently verbatim and locatable. Phase 3
independently audits publication type, every card/bundle pair, cross-fragment scope,
table reconstruction, and evidence laundering, then writes one complete review with a
pass/fail result for every card. Phase 4 presents every card and its review to the human,
applies the final source-supported adjudication, and alone writes `paper.final.json`.
Mandatory pre-output gates prevent a phase from overwriting its inputs or returning
another phase's artefact.
`confirm` is the last source-aware gate: it verifies every evidence fragment against `paper.md`
and validates the complete Phase 3 review, Phase 4 final audit, and final package lineage
to the independently audited provisional. Phase 4 may amend source-supported extraction
content during human adjudication. `incorporate` excludes invalid individual accepted
pairs, strips all private evidence bundles and fragment text, and writes:
```text
output/corpus/nel.corpus.json
output/corpus/nel.index.json
output/reports/build-report.json
```

There is no provisional corpus. Membership means a package completed independent audit,
human adjudication, and deterministic acceptance. See `INGEST.md` for the operator
runbook and `docs/INPUT.md` for private input metadata.
## Retrieval

Case handling has two bounded model steps. Step 1 extracts a provisional major
diagnostic category, variant genes, and structured case facts with stable `fact_id`
values into `case-input.json`. Step 3 adjudicates those facts against retrieved
diagnosis cards under `prompts/diagnostic_adjudication_prompt.md`. Steps 2, 4, and 5
are deterministic, performed by `scripts/run_case.py`.

For example, `case-input.json` may contain:
```json
{
  "provisional_disease": "myeloid neoplasm, unspecified",
  "genes": ["SF3B1"],
  "case_facts": [
    {"fact_id": "F-SF3B1", "type": "variant", "gene": "SF3B1", "vaf_percent": 30},
    {"fact_id": "F-RS", "type": "morphology", "ring_sideroblast_percent": 7}
  ]
}
```

When the stem does not specify a haematological malignancy and the NGS result contains
no variants, Step 1 instead uses the case-only disease
`no_haematological_malignancy` with `"genes": []`. This term is not a legal evidence-
card disease and cannot be used during ingestion.

```bash
python scripts/run_case.py diagnosis --work-dir <work-dir>
# Run a fresh model session with <work-dir>/step2.json and
# prompts/diagnostic_adjudication_prompt.md, saving <work-dir>/adjudication.json.

python scripts/run_case.py full --work-dir <work-dir>
```

The wrapper writes `<work-dir>/bundle.json` and `<work-dir>/block.md`. The sole final
artifact is `<work-dir>/block.md`; `bundle.json` is an internal deterministic
intermediate. If no working directory is supplied, `run_case.py` creates a retained
secure system temporary directory and prints it to stderr.
Advanced callers may still invoke `scripts/retrieve.py` directly:

```bash
python scripts/retrieve.py diagnosis \
  --case-input <work-dir>/case-input.json \
  --output <work-dir>/step2.json

python scripts/retrieve.py full \
  --diagnosis-result <work-dir>/step2.json \
  --adjudication-result <work-dir>/adjudication.json \
  --output <work-dir>/bundle.json

python scripts/render.py --bundle <work-dir>/bundle.json --output <work-dir>/block.md
```
The legacy `retrieve.py diagnosis` flags (`--genes`, `--provisional-disease`,
`--case-facts`, `--corpus`, `--index`) remain available as advanced overrides.
Diagnosis retrieval is gene-based and returns all matching diagnosis cards without a
disease filter. The adjudicator may compose multiple supplied patient facts against a
card's source-stated criteria, but may not add criteria or facts from model knowledge.
Missing required facts are `unknown` and fail closed as `indeterminate`. A card's
legacy `escalates_to` value remains provenance and is not a runtime decision gate.
The validated adjudication distinguishes the source-supported specific
`diagnostic_label` from the closed case-level `refined_disease`. The latter is the
major category used mechanically by full retrieval. For prognosis, treatment, and
biomarker cards, Step 4 retrieves gene-matched cards when their exact `diseases`
contain either the reviewed case disease or a direct category-specific disease listed
under that case disease in `retrieval_related`; legacy cards with an empty disease
array remain disease-unspecified, and germline remains gene-only. Related
retrieval is directional and non-transitive. Thus a `post-PV/post-ET MF` case may
retrieve configured PMF and MPN evidence without changing the source-grounded disease
context stored on those cards.
A changed major category is rejected unless every required criterion is met and cites
both retrieved diagnosis cards and supplied case facts. Genes the corpus cannot
address are named rather than answered from model memory.
Card `diseases` continue to contain only source-grounded exact clinical applicability.
`disease_ancestors` remain deterministic direct and transitive parents from
`schema/disease_vocabulary.json`; incorporation uses them for broad corpus indexing
without making a subtype card clinically applicable to its parent categories.
`umbrella` is not used for retrieval expansion. `diseases_covered` likewise remains
the union of exact card diseases only. The independent `retrieval_related` map controls
case-time evidence borrowing without changing card applicability or taxonomy.
Private evidence bundles never enter retrieval or rendered output. Every rendered
interpretation is traceable to its cards and deterministic citations through the
end-of-document `## Refs` card-to-reference map and the numbered `## References`
bibliography.
## Boundaries
- PDF conversion is an input-layer operation; Markdown alone is the archived evidence
  path and no card or model phase cites or reads a PDF.
- Crossref is used only to resolve a detected DOI; model-assisted repair supplies a
  DOI candidate that is re-resolved and recorded with provenance.
- Closed evidence-card disease vocabulary with separate case-only disease options,
  cycle-checked taxonomy ancestors, and directional category-specific retrieval
  relationships.
- Different publications coexist even when they disagree.
- No live databases, approval-status modelling, cross-publication deduplication, or
  clinical synthesis.
- Reporting-rule, vocabulary, or extraction-schema changes require re-ingestion,
  not a mechanical migration.
