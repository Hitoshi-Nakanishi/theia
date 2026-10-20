"""Resolve the local model folder from the environment or project .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> dict[str, str]:
    """Tiny KEY=value parser. Strips quotes; ignores blank / # lines."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        out[k] = v
    return out


@lru_cache(maxsize=1)
def _env() -> dict[str, str]:
    return _load_env_file(_PROJECT_ROOT / ".env")


def _from_env(key: str) -> str | None:
    if v := os.environ.get(key):
        return v
    return _env().get(key)


@lru_cache(maxsize=1)
def models_root() -> Path:
    """The folder opened when no file or folder is passed on the command line."""
    if value := _from_env("THEIA_MODELS_PATH"):
        return Path(value).expanduser()
    if value := _from_env("DATA_PATH"):
        return Path(value).expanduser() / "models"
    return Path.home() / "Documents" / "Theia" / "models"
