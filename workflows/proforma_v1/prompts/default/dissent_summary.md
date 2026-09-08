# Task

Summarize the supplied semantic-dissent packet for human-readable presentation.

This is a presentation task only. Do not adjudicate the clinical question, alter any clinical conclusion, change an issue status, or introduce facts that are not present in the packet.

For each substantive statement, produce:

- `statement`: the statement under review;
- `concern`: the substantive concern or critique;
- `decision_and_basis`: the final disposition shown by the supplied history and the basis recorded there.

You may combine multiple source issues into one item only when they concern the same substantive statement or the same substantive criticism of that statement. Do not combine unrelated statements merely to shorten the output.

Every supplied `issue_id` must appear exactly once in `source_issue_ids`. Do not invent, omit, or duplicate IDs.

If the ledger remains unresolved, say so plainly in `decision_and_basis`. Do not make an unresolved issue appear resolved.

Return only the requested structured artifact.
