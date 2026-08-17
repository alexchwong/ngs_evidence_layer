#!/usr/bin/env python3
"""Compatibility CLI for workflow-neutral report citation mechanics."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core.citations import *  # noqa: F401,F403,E402
from scripts.core.citations import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
