"""Workspace file tools."""

from __future__ import annotations

from pathlib import Path


class ToolError(RuntimeError):
    """Raised when a workspace tool request is invalid or cannot be completed."""


def resolve_workspace_path(workspace_root: Path, path: str) -> Path:
    """Resolve a user path and reject anything outside the workspace root."""
    root = workspace_root.expanduser().resolve()
    candidate = (root / path).expanduser().resolve() if not Path(path).is_absolute() else Path(path).expanduser().resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ToolError(f"path escapes workspace root: {path}") from exc

    return candidate


def display_path(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def read_file(path: str, workspace_root: Path) -> dict[str, object]:
    resolved = resolve_workspace_path(workspace_root, path)
    if not resolved.is_file():
        raise ToolError(f"not a file: {path}")

    return {
        "path": display_path(workspace_root, resolved),
        "content": resolved.read_text(encoding="utf-8"),
    }


def write_file(path: str, content: str, workspace_root: Path) -> dict[str, object]:
    resolved = resolve_workspace_path(workspace_root, path)
    existed = resolved.exists()
    if resolved.exists() and not resolved.is_file():
        raise ToolError(f"not a file: {path}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return {
        "path": display_path(workspace_root, resolved),
        "bytes_written": len(content.encode("utf-8")),
        "created": not existed,
    }


def edit_file(path: str, old: str, new: str, workspace_root: Path) -> dict[str, object]:
    resolved = resolve_workspace_path(workspace_root, path)
    if not resolved.is_file():
        raise ToolError(f"not a file: {path}")

    content = resolved.read_text(encoding="utf-8")
    count = content.count(old)
    if count == 0:
        raise ToolError("old text was not found")
    if count > 1:
        raise ToolError(f"old text matched {count} times; provide a more specific old value")

    updated = content.replace(old, new, 1)
    resolved.write_text(updated, encoding="utf-8")
    return {
        "path": display_path(workspace_root, resolved),
        "replacements": 1,
        "bytes_written": len(updated.encode("utf-8")),
    }


def list_files(path: str, workspace_root: Path, limit: int = 200) -> dict[str, object]:
    resolved = resolve_workspace_path(workspace_root, path)
    if not resolved.exists():
        raise ToolError(f"path does not exist: {path}")
    if not resolved.is_dir():
        raise ToolError(f"not a directory: {path}")

    entries: list[str] = []
    for child in sorted(resolved.rglob("*")):
        if any(part in {".git", "__pycache__", ".pytest_cache", ".mypy_cache"} for part in child.relative_to(workspace_root).parts):
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(display_path(workspace_root, child) + suffix)
        if len(entries) >= limit:
            break

    return {
        "path": display_path(workspace_root, resolved) or ".",
        "entries": entries,
        "truncated": len(entries) >= limit,
    }
