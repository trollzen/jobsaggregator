from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("channels", [])
    for key in ("fetch", "prefilter", "ai", "dedupe", "store", "health"):
        cfg.setdefault(key, {})
    return cfg
