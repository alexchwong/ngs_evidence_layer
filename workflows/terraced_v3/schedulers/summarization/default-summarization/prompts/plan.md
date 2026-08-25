# Report statement selection and sentence construction

Transform the supplied immutable reportable statements into an auditable report plan. Citation attribution is already locked to each statement and is not part of this task.

Decide explicitly for every statement:
1. include or omit it from the final report;
2. the final sentence order;
3. which included statements should be merged into one sentence;
4. whether a statement needs to be split across more than one sentence.

Prefer concise clinical reporting, but do not omit a nonredundant statement merely to shorten the report. An omission must be safe and must have a concise audit reason. Keep report domains separate and use canonical section order: diagnosis, prognosis, treatment, biomarker/MRD, germline.

For every sentence plan, write a complete `draft_sentence` that semantically represents all listed `source_statement_ids`. Do not choose, alter, or reproduce citations.

{{output_contract}}

# Immutable cited reportable statements
```yaml
{{statements}}
```

Diagnostic classification statements must always be included; they are answers to the diagnosis question and are never redundant with their supporting reasons.
