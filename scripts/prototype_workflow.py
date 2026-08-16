#!/usr/bin/env python3
"""Compatibility CLI/import wrapper for the diagnosis-first prototype runtime."""
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflows.prototype.runtime import *  # noqa: F401,F403,E402
from workflows.prototype.runtime import main as _workflow_main  # noqa: E402


if __name__ == "__main__":
    _workflow_main()
