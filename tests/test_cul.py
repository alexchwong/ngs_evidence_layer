"""Corpus user layer regression tests.

Run: python tests/test_cul.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core import corpus as corpus_core  # noqa: E402
from scripts.core import cul as cul_core  # noqa: E402
from scripts.core import rendering as core_rendering  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def expect_error(label, fn, fragment):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - the message is the assertion
        check(label, fragment in str(exc), f"(got: {exc})")
    else:
        check(label, False, "(no error raised)")


def profile(cards_doc, amendments=None, scope=None, name="test"):
    return {
        "schema_version": "1.0",
        "profile": name,
        "description": "",
        "scope": scope if scope is not None else {"enabled": True, "global": {}, "papers": {}},
        "amendments": amendments or {},
    }


def main():
    document, index, digest = corpus_core.load_corpus(
        corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX
    )
    cards = corpus_core.flatten(document)
    base = cul_core.base_cards(document)
    target = sorted(base)[0]
    other = sorted(base)[1]
    sha = cul_core.base_digest(base[target])

    print("shipped default profile")
    default_path = cul_core.profile_path(cul_core.DEFAULT_PROFILE)
    if default_path.is_file():
        layer = cul_core.load_profile(default_path, corpus_document=document, cards=cards)
        allowed, _ = cul_core.eligible_cards(cards, layer, verbose=False)
        legacy = corpus_core.blacklist_cards(cards, corpus_core.DEFAULT_BLACKLIST)
        check(
            "default profile reproduces legacy blacklist retrieval exactly",
            [c["card_id"] for c in allowed] == [c["card_id"] for c in legacy],
        )

    print("card creation is refused")
    expect_error(
        "amendment naming an unknown card is rejected",
        lambda: cul_core.resolve_profile(
            profile(document, {"not-a-real-card-C9999": {"interpretation": "x"}}),
            corpus_document=document, cards=cards,
        ),
        "cannot create cards",
    )

    print("field allowlist")
    for field in ("card_id", "publication_key", "locator", "citation_display", "secondary_citation"):
        expect_error(
            f"{field} is not editable",
            lambda f=field: cul_core.resolve_profile(
                profile(document, {target: {"base_sha256": sha, f: "x"}}),
                corpus_document=document, cards=cards,
            ),
            "uneditable or unknown field",
        )

    print("value validation")
    expect_error(
        "unknown category is rejected",
        lambda: cul_core.resolve_profile(
            profile(document, {target: {"base_sha256": sha, "category": "invented"}}),
            corpus_document=document, cards=cards,
        ),
        "category must be one of",
    )
    expect_error(
        "evidence tier outside the schema enum is rejected",
        lambda: cul_core.resolve_profile(
            profile(document, {target: {"base_sha256": sha, "evidence_tier": "very strong"}}),
            corpus_document=document, cards=cards,
        ),
        "evidence_tier must be one of",
    )
    schema = json.loads((REPO_ROOT / "schema" / "ingestion_package_schema.json").read_text(encoding="utf-8"))
    check(
        "evidence tier vocabulary matches the ingestion schema",
        set(cul_core.EVIDENCE_TIERS)
        == set(schema["$defs"]["card"]["properties"]["evidence_tier"]["enum"]),
    )
    accepted_tier = next(
        t for t in cul_core.EVIDENCE_TIERS if t != base[target]["evidence_tier"]
    )
    layer_tier = cul_core.resolve_profile(
        profile(document, {target: {"base_sha256": sha, "evidence_tier": accepted_tier}}),
        corpus_document=document, cards=cards,
    )
    applied_tier = cul_core.apply_amendments(cards, layer_tier)
    check(
        "a schema-valid tier is accepted and applied",
        next(c for c in applied_tier if c["card_id"] == target)["evidence_tier"] == accepted_tier,
    )

    expect_error(
        "disease outside the vocabulary is rejected",
        lambda: cul_core.resolve_profile(
            profile(document, {target: {"base_sha256": sha, "diseases": ["Not A Disease"]}}),
            corpus_document=document, cards=cards,
        ),
        "outside the disease vocabulary",
    )
    expect_error(
        "an amendment that changes nothing is rejected",
        lambda: cul_core.resolve_profile(
            profile(document, {target: {"base_sha256": sha,
                                        "interpretation": base[target]["interpretation"]}}),
            corpus_document=document, cards=cards,
        ),
        "changes nothing",
    )

    print("staleness")
    stale_layer = cul_core.resolve_profile(
        profile(document, {target: {"base_sha256": "0" * 64, "interpretation": "changed"}}),
        corpus_document=document, cards=cards, strict=False,
    )
    check("stale amendment is reported", stale_layer["stale"] == [target])
    applied = cul_core.apply_amendments(cards, stale_layer)
    unchanged = next(c for c in applied if c["card_id"] == target)
    check(
        "stale amendment does not apply",
        unchanged["interpretation"] == base[target]["interpretation"]
        and not unchanged.get("cul_amended"),
    )

    print("application")
    layer = cul_core.resolve_profile(
        profile(document, {
            target: {"base_sha256": sha, "interpretation": "Amended interpretation."},
            other: {"base_sha256": cul_core.base_digest(base[other]), "category": "prognosis"},
        }),
        corpus_document=document, cards=cards,
    )
    applied = cul_core.apply_amendments(cards, layer)
    a = next(c for c in applied if c["card_id"] == target)
    b = next(c for c in applied if c["card_id"] == other)
    check("interpretation is replaced", a["interpretation"] == "Amended interpretation.")
    check("original interpretation is preserved",
          a["cul_base_interpretation"] == base[target]["interpretation"])
    check("interpretation amendment is flagged for disclosure",
          a.get("cul_interpretation_amended") is True)
    check("category amendment applies", b["category"] == "prognosis")
    check("category amendment is not flagged for disclosure",
          not b.get("cul_interpretation_amended"))
    check("unamended cards are untouched",
          not any(c.get("cul_amended") for c in applied if c["card_id"] not in {target, other}))

    print("digest")
    same = cul_core.resolve_profile(
        profile(document, {target: {"base_sha256": sha, "interpretation": "Amended interpretation."},
                           other: {"base_sha256": cul_core.base_digest(base[other]),
                                   "category": "prognosis"}}),
        corpus_document=document, cards=cards,
    )
    check("digest is stable across identical profiles",
          same["cul_sha256"] == layer["cul_sha256"])
    different = cul_core.resolve_profile(
        profile(document, {target: {"base_sha256": sha, "interpretation": "Other text."}}),
        corpus_document=document, cards=cards,
    )
    check("digest changes with content", different["cul_sha256"] != layer["cul_sha256"])

    print("frozen layer binding")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cul.json"
        cul_core.freeze(layer, path)
        check("frozen layer round-trips",
              cul_core.load_frozen(path)["cul_sha256"] == layer["cul_sha256"])
        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["amendments"][other]["category"] = "treatment"
        path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
        expect_error("tampered frozen layer is refused",
                     lambda: cul_core.load_frozen(path), "modified since setup")

    print("reference disclosure")
    picked = [a, b] + [c for c in applied if c["publication_key"] == a["publication_key"]][:1]
    lines = core_rendering.card_lines([c for c in picked if c["publication_key"] == a["publication_key"]])
    references, _map = core_rendering.assign_references(lines)
    tail = "\n".join(core_rendering._render_tail(references, [], [], []))
    check("amended card is named in the reference note",
          cul_core.short_card_id(target) in tail and "custom corpus edit used" in tail)
    check("profile name appears in the reference note", f'"{layer["profile"]}"' in tail)

    only_scope = cul_core.resolve_profile(
        profile(document, {other: {"base_sha256": cul_core.base_digest(base[other]),
                                   "category": "prognosis"}}),
        corpus_document=document, cards=cards,
    )
    scoped = cul_core.apply_amendments(cards, only_scope)
    sb = next(c for c in scoped if c["card_id"] == other)
    lines = core_rendering.card_lines([sb])
    references, _map = core_rendering.assign_references(lines)
    tail = "\n".join(core_rendering._render_tail(references, [], [], []))
    check("classification-only amendment produces no reference note",
          "custom corpus edit" not in tail)

    print("scope model")
    scope_layer = cul_core.resolve_profile(
        profile(document, {}, scope={
            "enabled": True,
            "global": {"cards": {"exclude": [target]}},
            "papers": {base[target]["card_id"].rsplit("-C", 1)[0]: {
                "categories": {"exclude": ["biomarker"]}
            }},
        }),
        corpus_document=document, cards=cards,
    )
    allowed, _ = cul_core.eligible_cards(cards, scope_layer, verbose=False)
    allowed_ids = {c["card_id"] for c in allowed}
    check("card-level exclusion removes exactly that card", target not in allowed_ids)
    paper_key = base[target]["card_id"].rsplit("-C", 1)[0]
    check(
        "a paper category rule removes only that category",
        not any(
            c["publication_key"] == paper_key and c["category"] == "biomarker"
            for c in allowed
        )
        and any(c["publication_key"] == paper_key for c in allowed),
    )
    check(
        "a rule is stored as a rule, not expanded into card ids",
        not scope_layer["scope"]["papers"][paper_key]["cards"]["exclude"],
    )

    print("exemptions")
    paper_key = base[target]["card_id"].rsplit("-C", 1)[0]
    blocked_category = base[target]["category"]
    exempt_layer = cul_core.resolve_profile(
        profile(document, {}, scope={
            "enabled": True,
            "global": {},
            "papers": {paper_key: {"categories": {"exclude": [blocked_category]}}},
            "exemptions": [target],
        }),
        corpus_document=document, cards=cards,
    )
    allowed, _ = cul_core.eligible_cards(cards, exempt_layer, verbose=False)
    allowed_ids = {c["card_id"] for c in allowed}
    check("an exemption readmits a card a rule suppresses", target in allowed_ids)
    siblings = [
        c["card_id"] for c in cards
        if c["publication_key"] == paper_key
        and c["category"] == blocked_category
        and c["card_id"] != target
    ]
    check(
        "the rule still suppresses every other card it names",
        siblings and not any(s in allowed_ids for s in siblings),
    )
    check(
        "the rule is unchanged by the exemption",
        exempt_layer["scope"]["papers"][paper_key]["categories"]["exclude"]
        == [blocked_category],
    )

    both_layer = cul_core.resolve_profile(
        profile(document, {}, scope={
            "enabled": True,
            "global": {"cards": {"exclude": [target]}},
            "papers": {paper_key: {"categories": {"exclude": [blocked_category]}}},
            "exemptions": [target],
        }),
        corpus_document=document, cards=cards,
    )
    both_allowed, _ = cul_core.eligible_cards(cards, both_layer, verbose=False)
    check(
        "an explicit exclusion outranks an exemption",
        target not in {c["card_id"] for c in both_allowed},
    )
    expect_error(
        "an exemption naming an unknown card is rejected",
        lambda: cul_core.resolve_profile(
            profile(document, {}, scope={"enabled": True, "global": {}, "papers": {},
                                         "exemptions": ["not-a-card-C9999"]}),
            corpus_document=document, cards=cards,
        ),
        "exemptions names unknown card",
    )

    print("short card id")
    check("short id extracts the ordinal",
          cul_core.short_card_id("weeks-2023-nejm-evidence-2-na-C0007") == "C0007")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): " + ", ".join(FAILURES))
        return 1
    print("all CUL tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
