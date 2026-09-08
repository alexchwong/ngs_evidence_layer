# `default` workflow configs

Each YAML file in this directory is a selectable configuration for the `default` workflow. The browser UI discovers all `*.yaml` files here and shows the selector only when workflow `default` is selected. `default.yaml` is the shipped default.

Prompt modules are referenced by `{{ module "name" }}` in the default clinical prompts. Each module selects a versioned asset at `prompts/modules/<name>/<version>.md`. Disabled modules render exactly `(this section intentionally left blank)` and do not render their section heading.

The deterministic enrichment `protein_hgvs_one_letter_alias` controls whether an unambiguous three-letter simple protein substitution such as `p.Arg175His` is additionally exposed to downstream models as the one-letter alias `R175H`. It never rewrites the canonical reported variant.

Outside the UI, set `NEL_DEFAULT_CONFIG` to a config stem from this directory (for example `default`) or to an absolute path to a frozen config copy. If unset, `default.yaml` is used.

Versioned prompt assets should be treated as immutable after benchmarking; add `v2.md`, `v3.md`, etc. rather than silently changing a benchmarked version.
