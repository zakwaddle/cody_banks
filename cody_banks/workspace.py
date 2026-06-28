"""Workspace discovery and path handling."""

from __future__ import annotations

from pathlib import Path


def detect_workspace_root(path: Path | None = None) -> Path:
    candidate = path if path is not None else Path.cwd()
    return candidate.expanduser().resolve()

