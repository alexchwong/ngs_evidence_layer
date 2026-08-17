# Modify card retrieval blacklist

Use this prompt when a user wants LLM-assisted editing of `output/corpus/blacklist.yaml`.

## Inputs

Read:

1. the user's requested retrieval restrictions;
2. `output/corpus/blacklist.yaml`;
3. `output/corpus/nel.corpus.json` only as needed to resolve exact `publication_key`, `card_id`, category, or gene values.

Do not modify the corpus or retrieval code during this task.

## Goal

Edit `output/corpus/blacklist.yaml` so it expresses the user's policy exactly while preserving unrelated existing rules.

## Blacklist semantics

Normal card retrieval occurs first. The blacklist only removes or restricts cards that normal retrieval would otherwise make eligible.

- `enabled: false` at the root disables all blacklist filtering.
- `papers.<publication_key>.enabled: false` excludes that entire publication.
- `include: []`, or a missing `include`, means no include restriction for that dimension.
- A non-empty `include` requires the card to match at least one listed value in that dimension.
- Any `exclude` match rejects the card. Exclusion wins over inclusion.
- Global rules and paper-specific rules are combined with AND semantics.
- `categories` operate on the card's single `category`.
- `genes.include` requires at least one listed gene on the card; gene-less cards therefore fail a non-empty gene include rule.
- `genes.exclude` rejects a card if any listed gene occurs on it.
- `cards.include` / `cards.exclude` operate on exact `card_id` values.
- Gene matching is case-insensitive; write canonical uppercase gene symbols.
- Valid categories are `diagnosis`, `prognosis`, `treatment`, `biomarker`, and `germline`.

## Editing rules

1. Prefer the narrowest rule that expresses the request.
   - Whole paper unwanted -> `enabled: false`.
   - Only certain categories wanted from a paper -> `categories.include`.
   - Particular genes unwanted -> `genes.exclude`.
   - Particular known bad cards -> `cards.exclude`.
2. Use exact `publication_key` values from the corpus. Never guess a key from a paper nickname or citation.
3. Use exact `card_id` values from the corpus. Never invent card IDs.
4. Preserve all unrelated blacklist entries and comments where practical.
5. Do not put the same value in both `include` and `exclude` for one dimension.
6. Do not create duplicate YAML keys for the same paper. Merge requested restrictions into one paper mapping.
7. If the user's wording is ambiguous between excluding a whole paper and restricting only a category/gene subset, choose the narrower interpretation supported by their wording; if no reasonable interpretation exists, state the ambiguity rather than guessing.
8. Do not use blacklist rules to broaden retrieval. An `include` rule cannot force retrieval of a card that normal retrieval would not select.

## Verification

Before finishing, check that:

- every named publication exists in `nel.corpus.json`;
- every named card exists and belongs to the stated publication;
- every category is valid;
- gene symbols are uppercase;
- no include/exclude list contains duplicates or overlaps;
- the YAML remains syntactically valid;
- the resulting rules implement the requested policy without changing unrelated rules.

Return the updated blacklist and briefly state what retrieval behaviour changed.
