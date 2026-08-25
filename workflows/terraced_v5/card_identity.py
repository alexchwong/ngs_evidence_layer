"""Run-global deterministic identity for terraced-v5 corpus cards."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

SCHEMA_VERSION = "1.0"
TAG_HEX_LENGTH = 12
ALGORITHM = "sha256-12hex-collision-resolved-global-corpus"


def _canonical_card_bytes(card: dict) -> bytes:
    return json.dumps(
        card,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def build_manifest(cards: Iterable[dict], *, corpus_sha256: str | None = None) -> dict:
    """Hash every supplied card before retrieval and return a frozen identity map.

    ``card_tag`` identifies the stable card ID. ``content_sha256`` independently
    detects card-content drift.  Collision resolution is deterministic because
    card IDs are sorted before salts are assigned.
    """
    by_id: dict[str, dict] = {}
    for card in cards:
        card_id = card.get("card_id") if isinstance(card, dict) else None
        if not isinstance(card_id, str) or not card_id.strip():
            raise ValueError("every corpus card must have a non-empty string card_id")
        if card_id in by_id and _canonical_card_bytes(by_id[card_id]) != _canonical_card_bytes(card):
            raise ValueError(f"corpus contains conflicting duplicate card_id {card_id!r}")
        by_id.setdefault(card_id, card)

    used: dict[str, str] = {}
    rows = []
    for card_id in sorted(by_id):
        salt = 0
        while True:
            seed = card_id if salt == 0 else f"{card_id}#{salt}"
            tag = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:TAG_HEX_LENGTH]
            owner = used.get(tag)
            if owner is None or owner == card_id:
                used[tag] = card_id
                break
            salt += 1
        rows.append(
            {
                "card_tag": tag,
                "card_id": card_id,
                "content_sha256": hashlib.sha256(_canonical_card_bytes(by_id[card_id])).hexdigest(),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "tag_length": TAG_HEX_LENGTH,
        "corpus_sha256": corpus_sha256,
        "tags": rows,
    }


def tag_by_id(manifest: dict) -> dict[str, str]:
    return {row["card_id"]: row["card_tag"] for row in manifest.get("tags", [])}


def runtime_tag_map(manifest: dict, card_ids: Iterable[str] | None = None) -> dict:
    """Return the three-field map consumed by evidence/citation rendering."""
    wanted = None if card_ids is None else set(card_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "tags": [
            {"card_tag": row["card_tag"], "card_id": row["card_id"]}
            for row in manifest.get("tags", [])
            if wanted is None or row["card_id"] in wanted
        ],
    }
