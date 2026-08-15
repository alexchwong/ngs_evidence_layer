# Capture the supplied clinical case

## Task

Identify the exact supplied content that constitutes the clinical case.

## Task-specific rules

- Preserve supplied case content verbatim and in its original order.
- Include all supplied patient, specimen, morphology, laboratory, cytogenetic, molecular, treatment, and other clinical case information.
- Exclude workflow instructions, output requests, and other non-case commentary.
- Do not interpret, summarise, normalise, or reorganise the case.
- Do not add literature information, model knowledge, or facts not supplied by the case source.

## Output contract

Return only the clinical case text for `case.md`.

## Final check

Before returning, verify privately that every retained word came from the designated case source and that no supplied clinical case information was omitted.
