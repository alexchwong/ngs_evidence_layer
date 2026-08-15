#!/usr/bin/env python3
"""Deterministic opaque runtime tags for model-facing evidence cards."""
import hashlib


ALGORITHM = "sha256-6hex-collision-resolved-global-eligible-set"


def build_card_tags(card_ids):
    """Return stable six-hex tags for *card_ids* independent of render subsets.

    IDs are sorted before collision resolution. Callers that need tags to remain
    identical across workflow stages must supply the same eligibility universe
    (normally every blacklist-eligible corpus card for the case run).
    """
    used = {}
    rows = []
    for card_id in sorted(set(card_ids)):
        salt = 0
        while True:
            seed = card_id if salt == 0 else f"{card_id}#{salt}"
            tag = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]
            if tag not in used:
                used[tag] = card_id
                rows.append({"card_tag": tag, "card_id": card_id})
                break
            if used[tag] == card_id:
                break
            salt += 1
    return {
        "schema_version": "1.0",
        "algorithm": ALGORITHM,
        "tags": rows,
    }


def tag_by_id(tag_map):
    return {row["card_id"]: row["card_tag"] for row in tag_map.get("tags", [])}


def id_by_tag(tag_map):
    return {row["card_tag"]: row["card_id"] for row in tag_map.get("tags", [])}


def subset_tag_map(tag_map, card_ids):
    wanted = set(card_ids)
    return {
        "schema_version": tag_map.get("schema_version", "1.0"),
        "algorithm": tag_map.get("algorithm"),
        "tags": [row for row in tag_map.get("tags", []) if row.get("card_id") in wanted],
    }
