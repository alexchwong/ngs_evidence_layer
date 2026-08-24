{{ include "includes/audit_general.md" }}

# Summary-plan audit

Audit against:
- the ORIGINAL atomic reportable statements; and
- the deterministically assembled blocks.

## Omission

Check that:
- every omission is redundant or lacks useful patient-level reporting consequence;
- no clinically material proposition is omitted;
- retained negative, unavailable, uncertain, non-applicable, or non-calculable findings have useful clinical function;
- omission cannot make the report misleading.

## Split

Check that:
- every split reflects a meaningful semantic difference;
- each split part faithfully preserves its source;
- coherent propositions are not unnecessarily divided;
- parallel gene or variant findings are not split only because molecular identities differ.

## Merge

Check that:
- clinically equivalent statements differing only by gene or variant identity are grouped when otherwise compatible;
- all same-category statements were considered for merging;
- no unnecessary parallel blocks remain;
- merging preserves scope, polarity, framework, treatment context, qualifiers, and uncertainty.

## Overall preservation

Check that:
- every clinically material proposition remains represented;
- nothing clinically material is added, lost, broadened, narrowed, or changed;
- the plan uses the fewest clinically readable blocks consistent with semantic preservation.

When a problem is found:
- identify the affected statement or block;
- state the violated rule;
- give corrective guidance;
- do not provide replacement report prose.

Return YAML only:
```yaml
preserved: true
omission_valid: true
split_valid: true
merge_complete: true
issues: []
```
