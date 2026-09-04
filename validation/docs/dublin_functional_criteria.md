# Dublin functional criteria

This document is the single source of truth for the **F1-F9 functional assessment used by `nel-validate-dublin`**.

The canonical validation cases and their atomic marking criteria remain in `validation/validation_dublin.md` using the repository-wide R1-R5 / RxCy format. The marking LLM evaluates those RxCy criteria only. It does not receive, infer, or emit F1-F9 scores.

After marking, `validation/scripts/score_functional_dublin.py` reads the machine-readable specification below and deterministically maps each Dublin RxCy result to one functional criterion. Every marking criterion in `validation/validation_dublin.md` must map to exactly one F1-F9 function. The scorer validates that invariant against the canonical validation registry before calculating any result.

## Functional criteria

- **F1 — Diagnostic integration:** integrate NGS findings with the existing diagnosis.
- **F2 — Diagnostic refinement:** refine, escalate, or reclassify the diagnosis when molecular findings warrant it.
- **F3 — Concurrent diagnosis:** detect a second or concurrent haematological diagnosis.
- **F4 — Prognosis:** provide clinically appropriate molecular prognostic interpretation.
- **F5 — Therapeutic relevance:** identify therapeutically relevant molecular findings.
- **F6 — Molecular MRD:** identify the preferred appropriate molecular MRD target when one is present.
- **F7 — Possible germline variant:** identify a variant that is potentially germline in the supplied clinical context.
- **F8 — Germline predisposition syndrome:** identify the associated germline predisposition syndrome.
- **F9 — Disease-specific molecular prognostic system:** correctly recognise and apply molecular variables within the formal prognostic systems deliberately tested by Dublin: **IPSS-M, MIPSS70+/MIPSS70+ v2.0, and CPSS-Mol**. ELN AML risk is assessed under F4, not F9.

## Scoring rule

For a given case, an F-function is applicable when one or more RxCy criteria map to it. It is `met` only when **all** mapped criteria are marked `met=true`. Any mapped criterion with `met=false` makes that F-function `not_met`. A function with no mapped criteria for that case is `not_applicable`.

The mapping below is authoritative. Do not duplicate it in Python, prompts, or another metadata file.

## Machine-readable specification

```json
{
  "case_criteria_to_function": {
    "1": {
      "R1C1": "F1",
      "R1C2": "F2",
      "R2C1": "F4",
      "R3C1": "F5",
      "R4C1": "F6",
      "R5C1": "F7",
      "R5C2": "F8"
    },
    "10": {
      "R1C1": "F1",
      "R1C2": "F1",
      "R2C1": "F9"
    },
    "2": {
      "R1C1": "F1",
      "R1C2": "F2",
      "R3C1": "F5",
      "R4C1": "F6"
    },
    "3": {
      "R1C1": "F1",
      "R1C2": "F2",
      "R1C3": "F3",
      "R2C1": "F4",
      "R4C1": "F6"
    },
    "4": {
      "R1C1": "F2",
      "R1C2": "F2",
      "R2C1": "F9",
      "R5C1": "F7",
      "R5C2": "F8"
    },
    "5": {
      "R1C1": "F2",
      "R1C2": "F3",
      "R2C1": "F9"
    },
    "6": {
      "R1C1": "F1",
      "R2C1": "F4",
      "R2C2": "F9",
      "R2C3": "F9",
      "R2C4": "F9"
    },
    "7": {
      "R1C1": "F1",
      "R2C1": "F9",
      "R2C2": "F9",
      "R5C1": "F7",
      "R5C2": "F8"
    },
    "8": {
      "R1C1": "F1",
      "R1C2": "F3",
      "R2C1": "F9",
      "R2C2": "F9"
    },
    "9": {
      "R1C1": "F2",
      "R2C1": "F4",
      "R3C1": "F5"
    }
  },
  "functions": {
    "F1": "Integrate NGS findings with the existing diagnosis.",
    "F2": "Refine, escalate, or reclassify the diagnosis when the molecular findings warrant it.",
    "F3": "Detect a second or concurrent haematological diagnosis.",
    "F4": "Provide clinically appropriate molecular prognostic interpretation.",
    "F5": "Identify therapeutically relevant molecular findings.",
    "F6": "Identify the preferred appropriate molecular MRD target when one is present.",
    "F7": "Identify a variant that is potentially germline in the supplied clinical context.",
    "F8": "Identify the associated germline predisposition syndrome.",
    "F9": "Correctly recognise and apply molecular variables within the disease-specific prognostic systems deliberately tested by Dublin: IPSS-M, MIPSS70+/MIPSS70+ v2.0, and CPSS-Mol."
  },
  "schema_version": 1,
  "suite": "nel-validate-dublin"
}
```
