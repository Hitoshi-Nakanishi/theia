"""Central data path resolution.

The viewer opens a prepared archive rooted at ``$DATA_PATH`` by default. The
value comes from (in order):

  1. ``DATA_PATH`` environment variable
  2. ``DATA_PATH=...`` line in a ``.env`` file at the project root
  3. Per-OS default — ``example-data`` on Windows, ``~/Documents/Theia/models`` on
     mac/linux.

Standard layout under ``$DATA_PATH``::

    broker_models/
      canonical/<broker>/<analyst>/<ticker>.T_<name>.xlsx (+ optional sidecars)
"""

from __future__ import annotations

import os
import platform
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
def data_path() -> Path:
    """Root data directory."""
    if v := _from_env("DATA_PATH"):
        return Path(v).expanduser()
    if platform.system() == "Windows":
        return Path("example-data")
    return Path.home() / "Documents" / "Theia" / "models"


def broker_models_root() -> Path:
    return data_path() / "broker_models"


def canonical_root() -> Path:
    return broker_models_root() / "canonical"
