#!/usr/bin/env python3
"""Manage corpus user layer (CUL) profiles.

Profiles live in ``config/cul/<name>.json`` and are user-owned. They overlay the
incorporated corpus at retrieval time and never modify ``accept/``, ``archive/``
or ``output/corpus/``.

Commands:

    list                       show every profile and its amendment/scope counts
    show    --cul P            print the resolved layer
    new     --cul P            create a profile seeded from the default scope
    check   --cul P            validate and report stale amendments
    diff    --cul P            show every change the profile makes to the corpus
    apply   --cul P --from F   install a profile downloaded from the CUL editor
    --edit                     build/open the Corpus User Layer editor
    edit                       backward-compatible alias for --edit
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core import corpus as corpus_core  # noqa: E402
from scripts.core import cul as cul_core  # noqa: E402


def _corpus():
    document, _index, digest = corpus_core.load_corpus(
        corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX
    )
    return document, corpus_core.flatten(document), digest


def _resolve(name, *, strict=False):
    document, cards, _digest = _corpus()
    layer = cul_core.load_profile(
        cul_core.profile_path(name), corpus_document=document, cards=cards, strict=strict
    )
    return document, cards, layer



def _profile_payload(name: str, document, cards) -> dict:
    """Serializable profile state consumed by the editor."""
    path = cul_core.profile_path(name)
    raw = json.loads(path.read_text(encoding="utf-8"))
    layer = cul_core.load_profile(path, corpus_document=document, cards=cards, strict=False)
    return {
        "profile": layer["profile"],
        "description": layer.get("description") or "",
        "scope": raw.get("scope") or {"enabled": True, "global": {}, "papers": {}},
        "amendments": {
            card_id: {
                **{field: entry[field] for field in cul_core.AMENDABLE_FIELDS if field in entry},
                "base_sha256": entry.get("base_sha256"),
                "stale": entry.get("stale", False),
            }
            for card_id, entry in layer["amendments"].items()
        },
        "stale": layer.get("stale") or [],
    }


def _all_profiles(document, cards) -> dict:
    """Embed every valid CUL profile so the editor can switch without rebuilding."""
    profiles = {}
    for name in cul_core.available_profiles():
        try:
            profiles[name] = _profile_payload(name, document, cards)
        except (ValueError, cul_core.CULError):
            continue
    return profiles


def _vocabulary() -> dict:
    """Closed value sets used by the editor controls and CLI validator."""
    from scripts import vocab as vocab_module

    return {
        "categories": sorted(corpus_core.CARD_CATEGORIES),
        "evidenceTiers": list(cul_core.EVIDENCE_TIERS),
        "diseases": sorted(vocab_module.DISEASES, key=str.casefold),
    }


def _editor_data() -> dict:
    """Build the CUL editor payload from the incorporated corpus only.

    This deliberately has no dependency on ``accept/`` or ``archive/``. The CUL
    is a user overlay on the public incorporated corpus; private evidence belongs
    only to ``build_card_browser.py --full``.
    """
    document, cards, corpus_sha256 = _corpus()
    profiles = _all_profiles(document, cards)
    selected = cul_core.DEFAULT_PROFILE if cul_core.DEFAULT_PROFILE in profiles else None
    cul_profile = profiles[selected] if selected else None

    papers = []
    browser_cards = []
    for entry in document.get("publications", []):
        paper_doc = entry["document"]
        key = paper_doc["publication_key"]
        citation = paper_doc.get("citation", {})
        source = entry.get("source") or {}
        audit = source.get("audit") or {}
        audit_by_card = {
            item.get("card_id"): {
                "verdict": item.get("verdict"),
                "basis": item.get("review_basis"),
            }
            for item in (audit.get("results") or [])
            if item.get("card_id")
        }
        papers.append({
            "key": key,
            "nickname": paper_doc.get("paper_nickname") or key,
            "display": citation.get("display", ""),
            "journal": citation.get("journal", ""),
            "year": citation.get("year"),
            "type": paper_doc.get("publication_type", ""),
            "doi": citation.get("doi", ""),
            "citation": citation,
            "auditModel": audit.get("audit_model"),
            "extractionModel": paper_doc.get("extraction_model"),
            "auditDate": audit.get("audit_date"),
            "evidence": "absent",
        })

        for card in paper_doc.get("cards", []):
            browser_cards.append({
                "id": card["card_id"],
                "shortId": cul_core.short_card_id(card["card_id"]),
                "paper": key,
                "category": card.get("category", ""),
                "tier": card.get("evidence_tier", ""),
                "genes": card.get("genes", []),
                "diseases": card.get("diseases", []),
                "ancestors": card.get("disease_ancestors", []),
                "locator": card.get("locator", ""),
                "secondary": card.get("secondary_citation"),
                "text": card.get("interpretation", ""),
                "baseSha256": cul_core.base_digest(card),
                "audit": audit_by_card.get(card["card_id"]),
            })

    papers.sort(key=lambda item: (-(item["year"] or 0), item["nickname"]))
    browser_cards.sort(key=lambda item: item["id"])
    return {
        "corpusVersion": document.get("corpus_version"),
        "corpusSha256": corpus_sha256,
        "generatedAt": document.get("generated_at"),
        "full": False,
        "evidenceMode": "none",
        "missingPackages": [],
        "mismatchedPackages": [],
        "papers": papers,
        "cards": browser_cards,
        "cul": cul_profile,
        "editor": True,
        "profiles": profiles,
        "vocabulary": _vocabulary(),
    }

def cmd_list(args):
    names = cul_core.available_profiles()
    if not names:
        print("no CUL profiles; create one with: python scripts/cul.py new --cul <name>")
        return 0
    document, cards, _digest = _corpus()
    for name in names:
        try:
            layer = cul_core.load_profile(
                cul_core.profile_path(name), corpus_document=document, cards=cards, strict=False
            )
        except cul_core.CULError as exc:
            print(f"{name}: INVALID ({exc})")
            continue
        allowed, _ = cul_core.eligible_cards(cards, layer, verbose=False)
        stale = layer.get("stale") or []
        line = (
            f"{name}: {len(layer['amendments'])} amendment(s), "
            f"{len(allowed)}/{len(cards)} cards reachable, "
            f"digest {layer['cul_sha256'][:12]}"
        )
        if stale:
            line += f", {len(stale)} STALE"
        print(line)
    return 0


def cmd_show(args):
    _document, _cards, layer = _resolve(args.cul)
    print(json.dumps(layer, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_new(args):
    path = cul_core.profile_path(args.cul)
    if path.exists() and not args.force:
        sys.exit(f"CUL profile already exists: {path}")
    document, cards, _digest = _corpus()
    seed = {"enabled": True, "global": {}, "papers": {}}
    if not args.empty_scope:
        default_path = cul_core.profile_path(cul_core.DEFAULT_PROFILE)
        if default_path.is_file():
            seed = json.loads(default_path.read_text(encoding="utf-8")).get("scope") or seed
        elif Path(corpus_core.DEFAULT_BLACKLIST).is_file():
            seed = json.loads(Path(corpus_core.DEFAULT_BLACKLIST).read_text(encoding="utf-8"))
    profile = {
        "schema_version": cul_core.SCHEMA_VERSION,
        "profile": cul_core.validate_profile_name(args.cul),
        "description": args.description or "",
        "scope": seed,
        "amendments": {},
    }
    cul_core.resolve_profile(profile, corpus_document=document, cards=cards)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CUL PROFILE CREATED: {path}")
    return 0


def cmd_check(args):
    document, cards, layer = _resolve(args.cul)
    stale = layer.get("stale") or []
    allowed, _ = cul_core.eligible_cards(cards, layer, verbose=False)
    print(f"PROFILE={layer['profile']}")
    print(f"CUL_SHA256={layer['cul_sha256']}")
    print(f"AMENDMENTS={len(layer['amendments'])}")
    print(f"REACHABLE={len(allowed)}/{len(cards)}")
    exemptions = layer["scope"].get("exemptions") or []
    print(f"EXEMPTIONS={len(exemptions)}")
    if exemptions:
        print(
            "  Each exemption readmits one card that a rule would otherwise "
            "suppress. Review them if a rule exists for a safety reason."
        )
        for card_id in exemptions:
            print(f"  {card_id}")
    if stale:
        print("STALE=" + ",".join(stale))
        print(
            "\nThese amendments were authored against corpus cards that have since changed.\n"
            "They will not apply until reviewed. Re-edit each card in the CUL editor, or remove\n"
            "the amendment, then re-check."
        )
        return 1
    print("STALE=none")
    return 0


def cmd_diff(args):
    document, cards, layer = _resolve(args.cul)
    base = {card["card_id"]: card for card in cards}
    amended = cul_core.apply_amendments(cards, layer)
    allowed_ids = {c["card_id"] for c in cul_core.eligible_cards(cards, layer, verbose=False)[0]}

    changed = [card for card in amended if card.get("cul_amended")]
    if changed:
        print("## Amendments\n")
        for card in changed:
            print(f"### {card['card_id']}  ({card.get('paper_nickname') or ''})")
            for field in card["cul_amended_fields"]:
                before = base[card["card_id"]].get(field)
                print(f"- {field}:")
                print(f"    before: {before}")
                print(f"    after:  {card.get(field)}")
            print()
    else:
        print("## Amendments\n\nNone.\n")

    exemptions = layer["scope"].get("exemptions") or []
    print(f"## Exemptions ({len(exemptions)} card(s))\n")
    if not exemptions:
        print("None.\n")
    else:
        print("Each readmits one card that a rule would otherwise suppress.\n")
        for card_id in exemptions:
            card = base.get(card_id)
            label = card.get("paper_nickname") or card.get("publication_key") if card else ""
            print(f"- {cul_core.short_card_id(card_id)} ({label})")
        print()

    suppressed = sorted(set(base) - allowed_ids)
    print(f"## Not reachable under this profile ({len(suppressed)} card(s))\n")
    by_paper = {}
    for card_id in suppressed:
        by_paper.setdefault(base[card_id]["publication_key"], []).append(
            cul_core.short_card_id(card_id)
        )
    for paper, ids in sorted(by_paper.items()):
        print(f"- {paper}: {len(ids)} card(s)")
    if layer.get("stale"):
        print("\n## Stale amendments\n")
        for card_id in layer["stale"]:
            print(f"- {card_id}")
    return 0


def cmd_apply(args):
    source = Path(args.source)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"downloaded profile not found: {source}")
    except json.JSONDecodeError as exc:
        sys.exit(f"downloaded profile is not valid JSON: {exc}")
    name = args.cul or raw.get("profile")
    raw["profile"] = cul_core.validate_profile_name(name)
    document, cards, _digest = _corpus()
    layer = cul_core.resolve_profile(raw, corpus_document=document, cards=cards, strict=False)
    if layer.get("stale") and not args.allow_stale:
        sys.exit(
            "downloaded profile contains stale amendments: "
            + ", ".join(layer["stale"])
            + "\nRe-edit them in the CUL editor, or pass --allow-stale to install anyway."
        )
    path = cul_core.profile_path(raw["profile"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CUL PROFILE INSTALLED: {path}")
    print(f"CUL_SHA256={layer['cul_sha256']}")
    print(f"AMENDMENTS={len(layer['amendments'])}")
    if not args.no_rebuild:
        _refresh_editor()
    return 0


def _refresh_editor() -> None:
    """Refresh an already-built CUL editor after a profile install."""
    if not EDITOR_HTML.is_file():
        return
    try:
        _build_editor()
    except (OSError, ValueError, cul_core.CULError) as exc:
        print(f"WARNING: could not refresh {EDITOR_HTML.name}: {exc}")
        print("  Rebuild manually: python scripts/cul.py --edit --no-open --no-watch")
        return
    print(f"EDITOR REFRESHED: {EDITOR_HTML}")


# --------------------------------------------------------------------------
# editor: build, open, and watch for saved profiles
# --------------------------------------------------------------------------

SETTINGS_PATH = REPO_ROOT / "config" / "cul" / "settings.json"
EDITOR_HTML = REPO_ROOT / "config" / "cul" / "corpus-user-layer.html"
EDITOR_TEMPLATE = REPO_ROOT / "scripts" / "assets" / "corpus_user_layer_template.html"
EDITOR_SCRIPT = REPO_ROOT / "scripts" / "assets" / "card_browser_cul.js"
READ_ONLY_BROWSER_HTML = REPO_ROOT / "output" / "reports" / "card-browser.html"


def _settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _downloads_dir(explicit: str | None) -> Path:
    """Where saved profiles land.

    ``~/Downloads`` by default. An explicit path is remembered, so a machine
    whose browser saves elsewhere is configured once rather than every time.
    """
    if explicit:
        return Path(explicit).expanduser()
    remembered = _settings().get("downloads_dir")
    if remembered:
        return Path(remembered).expanduser()
    return Path.home() / "Downloads"


def _build_editor() -> Path:
    """Render the standalone Corpus User Layer editor.

    The editor is generated here, not through ``build_card_browser.py``. Its
    output path is deliberately separate from the read-only browser.
    """
    data = _editor_data()
    template = EDITOR_TEMPLATE.read_text(encoding="utf-8")
    cul_script = EDITOR_SCRIPT.read_text(encoding="utf-8")
    template = template.replace("/*__CUL_LAYER__*/", cul_script)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    html = template.replace("/*__CARD_DATA__*/null", payload)
    EDITOR_HTML.parent.mkdir(parents=True, exist_ok=True)
    EDITOR_HTML.write_text(html, encoding="utf-8")
    return EDITOR_HTML


def _open_in_browser(path: Path) -> bool:
    """Open the editor, preferring whatever the platform actually provides.

    On WSL ``xdg-open`` is frequently absent, so ``wslview`` and ``explorer.exe``
    are tried first; failing everything, the caller prints the path.
    """
    candidates = [["wslview", str(path)]]
    if shutil.which("wslpath"):
        try:
            windows_path = subprocess.run(
                ["wslpath", "-w", str(path)], capture_output=True, text=True, check=True
            ).stdout.strip()
            candidates.append(["explorer.exe", windows_path])
        except (subprocess.SubprocessError, OSError):
            pass
    candidates.extend([["xdg-open", str(path)], ["open", str(path)]])
    for command in candidates:
        if not shutil.which(command[0]):
            continue
        try:
            subprocess.run(command, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False


def _install_downloaded(path: Path, document, cards) -> str | None:
    """Validate and install a downloaded profile. Returns a status line, or None
    if the file is not a CUL profile at all."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != cul_core.SCHEMA_VERSION:
        return None
    if "scope" not in raw and "amendments" not in raw:
        return None
    try:
        layer = cul_core.resolve_profile(
            raw, corpus_document=document, cards=cards, strict=False, source=str(path)
        )
    except cul_core.CULError as exc:
        return f"REJECTED {path.name}: {exc}"
    if layer.get("stale"):
        return (
            f"REJECTED {path.name}: stale amendment(s): " + ", ".join(layer["stale"])
            + "\n  Re-edit them in the editor, or install with --allow-stale."
        )
    target = cul_core.profile_path(layer["profile"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    allowed, _ = cul_core.eligible_cards(cards, layer, verbose=False)
    _refresh_editor()
    return (
        f"INSTALLED {layer['profile']}: {len(allowed)}/{len(cards)} reachable, "
        f"{len(layer['amendments'])} amendment(s), digest {layer['cul_sha256'][:12]}"
    )


def cmd_edit(args):
    downloads = _downloads_dir(args.downloads_dir)
    if args.downloads_dir:
        settings = _settings()
        settings["downloads_dir"] = str(downloads)
        _save_settings(settings)
        print(f"REMEMBERED downloads directory: {downloads}")

    html = _build_editor()
    print(f"EDITOR: {html}")
    print(f"READ-ONLY CARD BROWSER (separate artefact): {READ_ONLY_BROWSER_HTML}")
    if not args.no_open and not _open_in_browser(html):
        print("Could not open a browser automatically; open the path above.")

    if args.no_watch:
        return 0
    if not downloads.is_dir():
        print(
            f"\nNot watching: {downloads} does not exist.\n"
            "Set the right one with: python scripts/cul.py --edit --downloads-dir <path>\n"
            "Or install a saved profile manually: "
            "python scripts/cul.py apply --from <file>"
        )
        return 0

    document, cards, _digest = _corpus()
    started = time.time()
    seen: dict[Path, float] = {}
    print(f"\nWatching {downloads} for saved profiles. Ctrl-C to stop.")
    try:
        while True:
            # Polling rather than inotify: on WSL the Windows filesystem is a
            # drvfs mount that does not deliver inotify events, so a watcher
            # would appear to work and never fire.
            for candidate in sorted(downloads.glob("*.json")):
                try:
                    stamp = candidate.stat().st_mtime
                except OSError:
                    continue
                if stamp < started or seen.get(candidate) == stamp:
                    continue
                seen[candidate] = stamp
                status = _install_downloaded(candidate, document, cards)
                if status:
                    print(status)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="show every profile")
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="print one resolved layer")
    show.add_argument("--cul", required=True)
    show.set_defaults(func=cmd_show)

    new = sub.add_parser("new", help="create a profile seeded from the default scope")
    new.add_argument("--cul", required=True)
    new.add_argument("--description")
    new.add_argument("--empty-scope", action="store_true", help="do not seed the default scope")
    new.add_argument("--force", action="store_true")
    new.set_defaults(func=cmd_new)

    check = sub.add_parser("check", help="validate one profile and report stale amendments")
    check.add_argument("--cul", required=True)
    check.set_defaults(func=cmd_check)

    diff = sub.add_parser("diff", help="show every change a profile makes")
    diff.add_argument("--cul", required=True)
    diff.set_defaults(func=cmd_diff)

    apply_cmd = sub.add_parser("apply", help="install a profile downloaded from the CUL editor")
    apply_cmd.add_argument("--from", dest="source", required=True)
    apply_cmd.add_argument("--cul", help="override the profile name in the downloaded file")
    apply_cmd.add_argument("--allow-stale", action="store_true")
    apply_cmd.add_argument("--no-rebuild", action="store_true",
                           help="do not refresh the editor after installing")
    apply_cmd.set_defaults(func=cmd_apply)

    edit = sub.add_parser(
        "edit",
        help="build and open the Corpus User Layer editor, installing saved profiles",
    )
    edit.add_argument("--downloads-dir",
                      help="where the browser saves files (default ~/Downloads; remembered)")
    edit.add_argument("--no-open", action="store_true", help="do not launch a browser")
    edit.add_argument("--no-watch", action="store_true", help="build and open only")
    edit.set_defaults(func=cmd_edit)
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    if argv and argv[0] == "--edit":
        argv[0] = "edit"
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except cul_core.CULError as exc:
        sys.exit(f"CUL ERROR:\n{exc}")
    except ValueError as exc:
        sys.exit(f"CUL ERROR:\n{exc}")


if __name__ == "__main__":
    raise SystemExit(main())
