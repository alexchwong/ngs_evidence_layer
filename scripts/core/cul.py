"""Corpus user layer (CUL): non-destructive per-profile corpus customisation.

A CUL profile is an overlay. It never edits ``accept/``, ``archive/`` or
``output/corpus/``; it is resolved against the incorporated corpus at run setup,
frozen into the run, and applied to flattened cards during retrieval.

Two edit classes live in a profile:

``scope``
    Reachability. The historical ``blacklist.json`` policy shape, unchanged, so
    an existing blacklist migrates verbatim. Changes which cards retrieval can
    reach; never changes what a card says.

``amendments``
    Assertion and classification. Per-card field overrides. Card creation is not
    supported: an amendment must name a card that exists in the corpus, because
    an invented card would render under a real citation with no locator and no
    evidence behind it.

An amendment binds to the corpus card it was authored against by
``base_sha256``. When a redo changes that card, the amendment goes stale and
refuses to apply, rather than silently reattaching to text that no longer
exists.

Only an amended ``interpretation`` produces a reference-list note in the final
report: a scope or classification change alters which cards are reached but
never misquotes a source.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path

from scripts.core import corpus as corpus_core

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CUL_DIR = REPO_ROOT / "config" / "cul"
DEFAULT_PROFILE = "default"
SCHEMA_VERSION = "1.0"
ENV_ACTIVE_LAYER = "NEL_CUL_LAYER"

PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Fields a profile may override. ``card_id``, ``publication_key``, ``locator``
#: and every citation field are deliberately absent: they bind a card to its
#: source and must not be editable from a user layer.
AMENDABLE_FIELDS = ("interpretation", "category", "genes", "diseases", "evidence_tier")

#: Only these amendments are disclosed in the rendered reference list.
DISCLOSED_FIELDS = ("interpretation",)

#: Closed set from ``schema/ingestion_package_schema.json``, strongest first.
#: A user layer must not be able to assign a tier no accepted card could hold.
EVIDENCE_TIERS = (
    "guideline criterion",
    "multivariable-adjusted",
    "univariable or descriptive",
    "restated secondary",
)


class CULError(ValueError):
    """Raised for any invalid profile, unknown card, or stale amendment."""


def canonical_sha256(document) -> str:
    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def short_card_id(card_id: str) -> str:
    """``weeks-2023-...-C0007`` -> ``C0007``; unrecognised IDs pass through."""
    text = str(card_id or "")
    match = re.search(r"(C\d{4,})$", text)
    return match.group(1) if match else text


def validate_profile_name(name: str) -> str:
    name = str(name or "").strip()
    if not PROFILE_NAME_RE.fullmatch(name):
        raise CULError(
            "invalid CUL profile name; use letters, numbers, '.', '_' and '-', "
            "starting with a letter or number"
        )
    return name


def profile_path(name: str, *, cul_dir: Path | None = None) -> Path:
    return (Path(cul_dir) if cul_dir else DEFAULT_CUL_DIR) / f"{validate_profile_name(name)}.json"


def available_profiles(*, cul_dir: Path | None = None) -> list[str]:
    directory = Path(cul_dir) if cul_dir else DEFAULT_CUL_DIR
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


# --------------------------------------------------------------------------
# base corpus card state
# --------------------------------------------------------------------------

def base_cards(corpus_document) -> dict[str, dict]:
    """Map card_id to the raw corpus card object, the amendment base image."""
    result = {}
    for publication in corpus_document.get("publications", []):
        document = publication.get("document", {})
        for card in document.get("cards", []):
            card_id = card.get("card_id")
            if card_id:
                result[card_id] = card
    return result


def base_digest(card: dict) -> str:
    return canonical_sha256(card)


# --------------------------------------------------------------------------
# profile validation
# --------------------------------------------------------------------------

def _validate_string_list(value, *, field, uppercase=False):
    if not isinstance(value, list):
        raise CULError(f"{field} must be a JSON array")
    out = []
    seen = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CULError(f"{field}[{index}] must be a non-empty string")
        item = item.strip().upper() if uppercase else item.strip()
        if item in seen:
            raise CULError(f"{field} contains duplicate value {item!r}")
        seen.add(item)
        out.append(item)
    return out


def _validate_amendment(card_id, raw, base, *, vocab):
    if not isinstance(raw, dict):
        raise CULError(f"amendments.{card_id} must be a JSON object")
    unknown = set(raw) - set(AMENDABLE_FIELDS) - {"base_sha256", "amended_at", "note"}
    if unknown:
        raise CULError(
            f"amendments.{card_id} contains uneditable or unknown field(s): "
            + ", ".join(sorted(unknown))
        )
    fields = {}
    for field in AMENDABLE_FIELDS:
        if field not in raw:
            continue
        value = raw[field]
        if field == "interpretation":
            if not isinstance(value, str) or not value.strip():
                raise CULError(f"amendments.{card_id}.interpretation must be a non-empty string")
            fields[field] = value.strip()
        elif field == "category":
            if value not in corpus_core.CARD_CATEGORIES:
                raise CULError(
                    f"amendments.{card_id}.category must be one of: "
                    + ", ".join(sorted(corpus_core.CARD_CATEGORIES))
                )
            fields[field] = value
        elif field == "evidence_tier":
            if value not in EVIDENCE_TIERS:
                raise CULError(
                    f"amendments.{card_id}.evidence_tier must be one of: "
                    + ", ".join(EVIDENCE_TIERS)
                )
            fields[field] = value
        elif field == "genes":
            fields[field] = _validate_string_list(
                value, field=f"amendments.{card_id}.genes", uppercase=True
            )
        elif field == "diseases":
            diseases = _validate_string_list(value, field=f"amendments.{card_id}.diseases")
            if vocab is not None:
                unknown_diseases = [d for d in diseases if d not in vocab.DISEASE_SET]
                if unknown_diseases:
                    raise CULError(
                        f"amendments.{card_id}.diseases names term(s) outside the disease "
                        "vocabulary: " + ", ".join(unknown_diseases)
                    )
            fields[field] = diseases
    if not fields:
        raise CULError(f"amendments.{card_id} changes nothing")
    unchanged = [f for f in fields if fields[f] == base.get(f)]
    if len(unchanged) == len(fields):
        raise CULError(f"amendments.{card_id} matches the corpus card and changes nothing")
    return fields


def load_profile(path, *, corpus_document=None, cards=None, strict=True):
    """Load, validate and resolve one profile against the incorporated corpus.

    ``strict`` False downgrades stale amendments to a reported list instead of an
    error, which the browser and ``cul check`` need in order to show a repair.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CULError(f"CUL profile not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CULError(f"CUL profile is not valid JSON: {path}: {exc}") from exc
    return resolve_profile(
        raw, corpus_document=corpus_document, cards=cards, strict=strict, source=str(path)
    )


def resolve_profile(raw, *, corpus_document=None, cards=None, strict=True, source="<memory>"):
    if not isinstance(raw, dict):
        raise CULError(f"CUL profile root must be a JSON object: {source}")
    unknown = set(raw) - {
        "schema_version", "profile", "description", "authored_against_corpus_sha256",
        "scope", "amendments",
    }
    if unknown:
        raise CULError(
            f"CUL profile contains unsupported key(s): " + ", ".join(sorted(unknown))
        )
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise CULError(f"CUL profile schema_version must be {SCHEMA_VERSION!r}: {source}")
    name = validate_profile_name(raw.get("profile"))

    if corpus_document is None and cards is None:
        raise CULError("resolving a CUL profile requires the corpus or flattened cards")
    if cards is None:
        cards = corpus_core.flatten(corpus_document)
    scope = corpus_core.normalise_policy(raw.get("scope"), cards, label="CUL scope")

    try:
        from scripts import vocab as vocab_module
    except Exception:  # vocabulary is optional for pure scope profiles
        vocab_module = None

    base_index = base_cards(corpus_document) if corpus_document is not None else {}
    amendments_raw = raw.get("amendments") or {}
    if not isinstance(amendments_raw, dict):
        raise CULError("CUL amendments must be a mapping keyed by card_id")

    amendments = {}
    stale = []
    for card_id, entry in sorted(amendments_raw.items()):
        if not isinstance(card_id, str) or not card_id.strip():
            raise CULError("CUL amendment keys must be non-empty card_id strings")
        card_id = card_id.strip()
        if base_index and card_id not in base_index:
            raise CULError(
                f"CUL amendment names a card that is not in the corpus: {card_id}. "
                "A user layer cannot create cards."
            )
        base = base_index.get(card_id, {})
        fields = _validate_amendment(card_id, entry, base, vocab=vocab_module)
        recorded = entry.get("base_sha256")
        current = base_digest(base) if base else None
        if base_index and recorded and current and recorded != current:
            stale.append(card_id)
            if strict:
                continue
        amendments[card_id] = {
            **fields,
            "base_sha256": recorded or current,
            "amended_at": entry.get("amended_at"),
            "note": entry.get("note"),
            "stale": card_id in stale,
        }

    layer = {
        "schema_version": SCHEMA_VERSION,
        "profile": name,
        "description": raw.get("description") or "",
        "source": source,
        "scope": scope,
        "amendments": amendments,
        "stale": sorted(stale),
    }
    layer["cul_sha256"] = layer_digest(layer)
    return layer


def layer_digest(layer) -> str:
    """Digest the resolved layer: the thing that actually affects retrieval."""
    material = {
        "profile": layer["profile"],
        "scope": layer["scope"],
        "amendments": {
            card_id: {field: entry[field] for field in AMENDABLE_FIELDS if field in entry}
            for card_id, entry in layer["amendments"].items()
        },
    }
    return canonical_sha256(material)


def empty_layer(profile=None):
    """A permissive layer that names no profile.

    ``profile`` stays None so a run that fell back to the legacy blacklist is not
    recorded as having used a CUL profile it never loaded."""
    layer = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "description": "",
        "source": "<none>",
        "scope": corpus_core.empty_policy(),
        "amendments": {},
        "stale": [],
    }
    layer["cul_sha256"] = layer_digest(layer)
    return layer


# --------------------------------------------------------------------------
# application
# --------------------------------------------------------------------------

def apply_amendments(cards, layer):
    """Return flattened cards with the layer's amendments applied.

    Provenance is attached to every amended card so that downstream rendering can
    disclose an amended interpretation without re-reading the profile.
    """
    amendments = layer.get("amendments") or {}
    if not amendments:
        return [dict(card) for card in cards]
    try:
        from scripts import vocab as vocab_module
    except Exception:
        vocab_module = None

    out = []
    for card in cards:
        entry = amendments.get(card.get("card_id"))
        if not entry or entry.get("stale"):
            out.append(dict(card))
            continue
        amended = dict(card)
        changed = []
        for field in AMENDABLE_FIELDS:
            if field not in entry:
                continue
            value = entry[field]
            if isinstance(value, list):
                value = list(value)
            if amended.get(field) == value:
                continue
            if field == "interpretation":
                amended["cul_base_interpretation"] = card.get("interpretation")
            amended[field] = value
            changed.append(field)
        if not changed:
            out.append(dict(card))
            continue
        if "diseases" in changed and vocab_module is not None and "disease_ancestors" in amended:
            amended["disease_ancestors"] = vocab_module.disease_ancestors(amended["diseases"])
        amended["cul_amended"] = True
        amended["cul_profile"] = layer.get("profile")
        amended["cul_amended_fields"] = sorted(changed)
        amended["cul_interpretation_amended"] = "interpretation" in changed
        out.append(amended)
    return out


def eligible_cards(cards, layer, *, verbose=True):
    """Apply amendments, then scope. Amendments run first so that a category or
    gene change is visible to the scope rules that filter on those dimensions."""
    amended = apply_amendments(cards, layer)
    scope = layer.get("scope") or corpus_core.empty_policy()
    allowed, excluded = corpus_core.apply_blacklist(amended, scope)
    if verbose:
        import sys
        print(
            f"[retrieve] CUL profile '{layer.get('profile')}' "
            f"({layer.get('cul_sha256', '')[:12]}) excluded {len(excluded)} of "
            f"{len(amended)} cards; {len(layer.get('amendments') or {})} amendment(s)",
            file=sys.stderr,
        )
    return allowed, amended


# --------------------------------------------------------------------------
# run binding
# --------------------------------------------------------------------------

def freeze(layer, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frozen = copy.deepcopy(layer)
    path.write_text(json.dumps(frozen, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def load_frozen(path):
    path = Path(path)
    try:
        layer = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CULError(f"frozen CUL layer is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CULError(f"frozen CUL layer is not valid JSON: {path}: {exc}") from exc
    expected = layer.get("cul_sha256")
    if expected and expected != layer_digest(layer):
        raise CULError(f"frozen CUL layer has been modified since setup: {path}")
    return layer


def active_layer(*, explicit=None, verbose=False):
    """Resolve the layer a workflow step should use.

    Precedence: an explicit path or resolved layer, then the frozen layer named
    by the environment, then an empty permissive layer.
    """
    if isinstance(explicit, dict):
        return explicit
    if explicit:
        return load_frozen(explicit)
    from_env = os.environ.get(ENV_ACTIVE_LAYER, "").strip()
    if from_env:
        return load_frozen(from_env)
    return empty_layer()
