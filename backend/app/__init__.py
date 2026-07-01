from __future__ import annotations

import sys
from pathlib import Path


_repo_dir = Path(__file__).resolve().parents[2]
if str(_repo_dir) not in sys.path:
    sys.path.insert(0, str(_repo_dir))

