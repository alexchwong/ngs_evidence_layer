#!/usr/bin/env python3
"""Build a self-contained, phone-sized HTML browser for the accepted card corpus.

Same corpus payload as build_card_browser.py, with the card locator added, but
rendered through a touch-first template: a single column of cards, filters in a
bottom sheet, and no external font or script requests so the page works with no
network. Intended for reading the corpus on a phone.

Usage:
  build_card_browser_mobile.py [--corpus output/corpus/nel.corpus.json]
                               [--output output/reports/card-browser-mobile.html]
                               [--serve] [--port 8000]

With --serve the file is built and then offered over the local network, so a
phone on the same Wi-Fi can open it in Safari. Stop the server with Ctrl-C.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_card_browser import collect  # noqa: E402  shared corpus reader

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "output" / "corpus" / "nel.corpus.json"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "reports" / "card-browser-mobile.html"
TEMPLATE = Path(__file__).resolve().parent / "assets" / "card_browser_mobile_template.html"


def add_locators(data: dict, corpus_path: Path) -> dict:
    """Attach each card's locator, which the desktop payload omits."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    locators = {}
    for entry in corpus.get("publications", []):
        for card in entry["document"].get("cards", []):
            locators[card["card_id"]] = card.get("locator", "")
    for card in data["cards"]:
        card["locator"] = locators.get(card["id"], "")
    return data


def lan_address() -> str:
    """Best-effort local network address for this machine."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 1))  # TEST-NET-1, no packets are sent
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def serve(output: Path, port: int) -> None:
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(output.parent))
    url = f"http://{lan_address()}:{port}/{output.name}"
    print(f"\nOpen this on the phone, same Wi-Fi:\n\n    {url}\n\nCtrl-C to stop.")
    with ThreadingHTTPServer(("0.0.0.0", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--serve", action="store_true", help="serve the file on the local network")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    data = add_locators(collect(args.corpus), args.corpus)
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    html = template.replace("/*__CARD_DATA__*/null", payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    size = args.output.stat().st_size / 1024
    print(f"{args.output} ({len(data['cards'])} cards, {len(data['papers'])} papers, {size:.0f} KB)")

    if args.serve:
        serve(args.output, args.port)


if __name__ == "__main__":
    main()
