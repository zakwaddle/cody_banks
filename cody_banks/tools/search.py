"""Workspace search tools."""

from __future__ import annotations

from pathlib import Path
import subprocess

from cody_banks.tools.files import ToolError, display_path, resolve_workspace_path


def search_text(query: str, path: str, workspace_root: Path, limit: int = 100) -> dict[str, object]:
    """Search workspace text using ripgrep when available, with a Python fallback."""
    if not query:
        raise ToolError("query must not be empty")

    resolved = resolve_workspace_path(workspace_root, path)
    if not resolved.exists():
        raise ToolError(f"path does not exist: {path}")

    try:
        return _search_with_rg(query, resolved, workspace_root, limit)
    except FileNotFoundError:
        return _search_with_python(query, resolved, workspace_root, limit)


def _search_with_rg(query: str, resolved: Path, workspace_root: Path, limit: int) -> dict[str, object]:
    completed = subprocess.run(
        ["rg", "--line-number", "--column", "--color", "never", "--", query, str(resolved)],
        cwd=workspace_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        raise ToolError(completed.stderr.strip() or "ripgrep search failed")

    lines = completed.stdout.splitlines()
    return {
        "query": query,
        "path": display_path(workspace_root, resolved) or ".",
        "matches": lines[:limit],
        "truncated": len(lines) > limit,
        "engine": "rg",
    }


def _search_with_python(query: str, resolved: Path, workspace_root: Path, limit: int) -> dict[str, object]:
    files = [resolved] if resolved.is_file() else [path for path in resolved.rglob("*") if path.is_file()]
    matches: list[str] = []
    ignored_dirs = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}

    for file_path in files:
        if any(part in ignored_dirs for part in file_path.relative_to(workspace_root).parts):
            continue
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            column = line.find(query)
            if column == -1:
                continue
            matches.append(f"{display_path(workspace_root, file_path)}:{line_number}:{column + 1}:{line}")
            if len(matches) >= limit:
                return {
                    "query": query,
                    "path": display_path(workspace_root, resolved) or ".",
                    "matches": matches,
                    "truncated": True,
                    "engine": "python",
                }

    return {
        "query": query,
        "path": display_path(workspace_root, resolved) or ".",
        "matches": matches,
        "truncated": False,
        "engine": "python",
    }
