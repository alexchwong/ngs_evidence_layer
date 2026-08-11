#!/usr/bin/env python3
"""Build and verify the uploadable skill ZIP described by release/skill.txt."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPOSITORY_ROOT / "release" / "skill.txt"
DEFAULT_VERSION_FILE = REPOSITORY_ROOT / "release" / "VERSION"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a skill-only ZIP from tracked files at HEAD, using the paths and "
            "glob patterns in release/skill.txt."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="manifest to resolve (default: release/skill.txt)",
    )
    parser.add_argument(
        "--version-file",
        type=Path,
        default=DEFAULT_VERSION_FILE,
        help="file containing an X.Y.Z release version (default: release/VERSION)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "output ZIP path (default: ngs-evidence-layer-<VERSION>.zip in the "
            "repository root)"
        ),
    )
    return parser.parse_args()


def read_version(version_file: Path) -> str:
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(f"Unable to read version file {version_file}: {exc}") from exc

    if VERSION_PATTERN.fullmatch(version) is None:
        raise SystemExit(
            f"{version_file} must contain exactly one version in X.Y.Z form"
        )
    return version


def read_patterns(manifest: Path) -> list[str]:
    try:
        patterns = [
            line
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line
        ]
    except OSError as exc:
        raise SystemExit(f"Unable to read release manifest {manifest}: {exc}") from exc

    if not patterns:
        raise SystemExit(f"Release manifest is empty: {manifest}")
    return patterns


def git_output(*arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SystemExit("git is required to build the skill ZIP") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"git {' '.join(arguments)} failed: {detail}") from exc
    return result.stdout


def resolve_manifest(patterns: list[str]) -> list[str]:
    resolved: set[str] = set()
    for pattern in patterns:
        output = git_output("ls-files", "-z", "--", pattern)
        matches = [
            entry.decode("utf-8", errors="surrogateescape")
            for entry in output.split(b"\0")
            if entry
        ]
        if not matches:
            raise SystemExit(
                f"Release manifest pattern matched no tracked files: {pattern}"
            )

        for match in matches:
            if not (REPOSITORY_ROOT / match).is_file():
                raise SystemExit(f"Release manifest matched a non-file path: {match}")
            resolved.add(match)

    if not resolved:
        raise SystemExit("Release manifest resolved to no files")
    return sorted(resolved)


def build_archive(files: list[str], archive: Path, archive_root: str) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="skill-zip-", dir=archive.parent
    ) as temporary_directory:
        temporary_archive = Path(temporary_directory) / archive.name
        try:
            subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=zip",
                    f"--prefix={archive_root}/",
                    f"--output={temporary_archive}",
                    "HEAD",
                    "--",
                    *files,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
            raise SystemExit(f"git archive failed: {detail}") from exc

        verify_archive(temporary_archive, files, archive_root)
        temporary_archive.replace(archive)


def verify_archive(archive: Path, files: list[str], archive_root: str) -> None:
    prefix = f"{archive_root}/"
    expected = {prefix + file for file in files}
    try:
        with zipfile.ZipFile(archive) as handle:
            corrupt_member = handle.testzip()
            actual = {name for name in handle.namelist() if not name.endswith("/")}
    except (OSError, zipfile.BadZipFile) as exc:
        raise SystemExit(f"Unable to verify ZIP {archive}: {exc}") from exc

    if corrupt_member is not None:
        raise SystemExit(f"ZIP contains a corrupt file: {corrupt_member}")

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise SystemExit(
            "Release ZIP does not match the resolved manifest.\n"
            f"Missing: {missing}\n"
            f"Extra: {extra}"
        )


def main() -> None:
    args = parse_args()
    version = read_version(args.version_file.resolve())
    files = resolve_manifest(read_patterns(args.manifest.resolve()))
    archive_root = f"ngs-evidence-layer-{version}"
    archive = (
        args.output.resolve()
        if args.output is not None
        else REPOSITORY_ROOT / f"{archive_root}.zip"
    )

    build_archive(files, archive, archive_root)
    print(f"Built {archive} with {len(files)} files under {archive_root}/")


if __name__ == "__main__":
    main()