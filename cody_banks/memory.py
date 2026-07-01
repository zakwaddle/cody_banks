"""Project memory helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MEMORY_TEMPLATE = """# Project Memory

Durable project context for Cody Banks.

Use this file for stable project facts, architectural decisions, coding conventions,
user preferences, known risks, recurring warnings, and durable lessons learned.

Do not use this file for full transcripts, raw tool output, temporary plans, or
speculative notes that are no longer relevant.

## Notes
"""


@dataclass(frozen=True, slots=True)
class SearchMatch:
    line_number: int
    line: str


def memory_path(workspace_root: Path) -> Path:
    return workspace_root / ".cody" / "memory.md"


def ensure_memory_file(workspace_root: Path) -> Path:
    path = memory_path(workspace_root)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MEMORY_TEMPLATE, encoding="utf-8")
    return path


def read_memory(workspace_root: Path) -> str:
    path = ensure_memory_file(workspace_root)
    return path.read_text(encoding="utf-8")


def read_memory_for_prompt(workspace_root: Path, max_chars: int = 6000) -> str:
    content = read_memory(workspace_root).strip()
    if not content:
        return "(project memory is empty)"
    if len(content) <= max_chars:
        return content

    omitted = len(content) - max_chars
    return content[:max_chars] + f"\n\n... omitted {omitted} chars from project memory ..."


def add_memory_note(workspace_root: Path, note: str) -> Path:
    cleaned = " ".join(note.strip().split())
    if not cleaned:
        raise ValueError("memory note must not be empty")

    path = ensure_memory_file(workspace_root)
    content = path.read_text(encoding="utf-8")
    if "## Notes" not in content:
        content = content.rstrip() + "\n\n## Notes\n"

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"\n- {timestamp}: {cleaned}\n"
    path.write_text(content.rstrip() + line, encoding="utf-8")
    return path


def search_memory(workspace_root: Path, query: str) -> list[SearchMatch]:
    needle = query.strip().lower()
    if not needle:
        raise ValueError("search query must not be empty")

    matches: list[SearchMatch] = []
    for line_number, line in enumerate(read_memory(workspace_root).splitlines(), start=1):
        if needle in line.lower():
            matches.append(SearchMatch(line_number=line_number, line=line))
    return matches


def prune_memory(workspace_root: Path) -> dict[str, int]:
    path = ensure_memory_file(workspace_root)
    original_lines = path.read_text(encoding="utf-8").splitlines()
    pruned_lines: list[str] = []
    seen_content_lines: set[str] = set()
    removed_duplicates = 0
    removed_session_lines = 0
    blank_run = 0
    skip_session_section = False

    for line in original_lines:
        if line.startswith("## Session compact "):
            skip_session_section = True
            removed_session_lines += 1
            continue
        if skip_session_section:
            if line.startswith("## "):
                skip_session_section = False
            else:
                removed_session_lines += 1
                continue

        if not line.strip():
            blank_run += 1
            if blank_run > 1:
                continue
            pruned_lines.append("")
            continue
        blank_run = 0

        if line.startswith("- "):
            normalized = _normalize_memory_line(line)
            if normalized in seen_content_lines:
                removed_duplicates += 1
                continue
            seen_content_lines.add(normalized)

        pruned_lines.append(line)

    pruned_content = "\n".join(pruned_lines).strip() + "\n"
    path.write_text(pruned_content, encoding="utf-8")
    return {
        "removed_duplicate_lines": removed_duplicates,
        "removed_session_lines": removed_session_lines,
    }


def _normalize_memory_line(line: str) -> str:
    bullet = line[2:].strip()
    if ": " in bullet:
        prefix, _, suffix = bullet.partition(": ")
        if _looks_like_iso_timestamp(prefix):
            return suffix.lower()
    return bullet.lower()


def _looks_like_iso_timestamp(text: str) -> bool:
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True
