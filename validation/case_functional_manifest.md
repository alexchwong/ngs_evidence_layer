# Functional validation design note

This file is retained only because historical/legacy workflow documentation refers to it as an evaluator-only asset.

It is **not** a validation registry, selector map, marking source, or runtime input. Do not add case IDs, marking criteria, suite filenames, or workflow routing logic here.

The canonical functional validation suite is self-described by its Markdown front matter and cases. Discover the current suite and selectors through:

```bash
python validation/case_registry.py list
```

Retrieve developer/evaluator content through the central registry only. The canonical schema and fair-marking rules are defined in `validation/DEVEL.md`.

This file may be removed once legacy documentation no longer references it.
