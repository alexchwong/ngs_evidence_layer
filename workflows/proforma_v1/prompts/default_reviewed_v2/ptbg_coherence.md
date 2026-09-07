# Prognosis / treatment / biomarker / germline coherence audit

Each supplied review is a reportable statement whose evidence review did not establish support. Decide whether the statement should be corrected.

No corpus and no evidence cards are supplied to this step. Do not introduce literature, and do not attempt to re-run the evidence decision: `evidence_outcome` is the accepted result of the independent evidence chain and is given to you as a fact.

## What to check

For each review, weigh `statement` and `stated_reason` against `patient_findings` and `evidence_outcome`.

Fail the review when:

- the statement asserts something the supplied patient findings do not establish;
- the stated reason overreaches the patient's actual state (for example, applying a multi-hit finding to a monoallelic patient);
- the stated reason contradicts the statement it accompanies;
- the statement's scope is broader than what the accepted evidence outcome can carry.

`evidence_context` tells you which evidence universe the statement belongs to. A `prognosis_framework` statement is a claim about a named prognostic framework; a `prognosis_other` statement is a non-framework claim. A statement that silently borrows framework authority for a non-framework claim is a failure.

Pass the review when the statement is correctly scoped and the absence of accepted evidence is the only issue — the existing pipeline already suppresses uncited content, and duplicating that here would be double-counting.

## Output

Return exactly one YAML mapping, with exactly one review for every supplied `reference`, using the supplied reference values unchanged:

```yaml
reviews:
  - reference: PX-OTHER_EVIDENCE_ADVERSE-01
    status: revision_required
    issues:
      - The patient's findings support monoallelic TP53; the stated reason relies on multi-hit disease.
  - reference: TX-THERAPY_OPTION-02
    status: pass
    issues: []
```

State issues in plain clinical English. Do not emit field paths or workflow internals.

Statements to review:
{{ input.coherence_packet }}
