"""Workspace resolution and content-addressed JSON storage (research R4).

No environment variable is read here — a workspace is resolved from an explicit
argument or the current working directory only (Constitution Article IV's discipline
extended in spirit: this feature adds no second configuration surface either).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> str:
    """A deterministic JSON encoding: sorted keys, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def workspace_root(explicit: Path | None) -> Path:
    """The workspace root: `explicit` unchanged, or `<cwd>/.tna-lab` by default."""
    if explicit is not None:
        return explicit
    return Path.cwd() / ".tna-lab"


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write `data` as JSON at `path`, creating parent directories as needed.

    A write to a path that already holds byte-identical content (by canonical form)
    is a silent no-op. A write that would change existing content raises ValueError —
    this is the append-only primitive both datasets.py and snapshots.py build on.
    """
    encoded = canonical_json(data)
    if path.exists():
        existing = path.read_text()
        if existing == encoded:
            return
        raise ValueError(f"{path} already exists with different content; refusing to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded)


def overwrite_json(path: Path, data: dict[str, Any]) -> None:
    """Write `data` as JSON at `path`, always replacing any existing content.

    For genuinely mutable state only (a dataset's HEAD) — content-addressed artifacts
    (records, snapshots, runs) use `write_json`'s append-only semantics instead.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(data))


def read_json(path: Path) -> dict[str, Any]:
    """Read and decode the JSON object at `path`."""
    data: dict[str, Any] = json.loads(path.read_text())
    return data
