#!/usr/bin/env python3
import argparse
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--project", action="store_true")
args = parser.parse_args()

if args.project:
    root = Path(__file__).resolve().parent.parent / "temp"
    root.mkdir(exist_ok=True)
    print(tempfile.mkdtemp(prefix="ngs-evidence-layer-", dir=root))
else:
    print(tempfile.mkdtemp(prefix="ngs-evidence-layer-"))
