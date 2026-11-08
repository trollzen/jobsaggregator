from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_env(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from .env into os.environ (existing variables win)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8-sig") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("channels", [])
    for key in ("fetch", "prefilter", "ai", "dedupe", "store", "health", "telethon"):
        cfg.setdefault(key, {})
    return cfg
