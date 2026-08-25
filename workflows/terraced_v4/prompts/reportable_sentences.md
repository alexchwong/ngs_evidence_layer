# Generate one reportable sentence per schema element

For EVERY supplied schema element, write exactly one concise, self-contained clinical report sentence. Preserve the element's meaning and disease/variant scope. Do not add new clinical claims. Do not include citations.

Return YAML only, preserving schema IDs and order:
```yaml
sentences:
  - schema_id: "DX-WHO5-01"
    sentence: "One self-contained report sentence."
```
