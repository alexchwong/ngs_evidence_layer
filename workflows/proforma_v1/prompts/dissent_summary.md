# Task

Summarize the supplied semantic-dissent packet for human-readable presentation.

This is a presentation task only. Do not adjudicate the clinical question, alter any clinical conclusion, change an issue status, or introduce facts that are not present in the packet.

For each substantive statement, produce:
- `statement`: the statement under review;
- `concern_critique`: the substantive concern or critique;
- `decision_and_basis`: the final disposition shown by the supplied history and the basis recorded there.

You may combine multiple source issues into one item only when they concern the same substantive statement or the same substantive criticism of that statement. Do not combine unrelated statements merely to shorten the output.

Every supplied `id` must appear exactly once in `source_issue_ids`. Do not invent, omit, or duplicate IDs.

If the ledger remains unresolved, say so plainly in `decision_and_basis`. Do not make an unresolved issue appear resolved.

Source issue IDs are linkage metadata only. Do not mention them in the prose fields.

## Semantic dissent packet

{{ input.dissent_items }}

## Deterministic retry feedback

{{ input.audit_feedback }}

If the retry feedback is `null`, this is the first attempt. Otherwise, repair exactly the structural coverage defect described there while preserving ledger-faithful content.

## Required output

Return YAML only in this shape:

summaries:
  - source_issue_ids:
      - D001
      - D002
    statement: Concise statement being reviewed.
    concern_critique: Concise combined concern or critique.
    decision_and_basis: Final recorded decision/disposition and its recorded basis.
