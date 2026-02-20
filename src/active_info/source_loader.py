from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_source_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Source config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        content = yaml.safe_load(f) or {}
    return content
