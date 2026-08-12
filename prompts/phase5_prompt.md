# Phase 5 — post-acceptance supplementation or revision
## Active phase and scope

Active phase: **Phase 5 only** for one already accepted publication.

Read-only inputs:
- `paper.md`
- `metadata.json`
- `paper.census.json`
- `paper.base.final.json`
- `phase5.json`
- `phase5.existing-cards.json`
- `phase5_prompt.md`
- revision mode only: `paper.phase5-targets.json`
Read `phase5.json` first. `mode: additive` uses the existing additive workflow. `mode: revision` may change only the cards locally authorised in `target_card_ids`. Never alter the census. In additive mode, first match each requested interpretation to one or more existing census claims. A census claim is a review boundary, not proof that a card should exist. If no existing census claim covers the requested interpretation, stop that item and tell the user it requires a redo from Phase 1.

## Shared card standards

### Clinical reporting gate

# Clinical reporting gate

A clinically useful fact is one that could materially contribute to a concise myeloid NGS report by informing:

- diagnosis or classification;
- patient-level prognosis;
- treatment or management;
- MRD interpretation; or
- assessment of possible germline predisposition.

The fact must apply to the stated disease, molecular finding and clinical context.

Background information is not clinically useful by itself, including prevalence, epidemiology, study methodology, molecular mechanism alone, or descriptive associations without a clinical implication.

A negative or null finding is useful only when its absence or lack of effect is clinically informative.

When several findings support the same clinical conclusion, prefer the clinical conclusion rather than its component statistics.

### Card content rules

# Card content rules

- One card represents one independently useful, directly supported clinical assertion.
- `genes` contains only genes participating in that assertion.
- `genes: []` is permitted only for geneless `diagnosis` or `treatment` assertions.
- A geneless `diagnosis` card must state an independently useful diagnostic/classification criterion, requirement, exclusion, threshold, or distinction.
- A geneless `treatment` card must state independently useful disease-level treatment context that informs treatment eligibility, selection, or interpretation of a molecular treatment modifier. Do not card generic treatment background that would not affect an NGS report.
- `diseases` records exact source-supported clinical applicability; derived ancestors are indexing terms only and do not broaden scope.
- Do not merge distinct assertions merely because they share a gene, disease, category, paragraph, table, or census claim.

## Category entailment

- `diagnosis`: the passage states a molecular, morphologic, clinical, quantitative, or other criterion that defines, supports, excludes, differentiates, or changes a diagnosis or classification.
- `prognosis`: the passage explicitly states an outcome, risk, survival, progression, relapse, or named prognostic-model effect.
- `treatment`: the passage explicitly supports treatment selection, eligibility, standard treatment, sensitivity, resistance, response, or a treatment-specific effect.
- `biomarker`: the passage explicitly assigns a testing, detection, monitoring, or discrimination role that remains independently useful rather than merely relabelling the same diagnostic assertion. The interpretation must name that independent function.
- `germline`: the passage explicitly concerns inherited, constitutional, or predisposition status, or germline evaluation. Preserve the source's certainty; a work-up recommendation does not establish constitutional status.

### Evidence bundle rules

# Evidence bundle rules

Every card must have exactly one evidence bundle. The bundle must directly support every material assertion in the interpretation using source-verbatim fragments from the paper. A locator is navigation metadata, not evidence.

Preserve every qualifier needed to determine where the claim applies or to prevent clinical misapplication. Do not include methodological detail unless it changes the clinical meaning or strength of the claim. Do not use a bibliographic reference-list entry, a heading alone, unsupported nearby text, or model knowledge as substantive evidence.

For germline content, distinguish established inherited or constitutional status from possible constitutional origin and from a recommendation or indication for germline work-up; a work-up recommendation supports only a conditional interpretation.

Use `contiguous_text` when one coherent contiguous passage is sufficient. Its sole fragment has role `claim` and may contain multiple contiguous sentences. Expand around the explicit role claim only as needed to capture antecedents, scope, population, treatment, comparator, analysis, thresholds, exclusions, direction, or clinical consequence. Stop only when the fragment supports every material element of the interpretation without relying on unquoted context.

Use `composite_text` only when no single coherent passage contains the minimal sufficient evidence. Use two to six independently verbatim fragments. One or more `claim` fragments may jointly support one source assertion; add `scope_heading`, `legend`, or `footnote` fragments only when they provide necessary governing context. Every fragment must contribute material support recorded in `support_map`, and all fragments must have compatible scope. Do not combine separate findings, populations, analyses, classifier branches, or independently useful conclusions. If a fragment is unnecessary, use `contiguous_text`, narrow the interpretation, split the card, or omit it.

A `scope_heading` is valid only when the substantive passage occurs within that heading's section and no intervening heading changes scope. A heading supplies context; it does not establish a role claim by itself.

Use `table_relation` when a table value cannot be interpreted defensibly without its governing labels. Quote each required `column_header`, `row_header`, `cell`, `legend`, and `footnote` as a separate fragment. Preserve all applicable row and column headers, spanning or multi-level headers, and marked legends or footnotes. Omit the card when extraction damage or missing structure leaves the relation ambiguous. Do not replace source labels with model-authored key/value facts.

Map every material assertion in the interpretation to explicit supporting source text in `support_map`. If any assertion is unsupported, expand the bundle, narrow the interpretation, split the card, or omit it. Once sufficient evidence is assembled, do not shorten it merely for concision.

### Source disease alias policy

A source-stated disease may ground a canonical card disease only when it is already
canonical or exactly matches a reviewed alias in the canonical source-alias file,
ignoring surrounding whitespace and letter case only.

Emit only the canonical target in `diseases`, but preserve the source's actual disease
or population wording in evidence and interpretation. Do not use fuzzy matching,
stemming, punctuation substitution, semantic inference, or nearest-term mapping. A
source term that is neither canonical nor a configured alias remains outside the
controlled vocabulary.

Canonical source aliases:

```json
{
  "clonal haematopoiesis": "CHIP",
  "clonal haemopoiesis": "CHIP"
}
```

## Additive mode
First ask what interpretation or interpretations the user believes this paper supports but the accepted cards missed.
For each requested interpretation:
1. identify the matching claim or claims in `paper.census.json`; if none match, require a redo from Phase 1 and stop that item;
2. search `phase5.existing-cards.json` semantically for the same or materially similar interpretation;
3. if the target publication already contains an equivalent card, show its `card_id` and interpretation and do not create a duplicate;
4. if only another publication contains a similar card, mention it as context but still assess whether this target paper independently supports the requested interpretation;
5. reread `paper.md` specifically for the requested interpretation;
6. if unsupported, say so and do not create a card;
7. if supported, propose one or more cards satisfying the shared card standards above.
Accept free-text discussion over any number of turns. The user may request rewording, narrower scope, different evidence, splitting, or deletion of proposed cards.
New cards must follow the exact card/evidence shapes already used in `paper.base.final.json`.
- `diseases` records exact source-supported applicability only.
- `disease_ancestors` must follow the same canonical values used by the existing accepted package.
- New `card_id` values must use the publication's existing ID pattern and the next unused numeric suffix. Never renumber existing cards.
When the user indicates the additions are ready for audit, write exactly `paper.phase5-provisional.json` using the existing ingestion-package shape containing only proposed new cards/evidence.
Set `paper_id` from the accepted package, `round` to `1`, `extraction_model` to this model's exact identity, publication type fields equal to the accepted package except `publication_type_verified_by_phase3: false`, `census_entries` equal to `paper.census.json`, coverage fields to exact unions of the proposed cards, and `audit: null`.
A different model reviews the provisional using `phase5_review_prompt.md`. If any card fails, discuss it with the user; any changed card/evidence requires a new independent review.

When the user sends `FINALIZE` on its own line, require all cards to pass, then show the exact pending change set using short card IDs:
- `ADD: 000x,...`
- `DELETE: none`
- `MODIFY: none`
Do **not** write `paper.final.json` yet. Ask the user to send `CONFIRM CHANGES` on its own line. Only after that exact confirmation, and only if the reviewed provisional has not changed, merge only the reviewed additions into `paper.base.final.json`, preserve `paper_nickname`, existing cards/evidence and audit metadata, append passing audit results for the new cards, and return exactly `paper.final.json`. Any change after review or confirmation requires a fresh review and confirmation.
## Revision mode — interactive authoring

Revision mode is selected locally with `prepare_redo.py --key <publication-key> --phase 5 --cards 0001,0003,...` or `--cards all`. `--cards all` releases every accepted card from this publication into the revision allowlist.
At the start:
1. read `paper.phase5-targets.json`;
2. present each selected card by short ID, interpretation and current evidence locator;
3. ask the user what they want changed;
4. discuss the requested revisions interactively over as many turns as needed.
The selected cards are an **allowlist**, not a requirement to change every selected card. During Phase 5 the user chooses the actual subset to modify or delete. A revision provisional contains only those actual changes. Revision mode does not add cards; use additive Phase 5 for additions.
For each proposed modification:
- reread the source specifically for the requested correction;
- explain briefly when the requested change is not source-supported;
- require the replacement interpretation and evidence to satisfy the shared card standards;
- keep these card fields unchanged: `card_id`, `genes`, `diseases`, `disease_ancestors`, `category`, `evidence_tier`, `secondary_citation`;
- `interpretation`, `locator`, and the paired evidence bundle may change;
- if a structural field needs changing, require a redo from Phase 2, or Phase 1 if the census must also change.
For each proposed deletion:
- delete only an authorised target card;
- record a concise reason agreed with the user;
- the deletion removes the accepted card, its paired evidence bundle, and its matching final audit result;
- do not use deletion to rename/restructure a card that should instead undergo a Phase 2 redo, or Phase 1 if the census must also change.

When the user sends `PROVISIONAL` on its own line, write exactly `paper.phase5-provisional.json` in this revision shape:
```json
{
  "schema_version": "1.1",
  "phase": 5,
  "mode": "revision",
  "publication_key": "<from phase5.json>",
  "paper_id": "<from paper.phase5-targets.json>",
  "round": 1,
  "extraction_model": "<this model's exact identity>",
  "revisions": [
    {
      "card_id": "<full accepted card_id>",
      "replacement_card": {},
      "replacement_evidence": {},
      "revision_sha256": "<revision_sha256(replacement_card, replacement_evidence)>"
    }
  ],
  "deletions": [
    {
      "card_id": "<full accepted card_id>",
      "reason": "<concise user-agreed reason>",
      "deletion_sha256": "<deletion_sha256(card_id, prepared card hash, prepared evidence hash, reason)>"
    }
  ]
}
```
`revisions` and `deletions` may each be empty, but at least one actual change is required. A card cannot appear in both arrays.

Before returning the file, execute the embedded `validate_revision_provisional(...)` code below against `phase5.json`, `paper.phase5-targets.json`, the provisional, and `paper.md`. If there are errors, fix the provisional and rerun until it passes. Return the validated provisional only.
## Revision mode — independent review return

Phase 5R is LLM-only and non-interactive. The user will later upload `paper.phase5-review.json` from the independent reviewer into this same Phase 5 conversation.
On receipt:
1. execute `validate_revision_review(...)` using the current provisional;
2. do not accept a review whose per-change hash differs from the current provisional;
3. if any modification or deletion fails, explain the review criticism to the user and resume interactive revision;
4. after any revision change, generate a new complete provisional and require a fresh Phase 5R review of the batch.
## Revision mode — FINALIZE

Treat all revision discussion as provisional until the user sends `FINALIZE` on its own line.

On `FINALIZE`, require a valid review in which every provisional modification/deletion passes. Do **not** create or edit `paper.final.json` and do **not** write `paper.phase5-revision.json` yet.

Show the exact pending change set using short card IDs:
- `ADD: none`
- `DELETE: 000x,...` or `none`
- `MODIFY: 000x,...` or `none`
Ask the user to send `CONFIRM CHANGES` on its own line. Only after that exact confirmation, and only if the reviewed provisional has not changed, write exactly `paper.phase5-revision.json`:
```json
{
  "schema_version": "1.1",
  "phase": 5,
  "mode": "revision",
  "operation": "change_cards",
  "publication_key": "<from phase5.json>",
  "paper_id": "<from provisional>",
  "base_final_sha256": "<from phase5.json>",
  "base_census_sha256": "<from phase5.json>",
  "extraction_model": "<from provisional>",
  "reviewer_model": "<from review>",
  "revisions": [],
  "deletions": [],
  "confirmed_change_set": {
    "add": [],
    "delete": ["<full deleted card IDs in provisional order>"],
    "modify": ["<full modified card IDs in provisional order>"]
  }
}
```
The `revisions` and `deletions` arrays must be exact copies of the reviewed provisional arrays. `confirmed_change_set` must exactly encode the change set the user just confirmed. Execute `validate_revision_asset(...)`. If errors occur, fix the asset and rerun. Return the validated `paper.phase5-revision.json` only. Do not claim that accepted corpus state has changed; local `apply_phase5.py` and `confirm.py` are authoritative.

## Embedded revision validation code

Execute this code; do not paraphrase or reimplement it.

```python
#!/usr/bin/env python3
"""Self-contained Phase 5 revision validators injected into the ChatGPT prompt.

These functions are an online artifact-quality gate. Local apply/confirm code reruns
all security-critical checks before any accepted corpus state is changed.
"""
import hashlib
import json
import re

IMMUTABLE_CARD_FIELDS = (
    "card_id",
    "genes",
    "diseases",
    "disease_ancestors",
    "category",
    "evidence_tier",
    "secondary_citation",
)


def canonical_sha256(document):
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def revision_sha256(card, evidence):
    return canonical_sha256({"card": card, "evidence": evidence})


def deletion_sha256(card_id, card_sha256, evidence_sha256, reason):
    return canonical_sha256(
        {
            "card_id": card_id,
            "card_sha256": card_sha256,
            "evidence_sha256": evidence_sha256,
            "reason": str(reason).strip(),
        }
    )


def _normalise(text, markdown=False):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        lines = []
        for line in text.splitlines():
            if re.match(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$", line):
                continue
            lines.append(line.replace("|", " "))
        text = "\n".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def _target_map(targets):
    return {item.get("card_id"): item for item in targets.get("targets", [])}


def _provisional_revision_map(provisional):
    return {item.get("card_id"): item for item in provisional.get("revisions", [])}


def _provisional_deletion_map(provisional):
    return {item.get("card_id"): item for item in provisional.get("deletions", [])}


def _provisional_changes(provisional):
    changes = [("modify", item) for item in provisional.get("revisions", [])]
    changes.extend(("delete", item) for item in provisional.get("deletions", []))
    return changes


def validate_revision_provisional(phase5, targets, provisional, paper_text):
    errors = []
    if phase5.get("phase") != 5 or phase5.get("mode") != "revision":
        errors.append("phase5.json is not revision mode")
        return errors
    if provisional.get("schema_version") != "1.1" or provisional.get("phase") != 5:
        errors.append("revision provisional must have schema_version 1.1 and phase 5")
    if provisional.get("mode") != "revision":
        errors.append("revision provisional mode must be revision")
    if provisional.get("publication_key") != phase5.get("publication_key"):
        errors.append("provisional publication_key does not match phase5.json")
    if provisional.get("paper_id") != targets.get("paper_id"):
        errors.append("provisional paper_id does not match targets")
    if provisional.get("round") != 1:
        errors.append("revision provisional round must be 1")
    if not isinstance(provisional.get("extraction_model"), str) or not provisional.get(
        "extraction_model", ""
    ).strip():
        errors.append("revision provisional extraction_model is required")
    target_map = _target_map(targets)
    allowed = set(phase5.get("target_card_ids") or [])
    if allowed != set(target_map):
        errors.append("target file card IDs do not exactly match phase5 target_card_ids")
    revisions = provisional.get("revisions")
    deletions = provisional.get("deletions")
    if not isinstance(revisions, list):
        errors.append("revision provisional revisions must be an array")
        revisions = []
    if not isinstance(deletions, list):
        errors.append("revision provisional deletions must be an array")
        deletions = []
    if not revisions and not deletions:
        errors.append("revision provisional must contain at least one changed card")
        return errors
    revision_ids = [item.get("card_id") for item in revisions]
    deletion_ids = [item.get("card_id") for item in deletions]
    if len(revision_ids) != len(set(revision_ids)):
        errors.append("revision provisional contains duplicate modified card IDs")
    if len(deletion_ids) != len(set(deletion_ids)):
        errors.append("revision provisional contains duplicate deleted card IDs")
    overlap = sorted(set(revision_ids) & set(deletion_ids))
    if overlap:
        errors.append("revision provisional cannot both modify and delete: " + ", ".join(overlap))
    off_target = sorted((set(revision_ids) | set(deletion_ids)) - allowed)
    if off_target:
        errors.append("revision provisional contains off-target cards: " + ", ".join(off_target))
    source = _normalise(paper_text, markdown=True)
    for item in revisions:
        card_id = item.get("card_id")
        if card_id not in target_map:
            continue
        if set(item) != {
            "card_id",
            "replacement_card",
            "replacement_evidence",
            "revision_sha256",
        }:
            errors.append(f"{card_id}: revision item has unexpected or missing fields")
            continue
        original = target_map[card_id]
        card = item.get("replacement_card")
        evidence = item.get("replacement_evidence")
        if not isinstance(card, dict) or not isinstance(evidence, dict):
            errors.append(f"{card_id}: replacement card and evidence must be objects")
            continue
        if card.get("card_id") != card_id or evidence.get("card_id") != card_id:
            errors.append(f"{card_id}: replacement card/evidence card_id mismatch")
        if set(card) != set(original.get("card") or {}):
            errors.append(
                f"{card_id}: replacement card fields must exactly match the original card fields"
            )
        for field in IMMUTABLE_CARD_FIELDS:
            if card.get(field) != (original.get("card") or {}).get(field):
                errors.append(f"{card_id}: immutable card field changed: {field}")
        if card == original.get("card") and evidence == original.get("evidence"):
            errors.append(f"{card_id}: replacement is identical to the accepted card/evidence")
        expected_hash = revision_sha256(card, evidence)
        if item.get("revision_sha256") != expected_hash:
            errors.append(f"{card_id}: revision_sha256 does not match replacement content")
        fragments = evidence.get("fragments") if isinstance(evidence, dict) else None
        if not isinstance(fragments, list) or not fragments:
            errors.append(f"{card_id}: replacement evidence requires fragments")
        else:
            for fragment in fragments:
                quote = _normalise((fragment or {}).get("quote", ""), markdown=True)
                fragment_id = (fragment or {}).get("fragment_id", "?")
                if not quote:
                    errors.append(f"{card_id}/{fragment_id}: evidence quote is empty")
                elif quote not in source:
                    errors.append(
                        f"{card_id}/{fragment_id}: evidence quote not found verbatim in paper.md"
                    )
    for item in deletions:
        card_id = item.get("card_id")
        if card_id not in target_map:
            continue
        if set(item) != {"card_id", "reason", "deletion_sha256"}:
            errors.append(f"{card_id}: deletion item has unexpected or missing fields")
            continue
        reason = str(item.get("reason", "")).strip()
        if not reason:
            errors.append(f"{card_id}: deletion reason is required")
        target = target_map[card_id]
        expected_hash = deletion_sha256(
            card_id,
            target.get("card_sha256"),
            target.get("evidence_sha256"),
            reason,
        )
        if item.get("deletion_sha256") != expected_hash:
            errors.append(f"{card_id}: deletion_sha256 does not match prepared target and reason")
    return errors


def validate_revision_review(phase5, targets, provisional, review):
    errors = []
    if review.get("schema_version") != "1.1" or review.get("phase") != 5:
        errors.append("Phase 5 revision review must have schema_version 1.1 and phase 5")
    if review.get("mode") != "revision":
        errors.append("Phase 5 revision review mode must be revision")
    if review.get("publication_key") != phase5.get("publication_key"):
        errors.append("review publication_key does not match phase5.json")
    if review.get("paper_id") != provisional.get("paper_id"):
        errors.append("review paper_id does not match provisional")
    if review.get("round") != provisional.get("round"):
        errors.append("review round does not match provisional")
    if review.get("extraction_model_reviewed") != provisional.get("extraction_model"):
        errors.append("review extraction_model_reviewed does not match provisional")
    if review.get("reviewer_model") == provisional.get("extraction_model"):
        errors.append("reviewer model must differ from Phase 5 extraction model")
    if not isinstance(review.get("reviewer_model"), str) or not review.get(
        "reviewer_model", ""
    ).strip():
        errors.append("reviewer_model is required")
    revision_map = _provisional_revision_map(provisional)
    deletion_map = _provisional_deletion_map(provisional)
    changes = _provisional_changes(provisional)
    results = review.get("results")
    if not isinstance(results, list):
        errors.append("review results must be an array")
        return errors
    expected = [(operation, item.get("card_id")) for operation, item in changes]
    actual = [(item.get("operation"), item.get("card_id")) for item in results]
    if actual != expected:
        errors.append("review results must cover every provisional change once and preserve order")
    if len(actual) != len(set(actual)):
        errors.append("review contains duplicate change results")
    for result in results:
        operation = result.get("operation")
        card_id = result.get("card_id")
        if operation == "modify":
            provisional_item = revision_map.get(card_id)
            if provisional_item is not None and result.get("revision_sha256") != provisional_item.get(
                "revision_sha256"
            ):
                errors.append(f"{card_id}: review hash does not match current provisional revision")
        elif operation == "delete":
            provisional_item = deletion_map.get(card_id)
            if provisional_item is not None and result.get("deletion_sha256") != provisional_item.get(
                "deletion_sha256"
            ):
                errors.append(f"{card_id}: review hash does not match current provisional deletion")
        else:
            errors.append(f"{card_id}: review operation must be modify or delete")
        verdict = result.get("verdict")
        if verdict not in {"pass", "fail"}:
            errors.append(f"{card_id}: review verdict must be pass or fail")
        if verdict == "fail":
            if not str(result.get("reason", "")).strip():
                errors.append(f"{card_id}: failed review requires reason")
            if not str(result.get("suggested_action", "")).strip():
                errors.append(f"{card_id}: failed review requires suggested_action")
    return errors


def validate_revision_asset(phase5, targets, provisional, review, asset):
    errors = validate_revision_review(phase5, targets, provisional, review)
    if errors:
        return errors
    failed = [
        result.get("card_id")
        for result in review.get("results", [])
        if result.get("verdict") != "pass"
    ]
    if failed:
        errors.append("cannot finalize: review has failed cards: " + ", ".join(failed))
        return errors
    if asset.get("schema_version") != "1.1" or asset.get("phase") != 5:
        errors.append("revision asset must have schema_version 1.1 and phase 5")
    if asset.get("mode") != "revision" or asset.get("operation") != "change_cards":
        errors.append("revision asset must use mode=revision and operation=change_cards")
    if asset.get("publication_key") != phase5.get("publication_key"):
        errors.append("revision asset publication_key does not match phase5.json")
    if asset.get("paper_id") != provisional.get("paper_id"):
        errors.append("revision asset paper_id does not match provisional")
    if asset.get("base_final_sha256") != phase5.get("base_final_sha256"):
        errors.append("revision asset base_final_sha256 does not match phase5.json")
    if asset.get("base_census_sha256") != phase5.get("base_census_sha256"):
        errors.append("revision asset base_census_sha256 does not match phase5.json")
    if asset.get("extraction_model") != provisional.get("extraction_model"):
        errors.append("revision asset extraction_model does not match provisional")
    if asset.get("reviewer_model") != review.get("reviewer_model"):
        errors.append("revision asset reviewer_model does not match review")
    provisional_revisions = provisional.get("revisions", [])
    provisional_deletions = provisional.get("deletions", [])
    asset_revisions = asset.get("revisions")
    asset_deletions = asset.get("deletions")
    if not isinstance(asset_revisions, list):
        errors.append("revision asset revisions must be an array")
        asset_revisions = []
    if not isinstance(asset_deletions, list):
        errors.append("revision asset deletions must be an array")
        asset_deletions = []
    if asset_revisions != provisional_revisions:
        errors.append("revision asset revisions must exactly match the independently reviewed provisional")
    if asset_deletions != provisional_deletions:
        errors.append("revision asset deletions must exactly match the independently reviewed provisional")
    confirmed = asset.get("confirmed_change_set")
    expected_confirmed = {
        "add": [],
        "delete": [item.get("card_id") for item in provisional_deletions],
        "modify": [item.get("card_id") for item in provisional_revisions],
    }
    if confirmed != expected_confirmed:
        errors.append("revision asset confirmed_change_set does not exactly match reviewed changes")
    return errors
```
