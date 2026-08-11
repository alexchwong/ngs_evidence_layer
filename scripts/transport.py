#!/usr/bin/env python3
"""Export or import private pre-corpus state as a verified compressed archive."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


FORMAT = "ngs-evidence-layer-private-state"
FORMAT_VERSION = 2
ROOT_NAMES = (
    "pdf", "input", "work", "quarantine", "accept", "archive", "curation"
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def root_paths(args):
    return {name: Path(getattr(args, f"{name}_dir")) for name in ROOT_NAMES}


def archive_path(root_name, relative):
    return PurePosixPath("state", root_name, *relative.parts).as_posix()


def collect_files(roots):
    files = []
    for root_name, root in roots.items():
        if not root.exists():
            continue
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"private state root is not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symbolic links are not supported: {path}")
            if path.is_file():
                relative = path.relative_to(root)
                stat = path.stat()
                files.append({
                    "path": archive_path(root_name, relative),
                    "size": stat.st_size,
                    "sha256": sha256(path),
                    "mtime_ns": stat.st_mtime_ns,
                    "source": path,
                })
            elif not path.is_dir():
                raise ValueError(f"unsupported filesystem entry: {path}")
    return files


def export_state(args):
    output = Path(args.output)
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    files = collect_files(root_paths(args))
    manifest = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roots": list(ROOT_NAMES),
        "files": [
            {key: entry[key] for key in ("path", "size", "sha256", "mtime_ns")}
            for entry in files
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(manifest_bytes)
            info.mtime = 0
            info.mode = 0o600
            with tempfile.SpooledTemporaryFile() as manifest_file:
                manifest_file.write(manifest_bytes)
                manifest_file.seek(0)
                archive.addfile(info, manifest_file)
            for entry in files:
                archive.add(entry["source"], arcname=entry["path"], recursive=False)
        os.replace(temporary, output)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    total = sum(entry["size"] for entry in files)
    print(f"Exported {len(files)} files ({total} bytes) to {output}")


def validated_member_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError(f"unsafe archive path: {name}")
    if name == "manifest.json":
        return path
    if len(path.parts) < 3 or path.parts[0] != "state" or path.parts[1] not in ROOT_NAMES:
        raise ValueError(f"unexpected archive path: {name}")
    return path


def inspect_archive(archive):
    members = {}
    for member in archive.getmembers():
        validated_member_path(member.name)
        if member.name in members:
            raise ValueError(f"duplicate archive member: {member.name}")
        if not member.isfile():
            raise ValueError(f"archive contains a non-file entry: {member.name}")
        members[member.name] = member
    manifest_member = members.get("manifest.json")
    if manifest_member is None:
        raise ValueError("archive has no manifest.json")
    manifest_file = archive.extractfile(manifest_member)
    if manifest_file is None:
        raise ValueError("could not read manifest.json")
    try:
        manifest = json.load(manifest_file)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest.json: {exc}") from exc
    if manifest.get("format") != FORMAT or manifest.get("version") != FORMAT_VERSION:
        raise ValueError("unsupported private-state archive format or version")
    created_at = manifest.get("created_at")
    try:
        created_at_value = datetime.fromisoformat(created_at)
    except (TypeError, ValueError) as exc:
        raise ValueError("manifest created_at must be an ISO 8601 date-time") from exc
    if created_at_value.tzinfo is None:
        raise ValueError("manifest created_at must include a timezone")
    roots = manifest.get("roots")
    if roots != list(ROOT_NAMES):
        raise ValueError("manifest roots do not identify the complete private state")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("manifest files must be an array")
    expected = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid file entry in manifest")
        name = entry.get("path")
        if not isinstance(name, str) or name == "manifest.json":
            raise ValueError("invalid file path in manifest")
        validated_member_path(name)
        if name in expected:
            raise ValueError(f"duplicate manifest path: {name}")
        size = entry.get("size")
        checksum = entry.get("sha256")
        mtime_ns = entry.get("mtime_ns")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid size for {name}")
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise ValueError(f"invalid SHA-256 for {name}")
        if not isinstance(mtime_ns, int) or mtime_ns < 0:
            raise ValueError(f"invalid mtime_ns for {name}")
        expected[name] = entry
    archive_files = set(members) - {"manifest.json"}
    if archive_files != set(expected):
        missing = sorted(set(expected) - archive_files)
        extra = sorted(archive_files - set(expected))
        raise ValueError(f"archive and manifest differ; missing={missing}, extra={extra}")
    created_at_ns = int(created_at_value.timestamp() * 1_000_000_000)
    return members, expected, created_at_ns


def stage_archive(archive, members, expected, staging):
    for name, entry in expected.items():
        member = members[name]
        if member.size != entry["size"]:
            raise ValueError(f"size mismatch for {name}")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"could not read {name}")
        destination = staging.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        written = 0
        with destination.open("wb") as handle:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                written += len(block)
                digest.update(block)
                handle.write(block)
        if written != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"checksum mismatch for {name}")


def destination_for(name, roots):
    parts = PurePosixPath(name).parts
    return roots[parts[1]].joinpath(*parts[2:])


def collect_destination_files(roots):
    files = {}
    for root_name, root in roots.items():
        if not root.exists():
            continue
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"private state root is not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symbolic links are not supported: {path}")
            if path.is_file():
                relative = path.relative_to(root)
                files[archive_path(root_name, relative)] = path
            elif not path.is_dir():
                raise ValueError(f"unsupported filesystem entry: {path}")
    return files


def classify_import(expected, roots):
    additions = []
    identical = []
    replacements = []
    for name, entry in expected.items():
        destination = destination_for(name, roots)
        if destination.exists():
            if (
                destination.is_file()
                and not destination.is_symlink()
                and destination.stat().st_size == entry["size"]
                and sha256(destination) == entry["sha256"]
            ):
                identical.append(destination)
            else:
                replacements.append((name, destination))
        else:
            additions.append((name, destination))
    local_files = collect_destination_files(roots)
    deletions = [
        (name, destination)
        for name, destination in local_files.items()
        if name not in expected
    ]
    return additions, identical, replacements, deletions


def render_paths(items):
    return "\n  ".join(str(item[1]) for item in items)


def remove_empty_directories(roots):
    for root in roots.values():
        if not root.is_dir():
            continue
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass


def install_staged(staging, expected, roots, created_at_ns, dry_run, overwrite):
    additions, identical, replacements, deletions = classify_import(expected, roots)
    if (replacements or deletions) and not overwrite:
        details = []
        if replacements:
            details.append("files requiring overwrite:\n  " + render_paths(replacements))
        if deletions:
            details.append("local files absent from manifest:\n  " + render_paths(deletions))
        raise ValueError("import conflicts with existing state:\n" + "\n".join(details))

    newer = []
    if overwrite:
        newer.extend(
            (name, destination)
            for name, destination in replacements
            if destination.stat().st_mtime_ns > expected[name]["mtime_ns"]
        )
        newer.extend(
            (name, destination)
            for name, destination in deletions
            if destination.stat().st_mtime_ns > created_at_ns
        )
    if newer:
        raise ValueError(
            "import --overwrite refused because local files are newer than the transport archive:\n  "
            + render_paths(newer)
            + "\nRemove these newer local files manually if you wish to proceed with transport import --overwrite."
        )

    if not dry_run:
        changed = additions + replacements
        with tempfile.TemporaryDirectory(prefix="nel-transport-rollback-") as temporary:
            rollback = Path(temporary)
            for name, destination in replacements + deletions:
                backup = rollback.joinpath(*PurePosixPath(name).parts)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
            written_additions = []
            try:
                for name, destination in changed:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source = staging.joinpath(*PurePosixPath(name).parts)
                    temporary_path = destination.with_name(
                        f".{destination.name}.transport-tmp"
                    )
                    try:
                        shutil.copy2(source, temporary_path)
                        os.replace(temporary_path, destination)
                        os.utime(destination, ns=(expected[name]["mtime_ns"], expected[name]["mtime_ns"]))
                    finally:
                        if temporary_path.exists():
                            temporary_path.unlink()
                    if (name, destination) in additions:
                        written_additions.append(destination)
                for _name, destination in deletions:
                    destination.unlink()
                remove_empty_directories(roots)
            except Exception:
                for destination in written_additions:
                    destination.unlink(missing_ok=True)
                for name, destination in replacements + deletions:
                    backup = rollback.joinpath(*PurePosixPath(name).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, destination)
                raise
    action = "Would import" if dry_run else "Imported"
    print(
        f"{action} {len(additions)} additions, {len(replacements)} overwrites, "
        f"{len(deletions)} deletions; {len(identical)} identical files skipped"
    )


def import_state(args):
    archive_path_value = Path(args.archive)
    roots = root_paths(args)
    with tempfile.TemporaryDirectory(prefix="nel-transport-") as temporary:
        staging = Path(temporary)
        try:
            with tarfile.open(archive_path_value, "r:gz") as archive:
                members, expected, created_at_ns = inspect_archive(archive)
                stage_archive(archive, members, expected, staging)
        except (OSError, tarfile.TarError) as exc:
            raise ValueError(f"could not read archive: {exc}") from exc
        install_staged(
            staging, expected, roots, created_at_ns, args.dry_run, args.overwrite
        )


def add_root_arguments(parser):
    for name in ROOT_NAMES:
        parser.add_argument(f"--{name}-dir", type=Path, default=Path(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    export_parser = commands.add_parser("export", help="create a compressed private-state archive")
    export_parser.add_argument("--output", type=Path, required=True)
    add_root_arguments(export_parser)
    export_parser.set_defaults(function=export_state)

    import_parser = commands.add_parser("import", help="verify and import a private-state archive")
    import_parser.add_argument("archive", type=Path)
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="reproduce the archive state by replacing and deleting older local files",
    )
    add_root_arguments(import_parser)
    import_parser.set_defaults(function=import_state)

    args = parser.parse_args()
    try:
        args.function(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()