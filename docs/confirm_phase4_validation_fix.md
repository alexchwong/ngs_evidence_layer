# Fix `confirm.py` so Phase 4 evidence corrections are not blocked by immutable provisional evidence

## Repository and branch

- Repository: `alexchwong/ngs_evidence_layer`
- Branch: `v0.1.3-devel`

## Problem summary

`confirm.py` currently performs full source-evidence validation on both:

1. the approved provisional package; and
2. the Phase 4 final package.

This causes valid Phase 4 evidence corrections to fail confirmation.

Phase 4 is allowed to correct evidence fragments in `paper.final.json`, but the provisional package is a read-only historical artefact and must not be overwritten. If a provisional evidence quote was non-verbatim and Phase 4 corrects it in the final package, `confirm.py` still rejects the publication because it revalidates the immutable provisional quote against `paper.md`.

This is a workflow conflict:

- Phase 4 correctly preserves the original provisional package.
- Phase 4 correctly places the corrected evidence in the final package.
- `confirm.py` nevertheless requires the historical provisional evidence to satisfy current source-fragment validation.
- Therefore, some legitimate Phase 4 corrections can never be confirmed.

## Confirmed example

The affected provisional package contained seven evidence fragments that did not match `paper.md` under the validator's normalization:

- `bernard-2022-nejm-evidence-1-na-C0001/F01`
- `bernard-2022-nejm-evidence-1-na-C0002/F01`
- `bernard-2022-nejm-evidence-1-na-C0003/F01`
- `bernard-2022-nejm-evidence-1-na-C0006/F01`
- `bernard-2022-nejm-evidence-1-na-C0008/F01`
- `bernard-2022-nejm-evidence-1-na-C0009/F01`
- `bernard-2022-nejm-evidence-1-na-C0010/F01`

Phase 4 corrected those fragments in `paper.final.json`. The final package passes source-fragment validation, but confirmation still fails because `confirm.py` also validates the original provisional package with `source_text`.

The provisional differences include:

- ordinary character sequences replacing source ligatures, such as `first` versus `ﬁrst`, `significantly` versus `signiﬁcantly`, and `specificity` versus `speciﬁcity`;
- at least one substantive wording difference, such as the longer C0008 provisional passage.

Whitespace normalization does not repair these differences because `normalise()` does not perform Unicode compatibility normalization.

## Current problematic behavior

In `confirm.py`, the approved provisional package is validated as follows:

```python
provisional_errors, _warnings, _report = validation.validate_package(
    provisional,
    metadata,
    census,
    paths["source"].read_text(encoding="utf-8"),
    False,
)
errors.extend(provisional_errors)
```

Passing `paper.md` as `source_text` causes `validate_package()` to perform source-fragment containment checks on the historical provisional evidence.

Later, the final package is also fully validated against the same source:

```python
final_errors, warnings, report = validation.validate_package(
    final,
    metadata,
    census,
    paths["source"].read_text(encoding="utf-8"),
    True,
)
errors.extend(final_errors)
```

Both sets of errors are added without package labels, so users cannot tell whether a reported fragment failure came from the provisional or final package.

## Intended behavior

At confirmation time:

- `paper.final.json` is the authoritative, Phase 4-adjudicated evidence package and must receive full validation against `paper.md`.
- `paper.provisional-NNN.json` remains an immutable historical input and must be validated for schema and lineage integrity.
- `paper.review-NNN.json` must still be validated against the exact provisional package.
- Historical provisional source-fragment defects that were corrected during Phase 4 must not block confirmation.
- Structural or lineage defects in the provisional must continue to block confirmation.

## Proposed fix

### 1. Skip source-fragment containment checks for the approved provisional during confirmation

Change the provisional validation call in `confirm.py` to pass `source_text=None`:

```python
provisional_errors, _warnings, _report = validation.validate_package(
    provisional,
    metadata,
    census,
    source_text=None,
    require_final=False,
)
```

`validate_package()` already makes source containment conditional:

```python
source = normalise(source_text, markdown=True) if source_text is not None else None
```

and:

```python
if source is not None and normalized not in source:
    errors.append(f"{fragment_label}: fragment not found verbatim in paper.md")
```

Therefore, passing `None` preserves the existing schema, identity, card/evidence pairing, coverage, audit-state, and other structural checks while skipping only checks that require comparison with `paper.md`.

The final package must continue to be validated with the actual source text.

### 2. Label errors by artefact

Prefix errors before adding them to the aggregate error list:

```python
errors.extend(f"provisional: {error}" for error in provisional_errors)
```

```python
errors.extend(f"review: {error}" for error in review_errors)
```

```python
errors.extend(f"final: {error}" for error in final_errors)
```

Also consider labeling metadata and census errors consistently:

```python
errors.extend(f"metadata: {error}" for error in validation.validate_metadata(metadata))
errors.extend(f"census: {error}" for error in validation.validate_census(census, metadata))
```

Avoid double-prefixing schema messages if their existing wording is considered sufficient. The essential requirement is that provisional and final package errors be distinguishable.

### 3. Document the validation boundary

Add a concise comment in `confirm.py` explaining why the provisional is not source-validated:

```python
# The approved provisional is an immutable historical artefact. Phase 4 may
# correct its evidence in paper.final.json, so confirmation validates the
# provisional's structure and lineage but treats the final package as the
# authoritative source-validated evidence package.
```

## Suggested patch

```diff
diff --git a/<path>/confirm.py b/<path>/confirm.py
index 0000000..0000000 100755
--- a/<path>/confirm.py
+++ b/<path>/confirm.py
@@ -35,13 +35,20 @@ def confirm(args):
     if provisional_path is None or not provisional_path.is_file():
         errors.append("final audit approved_round does not identify an existing provisional file")
     else:
         provisional = validation.read_json(provisional_path, "approved provisional package")
+
+        # The approved provisional is an immutable historical artefact. Phase 4
+        # may correct its evidence in paper.final.json, so confirmation validates
+        # provisional structure and lineage but source-validates only the final.
         provisional_errors, _warnings, _report = validation.validate_package(
-            provisional, metadata, census, paths["source"].read_text(encoding="utf-8"), False
+            provisional,
+            metadata,
+            census,
+            source_text=None,
+            require_final=False,
         )
-        errors.extend(provisional_errors)
-        errors.extend(validation.validate_final_against_provisional(final, provisional))
+        errors.extend(f"provisional: {error}" for error in provisional_errors)
+        errors.extend(
+            f"final lineage: {error}"
+            for error in validation.validate_final_against_provisional(final, provisional)
+        )
         if review_path is None or not review_path.is_file():
             errors.append("final audit approved_round does not identify an existing Phase 3 review")
         else:
             review = validation.read_json(review_path, "Phase 3 review")
-            errors.extend(validation.validate_review(review, provisional))
+            review_errors = validation.validate_review(review, provisional)
+            errors.extend(f"review: {error}" for error in review_errors)
+
     final_errors, warnings, report = validation.validate_package(
         final, metadata, census, paths["source"].read_text(encoding="utf-8"), True
     )
-    errors.extend(final_errors)
+    errors.extend(f"final: {error}" for error in final_errors)
```

Adjust the repository path in the diff to the actual location of `confirm.py`.

## Tests to add

Add regression tests at the most appropriate existing test location.

### Test 1: corrected final passes despite invalid historical provisional quote

Construct a working publication directory containing:

- valid metadata;
- valid census;
- `paper.md`;
- a structurally valid provisional package whose evidence quote does not occur in `paper.md`;
- a matching valid Phase 3 review;
- a final package with the corrected source-verbatim quote;
- a valid final audit pointing to the provisional round.

Expected result:

- `confirm()` succeeds;
- the accepted final file is created;
- the census is copied;
- the full working directory is archived.

This is the primary regression test.

### Test 2: invalid final quote still fails

Use the same setup, but place a non-verbatim quote in `paper.final.json`.

Expected result:

- confirmation fails;
- the error is prefixed with `final:`;
- no accepted or archived artefact is committed.

### Test 3: provisional structural defect still fails

Use a provisional package with a structural defect unrelated to source containment, for example:

- missing evidence bundle for a card;
- duplicate card ID;
- wrong `paper_id`;
- invalid `publication_type_verified_by_phase3` for a provisional package.

Expected result:

- confirmation fails;
- the error is prefixed with `provisional:`.

### Test 4: review/provisional mismatch still fails

Use a valid final package but a Phase 3 review that:

- omits a provisional card;
- has a mismatched round;
- has mismatched extraction-model identity; or
- changes card order.

Expected result:

- confirmation fails;
- the error is prefixed with `review:`.

### Test 5: final/provisional lineage mismatch still fails

Change one of:

- `round`;
- `paper_id`;
- `extraction_model`.

Expected result:

- confirmation fails;
- the error is prefixed with `final lineage:`.

### Test 6: uncorrected provisional and final defect fails through final validation

Use the same invalid fragment in both provisional and final.

Expected result:

- the provisional source defect is ignored as historical;
- confirmation still fails because the final source quote is invalid;
- the error is prefixed with `final:`.

## Optional hardening

### Add an explicit validation mode

The minimal fix uses `source_text=None`, which is already supported by the function. A clearer long-term API would replace the implicit behavior with an explicit validation mode, for example:

```python
validate_package(
    package,
    metadata,
    census,
    source_text=source_text,
    require_final=False,
    validate_source_fragments=False,
)
```

A possible signature:

```python
def validate_package(
    package,
    metadata,
    census,
    source_text=None,
    require_final=False,
    validate_source_fragments=True,
):
```

Guard against contradictory use:

```python
if validate_source_fragments and source_text is None:
    raise ValueError("source_text is required when validate_source_fragments is true")
```

Then call:

```python
validation.validate_package(
    provisional,
    metadata,
    census,
    source_text=None,
    require_final=False,
    validate_source_fragments=False,
)
```

and:

```python
validation.validate_package(
    final,
    metadata,
    census,
    source_text=paper_text,
    require_final=True,
    validate_source_fragments=True,
)
```

This API refactor is optional for `v0.1.3`; the `source_text=None` change is sufficient to correct the bug with minimal risk.

## Do not fix this by mutating the provisional package

Do not copy the final evidence back into `paper.provisional-NNN.json`.

The provisional and Phase 3 review are historical records. Rewriting the provisional would:

- violate the Phase 4 read-only contract;
- break the integrity of the Phase 3 review;
- obscure what Phase 3 actually reviewed;
- undermine archive provenance.

The correct boundary is to preserve the provisional unchanged and make the final package the authoritative source-validated output.

## Do not solve this only with Unicode normalization

Adding NFKC normalization could make ligature-only differences compare equal, but it would not address the workflow defect:

- Phase 4 may make substantive evidence changes, not only ligature corrections.
- The provisional must remain immutable.
- The final must be able to supersede invalid provisional evidence.

Unicode normalization may be considered separately as a validator policy decision, but it is not the correct fix for this confirmation failure.

## Acceptance criteria

The change is complete when all of the following are true:

1. A structurally valid historical provisional package with an invalid source quote does not block confirmation when the final package contains a valid corrected quote.
2. Every final evidence fragment is still checked against `paper.md`.
3. Invalid final evidence still blocks confirmation.
4. Provisional schema and structural defects still block confirmation.
5. Review/provisional mismatches still block confirmation.
6. Final/provisional lineage mismatches still block confirmation.
7. Error messages clearly identify whether the failure arose from the provisional, review, final lineage, or final package.
8. Existing confirmation tests continue to pass.
9. A regression test reproduces the Bernard/IPSS-M failure mode or an equivalent minimal fixture.
10. The provisional and review remain unchanged in the archive.

## Suggested commit message

```text
fix(confirm): source-validate final package only after Phase 4
```

## Suggested pull-request summary

`confirm.py` previously revalidated immutable provisional evidence against `paper.md`, causing legitimate Phase 4 evidence corrections to remain unconfirmable. This change preserves structural and lineage validation for the provisional and review, while treating `paper.final.json` as the authoritative source-validated evidence package. It also labels validation errors by artefact and adds regression coverage for corrected Phase 4 evidence.
