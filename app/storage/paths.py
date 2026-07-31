from __future__ import annotations

from pathlib import Path

from app.config.settings import PROJECT_ROOT


def resolve_storage_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def ensure_storage_dir(path: str) -> Path:
    resolved = resolve_storage_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
