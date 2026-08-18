# Final sentence-to-fact citation alignment

Add citation dispositions to the supplied uncited report by semantically matching each report sentence to the accepted category facts.

The accepted fact records include citations that were assigned earlier by direct reason-to-card semantic matching. Do not search for new evidence and do not change the clinical prose.

For every sentence-ending full stop in the report:
- identify the accepted fact or facts represented by that sentence;
- append the union of their non-null runtime card tags immediately after the full stop;
- if all matched source facts have `citation: null`, append `(no citation required)`;
- if a sentence cannot be reasonably matched to any accepted fact, return exactly `UNMATCHED_SUMMARY_SENTENCE` instead of a report. This indicates synthesis drift and requires the summary to be redrafted.

Required syntax:
`Sentence. [card:abcdef][card:123456]`
or
`Sentence. (no citation required)`

Return the complete report only. Do not add or remove words, headings or sentences. Do not create numeric citations or a bibliography.
