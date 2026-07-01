"""Infinite Company Arena benchmark package."""

from __future__ import annotations

import sys
from pathlib import Path


_repo_dir = Path(__file__).resolve().parents[1]
_backend_dir = _repo_dir / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
