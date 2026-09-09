# Task

Summarize the supplied semantic audit packet for human review.

This is a presentation task only. Do not adjudicate, correct, add, or remove any clinical conclusion. Do not introduce facts that are not in the packet.

The packet is decision-centric. Each row with a `decision_id` is one explicit owner decision/reason preserved in the structured proformas, including positive, negative, neutral and non-reportable decisions. Evidence challenge/audit/adjudication history has already been folded into the relevant owner decision or evidence item rather than repeated as separate dissent decisions. Rare `review_context` rows have no `decision_id`; they are context only and are not coverage units.

Write a concise audit log, not a field-by-field dump. Group closely related source decisions when that improves readability, but do not group unrelated decisions merely to shorten the output.

For each summary group:
- identify the clinical topic in plain language;
- state what was considered and the recorded reason(s);
- state the final disposition, including whether it was reported or not reported;
- when evidence review mattered, explain what the supplied evidence interpretation said and the recorded concern/resolution;
- preserve explicit negative and neutral decisions even when they did not reach the report.

Use the supplied human-readable variant descriptions. Do not refer to decision IDs or other opaque runtime identifiers in the prose. Evidence entries are deliberately compact: `interpretation` says what the source evidence meant; `final_status` records accepted/rejected use when known; `review` contains the recorded concern/resolution when that evidence was challenged.

Every supplied `decision_id` must appear exactly once in `source_decision_ids`, either alone or in one grouped summary. IDs are linkage metadata only and must not appear in the prose fields. Rows without a `decision_id` do not belong in `source_decision_ids`.

## Semantic audit packet

{{ input.audit_items }}

## Deterministic retry feedback

{{ input.audit_feedback }}

If the retry feedback is `null`, this is the first attempt. Otherwise repair only the structural coverage defect described there while preserving packet-faithful content.

## Required output

Return YAML only:

summaries:
  - source_decision_ids:
      - owner:prognosis:prognosis.classification[0]
    domain: prognosis
    topic: Concise human-readable topic
    summary: Concise audit narrative covering the supplied decision(s), reasons, evidence meaning, and final disposition.
