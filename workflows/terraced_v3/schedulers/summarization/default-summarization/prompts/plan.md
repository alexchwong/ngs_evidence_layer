# Report fact selection and sentence construction

Transform the supplied immutable reportable facts into an auditable report plan. Citation attribution is already locked to each fact and is not part of this task.

Decide explicitly for every fact:
1. include or omit it from the final report;
2. the final sentence order;
3. which included facts should be merged into one sentence;
4. whether a fact needs to be split across more than one sentence.

Prefer concise clinical reporting, but do not omit a nonredundant fact merely to shorten the report. An omission must be safe and must have a concise audit reason. Keep report domains separate and use canonical section order: diagnosis, prognosis, treatment, biomarker/MRD, germline.

For every sentence plan, write a complete `draft_sentence` that semantically represents all listed `source_fact_ids`. Do not choose, alter, or reproduce citations.

{{output_contract}}

# Immutable cited reportable facts
```yaml
{{facts}}
```
