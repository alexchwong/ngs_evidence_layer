# Reject-only semantic preservation check

Judge only whether the paraphrased sentence faithfully preserves the supplied planned meaning. Do not rewrite anything.

You are given only:
- the planner's `draft_sentence`;
- the immutable `source_facts` from which that sentence was constructed;
- `split_source_fact_ids`, identifying any source fact intentionally distributed across more than one planned sentence;
- the `paraphrased_sentence`.

Pass only if:
- the paraphrased sentence is semantically equivalent to the `draft_sentence`;
- it is self-contained;
- it preserves scope, polarity, uncertainty, authority and clinically material qualifiers;
- it adds no new clinical proposition;
- for each source fact **not** listed in `split_source_fact_ids`, the complete source proposition remains represented;
- for a listed split source fact, the sentence faithfully preserves the portion expressed by the supplied `draft_sentence` and does not contradict or overstate the complete source fact.

Do not propose alternate wording. Do not change source attribution. Return only the requested YAML.

{{output_contract}}
