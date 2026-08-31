# NEWS
## 0.3.0
- Added the corpus user layer (CUL): per-profile, non-destructive corpus customisation in `config/cul/<name>.json` that never modifies `accept/`, `archive/` or `output/corpus/`.
- CUL profiles may amend `interpretation`, `category`, `evidence_tier`, `genes` and `diseases` on existing cards, and may scope retrieval by paper, category, gene or card. Card creation is not supported.
- Amendments bind to the corpus card they were authored against; a card changed by a redo makes its amendment stale, which blocks run setup until reviewed.
- An amended interpretation is disclosed in the report reference list, naming the profile and the affected card IDs. Scope and classification changes are not disclosed per statement.
- `nel.py setup --cul` and `nel.py run --cul` select a profile; the resolved layer is frozen into `runs/<id>/run-config/cul.json` and digested into the run manifest, and is re-verified on every resume.
- `workflows/proforma_v1/step.py` and `self.py` accept `--cul`, and the card-identity manifest records the active profile and digest.
- Added `scripts/cul.py` with `list`, `show`, `new`, `check`, `diff` and `apply`.
- `config/cul/default.json` reproduces the previous `blacklist.json` retrieval scope exactly; `output/corpus/blacklist.json` and `scripts/build_blacklist.py` are deprecated.
- The read-only card browser is built from `output/corpus/` alone. `--full` uses the same browser with accepted evidence/mapping/provenance, requires matching `accept/*.final.json` packages, and does not read or require `archive/`.
- Restored the read-only card-browser interface and removed edit mode from `build_card_browser.py`. Both normal and `--full` browser modes now include a per-card `Copy citation` control.
- Fixed: the Corpus User Layer editor's opening view rendered in browse mode, so the card list showed editor controls until the first filter click. Edit mode is now set at declaration and applied before the first render rather than corrected afterwards.
- Added scope-level `exemptions`: a card named there is readmitted despite the category, gene or paper rules that would suppress it, leaving the rule intact for every other card. Precedence is explicit exclusion, then exemption, then rules. Reported separately by `cul.py check`, `cul.py diff` and the editor.
- The editor's left rail now lists every retrieval rule with a checkbox to disable it and a control to remove it, and a form to create new rules from paper, dimension, mode and values, previewing how many cards a rule would remove before it is added.
- Rule-suppressed cards are no longer locked in the card list: ticking one writes an exemption.
- `cul.py --edit` builds the Corpus User Layer editor, opens it, and installs profiles as they are saved by watching the downloads directory (`~/Downloads` by default, overridable and remembered). `cul.py edit` remains a backward-compatible alias and `cul.py apply --from` remains the manual install path.
- The editor is now a separate artefact at `config/cul/corpus-user-layer.html`, owned by `cul.py` and gitignored, distinct from the read-only `output/reports/card-browser.html` that incorporation regenerates. It carries its own title and has no browse mode.
- Installing a profile refreshes the editor so it appears in the dropdown; a failed refresh warns rather than failing the install.
- Removed edit/CUL handling from `build_card_browser.py` entirely. The standalone editor is rendered directly by `cul.py --edit`; every valid profile is embedded and the editor starts on `default` when available.
- Fixed: loading a profile from the browser dropdown replaced the underlying state but left the profile name and counters showing the previous profile, so a subsequent download used the wrong name.
- The profile bar now summarises reachable cards, rules, exclusions, amendments and unsaved state, and the dropdown reflects the profile currently loaded.
- Fixed: filtering while in edit mode rendered the editor controls into the right-hand card list. All rendering now routes through a single mode-aware function.
- The Corpus User Layer editor uses three panes: filters, editor, and a card list whose tickboxes control retrieval scope, replacing hand-edited scope JSON.
- Scope editing is hybrid: paper and category rules stay rules, tickboxes write only card-level exclusions, and rule-suppressed cards are shown locked. Bulk exclusions that match a whole paper or category offer promotion to a rule.
- "Review changes" summarises retrieval rules, individually excluded cards, and card amendments in one panel.
- Profiles in `config/cul/` are embedded when `cul.py --edit` builds the editor and are switchable from a dropdown; profiles can also be loaded from a file. Saving remains download-plus-`cul.py apply`, since a page opened from disk cannot overwrite files in place.
- The disease picker now lists the full schema vocabulary in alphabetical order.
- Card editing places the interpretation and its classification side by side, with `category` and `evidence_tier` as closed dropdowns, `diseases` as a filtering token field over the disease vocabulary, and the corpus value displayed beneath any amended field.
- CUL now validates `evidence_tier` against the ingestion schema enum rather than accepting any string.

## 0.2.5
- Added root `nel.py` setup, run, status, configuration checks, and run inventory for the then-current product workflow.
- Moved user-editable settings and provider pipelines to root configuration while leaving the then-current implementation files unchanged.
- New runs now live under gitignored root `runs/<run-id>/` with frozen per-run configuration and corpus provenance.
- Added artifact-derived incomplete-run grouping, including diagnosis, PTBG, evidence review, report synthesis, and completion states.
- Simplified root README and SKILL documentation to the then-current product interface; legacy workflow guidance moved to developer documentation.
- Release payloads were narrowed to the then-current product implementation and smoke-tested root setup in an isolated extracted archive.
- Expanded the active corpus from 12 to 19 publications with germline guidance, TP53 evidence, CCUS, and MPN prognostic models.
- Case structuring now records NGS completeness and deterministically materializes assayed genes with no detected variants.
- Model pipelines now support reusable aliases and OpenRouter provider routing with explicit fallback control.
- Diagnostic evidence retrieval now supports configurable paper include/exclude strategies.
- PTBG proformas now separate disease-specific variant effects from framework-level conclusions and use disease-scoped evidence retrieval.
- Prognosis now deterministically groups same-framework findings and suppresses only fully overlapping accepted-card restatements.
## 0.2.4
- Promoted the then-current reporting workflow to default, with native session-model execution and retained staged provider pipelines.
- Added independent WHO5, ICC, and second-WHO5 diagnosis passes before downstream prognosis, treatment, MRD, and germline reasoning.
- Deferred card assignment until shared evidence resolution, followed by independent audit and cropped disagreement adjudication.
- Added deterministic dissent rendering for evidence disagreements and adjudication outcomes.
- Native-self runs now default to system temporary storage; `->project` retains runs under repository `temp/`.
- Rebuilt the active corpus to 12 publications accepted under version 0.2.4.
- Added the consolidated ten-case `nel-validate-brief` end-to-end regression suite.
- Owner proformas now strip premature card tags and allow multiple supporting cards per reason after evidence resolution.
## 0.2.3
- Strengthened `terraced-v1` negative-statement gating with an exhaustive per-fact reportability classification contract and deterministic quarantine derivation. Resuming an older work directory without `synthesis/reportability-classification.yaml` reruns the reportability stage before synthesis.
- Added `WORKFLOW.md` documenting workflow isolation, cloning, modification, validation, and promotion.
- Refactored shared workflow scripts for better separation of workflows. Note `prompt/workflow/` prompts remain shared between workflows.
- Expanded the active corpus from 12 to 29 publications across diagnosis, prognosis, treatment, MRD, CHIP, CCUS, and germline evidence.
- Diagnosis-first rule drafting now supports multiple atomic statements per rule with statement-level citations.
- Diagnosis-first reporting suppresses generic negative or not-applicable statements unless their absence materially changes interpretation.
- Bundled the canonical NGS panel-scope definition required during workflow setup.
- Replaced Phase 5 with accepted-card review inside the standard Phase 2–4 workflow.
- Added collision-safe per-phase attempt filenames while retaining legacy archive filename compatibility.
- Simplified redo preparation to census, provisional, and cards restoration modes without card edit allowlists.
## 0.2.2
- Made `diagnosis-first-v1` the default reporting workflow while retaining `legacy-v1` through explicit selectors.
- Bound each work directory to a registered workflow so deterministic commands cannot silently switch pipelines.
- Added developer tooling to clone and check isolated experimental workflows without changing the default.
- Expanded the corpus to 12 publications with IPSS-M and germline predisposition guidance.
- Added function-targeted validation cases for specific AML, MDS, MPN, CMML, and germline reporting behaviours.
- Modularized workflow-specific retrieval and reporting logic while retaining shared citation, validation, rendering, and packaging infrastructure.
## 0.2.1
- Expanded the corpus to nine publications, adding WHO-HAEM5 lymphoid classification and reprocessing key ICC and ELN-DAVID sources.
- Centralized lymphoid and myeloid disease vocabulary support while separating broad case-major categories from refined disease terms.
- Added optional category-scoped Phase 1 ingestion, with confirmed scope persisted in `census.json` and respected downstream.
- Tightened Phase 1 claim atomicity and Phase 2 compatibility rules to reduce merged, independently reviewable claims.
- Refactored reporting workflow prompts into step-specific files while retaining shared orchestration in `SKILL.md`.
- Simplified evidence hand-offs using `diagnostic_evidence.md`, `evidence.md`, compact card tags, and richer internal JSON for deterministic processing.
- Strengthened report citation invariants and deterministic validation, including model-facing repair messages that identify the exact rule, line, or citation problem.
- Made variant summaries mandatory, separated patient findings from cited interpretations, and added assertive, qualification-preserving `REPORT:`/`OMIT:` drafting.
- Added a user-editable retrieval blacklist with YAML include/exclude rules for papers, categories, and genes, plus an LLM-assisted editing prompt.
- Refactored retrieval rendering to group evidence by paper, evidence tier, and disease while reducing redundant model-facing metadata.
- Updated `nel-validate` packaging so marking runs can be scored separately and debugging intermediates are packaged independently.
- Improved release/developer documentation and generated-artifact ownership rules.
## 0.2.0
- Rebuilt the active corpus around eight key publications re-ingested under 0.2.0 instead of carrying the 0.1.x corpus forward.
- Refactored ingestion around phase-specific prompt contracts.
  - Phase 1 performs an exhaustive claim census.
  - Phase 2 reviews claims evidence-first, retaining only directly supported, clinically useful interpretations as cards.
  - Phases 3 and 5 apply audit-focused review standards.
  - Phases 4 and 5 apply card-construction and adjudication standards.
- Modularized ingestion prompts into reusable assets and phase templates.
- Added phase-specific deterministic validation from `scripts/phase_validation/` where required.
- Expanded the census/card model to preserve distinct claims sharing the same gene and category.
- Added source-supported diagnosis and treatment cards without gene associations.
- Added complete Phase 1 and Phase 2 redo workflows for accepted papers.
- Redo workflows preserve superseded accepted state in `archive/`.
- Phase 5 remains available for focused post-acceptance additions and selected card revisions.
- Added operator-confirmed paper nicknames during Phase 4.
- Propagated `paper_nickname` into accepted corpus metadata.
- Expanded disease-vocabulary aliases for full disease names, including primary myelofibrosis mapped to PMF.
- Replaced validation cases with a clinician-authored 22-case set covering AML, MDS, and MPN/CMML differentials.
- Validation cases also cover variant-specific diagnostic support and possible germline predisposition.
- Improved transport and accepted-paper versioning for moving or reprocessing private intermediate state and updated corpus papers.
- Preserved prior accepted history when moving or reprocessing papers.
## 0.1.8
- Hardened diagnostic adjudication so each criterion assessment cites diagnosis evidence and non-unknown decisions also cite supplied case facts.
- Reports now state the WHO-5 diagnosis and separately assess ICC, reporting ICC when it is materially different.
- Reworked Step 6 citation handling around exact card-ID markers with deterministic validation and Vancouver citation/reference rendering.
- Refactored the default report-formatting prompt into clearer source, variant-summary, diagnosis, content-selection, and citation rules.
- Expanded Phase 5 to revise or delete selected accepted cards, including `--cards all`, with explicit change confirmation and deterministic application.
- Added committed human-readable `cards/` exports of accepted cards while keeping local `evidence/` views ignored.
- Added `scripts/build_skill_zip.py` to build and verify the skill-only release ZIP from `release/skill.txt`.
## 0.1.7
- Expanded the corpus by 20 papers covering clonal haematopoiesis, CCUS, germline predisposition, TP53 allelic state, and inherited myeloid risk.
- Added quarantine workflow for holding and reviewing pre-acceptance papers outside the normal incorporation path.
- Fanout now rejects DOI duplicates already present in accepted or quarantined papers.
- Added reviewed source-disease aliases with one centralized policy for generated ingestion prompts.
- Reports now open with a structured variant summary using exact hotspot and biomarker naming where relevant.
- Vancouver citations are now prepared and finalized deterministically around the report-formatting model step.
- Prognostic reporting now emphasizes disease-specific variant contributions and avoids unsupported transfer between diseases or models.
- Reporting-rule audit now evaluates every rule before final report formatting.
## 0.1.6
- Expanded the corpus with the v0.1.6 evidence tranche, including additional treatment, prognosis, germline, and clonal haematopoiesis evidence.
- Added nel-validate: cases can be run then scored against marking criteria
- Added Phase 5 ingestion: extract missed evidence from already accepted papers without altering existing accepted cards.
- Corpus papers now record the NEL version in which they were accepted, with version-based indexing.
- Added a curator backlog for useful secondary sources found in rejected cards but not already represented in the corpus.
- Reports now include patient-relevant molecular modifiers of treatment response, resistance, relapse risk, or survival.
- Publication keys now follow PDF filenames, giving papers stable operator-facing names independent of citation metadata.
- Slightly optimized skill.md pipeline
## 0.1.5
- Added automatic, manual, full-report, and report-only workflows.
- Manual mode now allows users to review and correct the integrated diagnosis.
- Diagnosis evidence can now be found from disease context even when no variants are detected.
- Evidence lookup can include selected related diseases while preserving the original disease context.
- Added support for cases with no stated haematological malignancy and no detected variants.
- Reports now separate evidence drafting from final formatting.
- Default reports now use numbered citations and a numbered reference list.
- Added six demonstration cases with expected results for checking workflow behaviour.
- Temporary working folders are now created automatically in the system temporary location.
- Simplified the skill instructions and divided complex stages into smaller steps.
## 0.1.4

- Improved multi-part evidence gathering for ingest phases 2 and 3
- Each ingest phase deterministically audits json prior to output and completion
- Updated corpus now includes ELN 2022/2024, ELN-DAVID 2025, IPSET, CHRS, Cpss-Mol and MIPPS70V2
## 0.1.3
- Corpus includes WHO5, ICC and IPSS-M paper
- Allowed multi-part quoting, introduced as evidence bundles (`contiguous_text`, `composite_text`, `table_relation`) using verbatim, role-tagged fragments mapped via `support_map`.
- Changed Phase 3 to emit one complete pass/fail review per card, including failure type, defensibility, guidance, and quote restatement for failures; mandatory audit checks added.
- Added Phase 4 human adjudication as the sole creator of `paper.final.json` and
  removed the Phase 3 to Phase 2 rework loop.
- Changed validation to focus only on the final json. Errors in upstream jsons return warnings
- Separated exact card diseases from corpus-broadening `disease_ancestors` derived from a cycle-checked umbrella graph.
- Extended the disease vocabulary to 1.2 with `MPN`, `MDS/MPN`, `MPN blast phase`,
  `acute leukaemia of ambiguous lineage`, `histiocytic/dendritic neoplasm`, and
  `haematological malignancy, other`, and re-parented the affected families.
- `publication_type` limited to 6 categorical possibilities.
- Added `publication_type_verified_by_phase3` and removed `escalates_to` from cards,
  the index, and retrieval
- Added `scripts/transport.py` to move private corpus files between computers
- Optimized `SKILL.md` as a four-step workflow, returning a evidence.md containing evidence cards.
## 0.1.2
- Added deterministic, content-addressed PDF-to-Markdown ingestion with locked
  OpenDataLoader settings and atomic publication.
- Added DOI detection, Crossref resolution, model-assisted DOI recovery, and a
  batch-atomic manual citation worksheet.
- Made JSONL the canonical input index and added a synchronized read-only CSV view.
- Made the human-readable publication key the operator-facing work-folder identity
  and card-ID prefix while retaining the content-derived paper UUID internally.
- Moved publication-type assignment and justification into Phase 1, propagation into
  Phase 2, and independent audit into Phase 3.
- Hardened all model phases with exclusive output contracts and mandatory pre-output
  gates; strengthened Phase 2 qualifier, quote, and independent-utility checks, and
  added bounded Phase 3 reviewer suggestions for rejected packages.
- Added stable acceptance timestamps and changed duplicate publication keys at
  incorporation from fatal errors to deterministic per-paper rejection.
- Replaced escalation-candidate selection with evidence-bounded diagnostic
  adjudication over structured case facts and all gene-matched diagnosis cards.
  Adjudication now separates a source-supported diagnostic label from the major
  disease category used for deterministic downstream filtering, and fails closed
  when required facts are missing or criteria are unmet.
- Updated rendering to expose adjudication status, the downstream filter disease,
  any supported diagnostic label, and the cards driving a changed major category.
- Bumped all working and accepted schemas; prior in-flight artefacts require
  re-ingestion rather than migration.
## 0.1.1
- Replaced central phase queues with independent `work/<paper-id>/` folder state.
- Moved complete, generated phase instructions to committed `prompts/` data.
- Added deterministic fan-out, source-aware confirmation, and accept-only incorporation.
- Made final packages identify the exact provisional round independently audited.
- Removed provisional corpus semantics; corpus membership now implies completed audit.
- Added per-paper incorporation rejection while keeping global identity collisions fatal.
- Separated private input, work, acceptance, and archive data from shipped `output/` artefacts.
## 0.1.0

Initial release of the corpus-grounded evidence layer for myeloid NGS interpretation.
- Publication selection - Identifies the next indexed publication and ingestion phase to process.
- Phased ingestion - Prepares and accepts bounded census, extraction, and independent audit handoffs.
- Evidence validation - Checks schemas, census completeness, source-verbatim quotes, and audit requirements.
- Extraction rework - Returns failed audits to a controlled Phase 2 correction round while preserving provenance.
- Corpus building - Incorporates accepted packages into deterministic provisional or audited corpus and index files.
- Evidence retrieval - Selects gene- and disease-matched cards and reports genes the corpus cannot assess.
- Evidence rendering - Produces a deterministic, citable Markdown evidence block within a token budget.
- Citation key generation - Builds stable publication identifiers and display citations from citation metadata.
- Vocabulary validation - Enforces the closed disease vocabulary and required umbrella relationships.
