"""Workspace file tools."""

from __future__ import annotations

from pathlib import Path
import subprocess


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


def create_file(path: str, content: str, workspace_root: Path) -> dict[str, object]:
    resolved = resolve_workspace_path(workspace_root, path)
    if resolved.exists():
        raise ToolError(f"file already exists: {path}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return {
        "path": display_path(workspace_root, resolved),
        "bytes_written": len(content.encode("utf-8")),
        "created": True,
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


def rename_file(old_path: str, new_path: str, workspace_root: Path) -> dict[str, object]:
    old_resolved = resolve_workspace_path(workspace_root, old_path)
    new_resolved = resolve_workspace_path(workspace_root, new_path)
    if not old_resolved.is_file():
        raise ToolError(f"not a file: {old_path}")
    if new_resolved.exists():
        raise ToolError(f"destination already exists: {new_path}")

    new_resolved.parent.mkdir(parents=True, exist_ok=True)
    old_resolved.rename(new_resolved)
    return {
        "old_path": display_path(workspace_root, old_resolved),
        "new_path": display_path(workspace_root, new_resolved),
        "renamed": True,
    }


def delete_file(path: str, workspace_root: Path) -> dict[str, object]:
    resolved = resolve_workspace_path(workspace_root, path)
    if not resolved.is_file():
        raise ToolError(f"not a file: {path}")

    byte_count = resolved.stat().st_size
    resolved.unlink()
    return {
        "path": display_path(workspace_root, resolved),
        "deleted": True,
        "bytes_deleted": byte_count,
    }


def apply_patch_text(patch_text: str, workspace_root: Path) -> dict[str, object]:
    touched_paths = touched_paths_from_patch(patch_text, workspace_root)
    if not touched_paths:
        raise ToolError("patch did not contain any workspace file paths")

    check = subprocess.run(
        ["git", "apply", "--check", "--whitespace=nowarn", "-"],
        cwd=workspace_root,
        input=patch_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        raise ToolError(check.stderr.strip() or "patch check failed")

    applied = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=workspace_root,
        input=patch_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if applied.returncode != 0:
        raise ToolError(applied.stderr.strip() or "patch apply failed")

    return {
        "paths": [display_path(workspace_root, path) for path in touched_paths],
        "applied": True,
    }


def touched_paths_from_patch(patch_text: str, workspace_root: Path) -> list[Path]:
    paths: list[Path] = []
    for raw_line in patch_text.splitlines():
        line = raw_line.strip()
        candidate: str | None = None
        if line.startswith("diff --git "):
            parts = line.split()
            for item in parts[2:4]:
                candidate = _strip_diff_prefix(item)
                if candidate is not None:
                    paths.append(resolve_workspace_path(workspace_root, candidate))
            continue
        if line.startswith(("--- ", "+++ ")):
            candidate = _strip_diff_prefix(line[4:].split("\t", 1)[0].strip())
        elif line.startswith(("rename from ", "rename to ")):
            candidate = line.split(" ", 2)[2].strip()

        if candidate is not None:
            paths.append(resolve_workspace_path(workspace_root, candidate))

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)
    return unique_paths


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


def _strip_diff_prefix(path: str) -> str | None:
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path
