#!/usr/bin/env python3
"""Select exactly one indexed publication for an isolated session, and say which
phase it is due.

One publication per session, no exceptions. The rule is not administrative: a
carder that has seen how another paper was carded starts pattern-matching to it
instead of reading the document in front of it, which is precisely the narrowness
this build exists to remove.

With no --input-root, the script selects the only valid corpus below --input-dir.
If more than one corpus exists it stops, so the operator chooses explicitly.

Usage:
  next_paper.py
  next_paper.py --id <input id> --format json
"""
import argparse
import json
import sys
from pathlib import Path

PORTABLE_PHASES = ("phase1", "phase2", "phase3")


def discover_input_root(input_dir):
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise ValueError(f"input directory not found: {input_dir}")
    candidates = sorted(
        path for path in input_dir.iterdir()
        if path.is_dir()
        and (path / "index" / "papers.jsonl").is_file()
        and (path / "markdown").is_dir()
    )
    if not candidates:
        raise ValueError(
            f"no input corpus found below {input_dir}; expected a folder containing "
            "index/papers.jsonl and markdown/"
        )
    if len(candidates) > 1:
        choices = ", ".join(str(path) for path in candidates)
        raise ValueError(
            f"multiple input corpora found: {choices}. Ask the operator which corpus "
            "to process, then pass it with --input-root."
        )
    return candidates[0]


def resolve_input_root(input_root, input_dir):
    if input_root:
        root = Path(input_root)
        if not (root / "index" / "papers.jsonl").is_file():
            raise ValueError(f"input corpus lacks index/papers.jsonl: {root}")
        if not (root / "markdown").is_dir():
            raise ValueError(f"input corpus lacks markdown/: {root}")
        return root
    return discover_input_root(input_dir)


def load_index(path):
    records = []
    seen_ids = set()
    seen_paths = set()
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        input_id = record.get("id")
        markdown_path = record.get("markdown_path")
        if not input_id or not markdown_path:
            raise ValueError(f"{path}:{line_no}: id and markdown_path are required")
        if input_id in seen_ids:
            raise ValueError(f"duplicate input id: {input_id}")
        if markdown_path in seen_paths:
            raise ValueError(f"duplicate markdown_path: {markdown_path}")
        if record.get("status") != "ingested":
            raise ValueError(f"{input_id}: status must be 'ingested'")
        expected_suffix = f"--{input_id[:8]}.md"
        if not Path(markdown_path).name.endswith(expected_suffix):
            raise ValueError(f"{input_id}: markdown filename must end with {expected_suffix}")
        seen_ids.add(input_id)
        seen_paths.add(markdown_path)
        records.append(record)
    if not records:
        raise ValueError(f"{path}: no indexed publications")
    return records


def paths_for(record, input_root, output_root):
    relative = Path(record["markdown_path"])
    stem = relative.stem
    return {
        "stem": stem,
        "markdown": input_root / relative,
        "skip": output_root / "reports" / f"{stem}.skipped.md",
    }


def portable_paths_for(record, input_root, output_root):
    paths = paths_for(record, input_root, output_root)
    stem = paths["stem"]
    paths.update({
        phase: output_root / phase / f"{stem}.{phase}.json"
        for phase in PORTABLE_PHASES
    })
    return paths


def phase_handoff_paths(paths, phase_number, exchange_root):
    """Return all paths for one portable phase without creating them."""
    stem = paths["stem"]
    phase = f"phase{phase_number}"
    root = Path(exchange_root) / "ingest" / phase
    return {
        "context": root / "outbox" / f"{stem}.{phase}-context.md",
        "source": root / "outbox" / paths["markdown"].name,
        "inbox": root / "inbox" / f"{stem}.{phase}.json",
        "archive": root / "archive" / f"{stem}.{phase}.json",
        "accepted": Path(paths[phase]),
    }


def portable_phase_for(paths):
    for phase in PORTABLE_PHASES:
        if not paths[phase].is_file():
            return phase
    return None


def select(records, input_root, output_root, requested_id=None, force=False):
    """Select the first publication with a missing accepted portable phase."""
    if requested_id and not any(r["id"] == requested_id for r in records):
        raise ValueError(f"input id not found: {requested_id}")
    candidates = []
    for record in records:
        paths = portable_paths_for(record, input_root, output_root)
        if not paths["markdown"].is_file():
            raise ValueError(f"indexed Markdown not found: {paths['markdown']}")
        if requested_id and record["id"] != requested_id:
            continue
        phase = portable_phase_for(paths)
        if phase or force:
            candidates.append((record, paths, phase or "phase3"))
    if requested_id and not candidates:
        raise ValueError(f"{requested_id} is complete; use --force to select it anyway")
    return candidates[0] if candidates else None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument("--id", dest="requested_id")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        input_root = resolve_input_root(args.input_root, args.input_dir)
        records = load_index(input_root / "index" / "papers.jsonl")
        selected = select(records, input_root, args.output_root, args.requested_id, args.force)
    except (OSError, ValueError) as exc:
        sys.exit(f"error: {exc}")

    complete = sum(
        portable_phase_for(portable_paths_for(record, input_root, args.output_root)) is None
        for record in records
    )

    if selected is None:
        print(f"No pending publications. {complete}/{len(records)} indexed are complete.")
        return

    record, paths, phase = selected
    result = {
        "collection": str(input_root),
        "total": len(records),
        "complete": complete,
        "remaining": len(records) - complete,
        "phase": phase,
        "paper": {
            "id": record["id"],
            "stem": paths["stem"],
            "markdown_path": str(paths["markdown"]),
            **{f"{name}_path": str(paths[name]) for name in PORTABLE_PHASES},
            "index_record": record,
        },
    }

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print("NEXT PUBLICATION - process this one only, in a fresh session")
    print(f"Input corpus: {input_root}")
    print(f"Input ID:     {record['id']}")
    print(f"Markdown:     {paths['markdown']}")
    print(f"Due phase:    {phase}")
    print(f"Write to:     {paths[phase]}")
    print(f"Progress:     {complete}/{len(records)} complete, "
          f"{len(records) - complete} outstanding")
    print()
    number = phase[-1]
    print(
        f"Portable Phase {number}. Run `python scripts/ingest.py pre-phase{number}` "
        "to generate or accept the two-file model handoff."
    )


if __name__ == "__main__":
    main()
