# Clinical coherence audit

Audit the complete clinical decision set below after evidence resolution. This is a reasoning/soundness audit, not an evidence-matching task.

Use only the supplied case and accepted clinical artifacts. Do not introduce a new diagnosis, treatment, biomarker, prognosis claim, or germline interpretation from outside knowledge. Do not choose evidence cards. The purpose is to detect contradictions, cross-domain incoherence, or loss of default-proforma clinical semantics before report synthesis.

## Required checks

1. **Diagnosis conclusion coherence**
   - The final WHO5/ICC label must agree with the stated reason and variant assessments.
   - If the artifact itself says a defining requirement is absent, not met, unknown, monoallelic when biallelic/multi-hit is required, or otherwise explicitly fails a defining criterion, it must not nevertheless establish that entity.
   - This rule is generic: do not special-case TP53 or any named disease.
   - `diagnostic_effect` must make sense relative to the supplied starting diagnosis.

2. **Cross-domain coherence**
   - Prognosis, treatment, biomarker/MRD, and germline interpretations must use the authoritative disease and must not contradict the accepted diagnosis or their own reasons.
   - Do not require wording identity; clinically equivalent representations pass.

3. **Prognosis framework preservation**
   - Apply the accepted framework preset below. A framework required by the authoritative disease must not disappear or be replaced by a cohort study/non-framework source.

{{ module "prognostic_frameworks" }}

4. **Germline threshold coherence**
   - `germline_suspicious` requires patient-specific positive support for constitutional origin; mere biological possibility, a known predisposition association, or missing family history is insufficient.
   - Discordant supplied factors must weigh against suspicion.

5. **Post-evidence soundness**
   - Compare the original clinical proformas with the final evidence audit (and adjudication when present).
   - If downstream evidence audit/adjudication removed or suppressed a clinically material proposition, check whether the remaining diagnosis/framework/category still survives without it.
   - Do not fail merely because an optional unsupported proposition was correctly suppressed. Fail only when the surviving clinical conclusion depends on evidence that is no longer supported.

6. **No clerical overreach**
   - Ignore empty evidence-card tag lists in the reviewed workflow; downstream matching owns evidence assignment.
   - Do not fail for stylistic wording, harmless ordering, or lack of an internal reasoning graph.

## Inputs

### Frozen clinical/evidence packet
{{ input.clinical_packet }}

## Output

Return YAML only. Use `status: pass` when there is no clinically material coherence defect. Use `status: fail` only for a concrete defect that should trigger a clinical redo.

```yaml
status: <pass|fail>
issues:
  - domain: <diagnosis|prognosis|treatment|biomarker|germline>
    path: "<best available artifact path>"
    message: "<what is clinically incoherent>"
    fix: "<minimal correction; preserve unrelated decisions>"
feedback: "<concise combined redo instruction, or null when status is pass>"
```

When `status: pass`, return `issues: []` and `feedback: null`.
