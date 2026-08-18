"""Retrieval provenance generation shared by reporting workflows."""
from __future__ import annotations

from datetime import datetime, timezone

def provenance(corpus, corpus_path, index_path, digest, card_ids):
    return {
        "corpus_version": corpus.get("corpus_version"),
        "corpus_generated_at": corpus.get("generated_at"),
        "corpus_sha256": digest,
        "corpus_path": str(corpus_path),
        "index_path": str(index_path),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "card_ids": sorted(card_ids),
    }
