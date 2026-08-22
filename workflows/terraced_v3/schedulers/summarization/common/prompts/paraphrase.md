# Paraphrase one planned report sentence

Rewrite the supplied `draft_sentence` as one concise, clinically readable, self-contained report sentence.

Requirements:
- preserve every semantic proposition in every supplied `source_facts` row;
- when multiple source facts were merged, retain all of them in the one output sentence;
- when one source fact was split across several planned sentences, preserve the semantic portion represented by this planned sentence without contradicting the full source fact;
- preserve disease/gene scope, polarity, uncertainty and authoritative qualifiers;
- add no new clinical proposition;
- do not rely on an adjacent sentence for meaning;
- do not include citations or card tags;
- return only the requested YAML.

{{output_contract}}

# Planned sentence and its source facts
```yaml
{{sentence_plan}}
```
