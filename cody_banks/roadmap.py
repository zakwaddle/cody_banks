"""Roadmap file helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


ROADMAP_SECTIONS = [
    "# Goal",
    "# Background",
    "# Clarifying Questions",
    "# Assumptions",
    "# Files Likely Involved",
    "# Steps",
    "# Validation Plan",
    "# Stop Conditions",
    "# Memory Updates To Consider",
]


ROADMAP_TEMPLATE = """# Goal

# Background

# Clarifying Questions

# Assumptions

# Files Likely Involved

# Steps

# Validation Plan

# Stop Conditions

# Memory Updates To Consider
"""


STEP_PATTERN = re.compile(r"^(?P<prefix>\s*[-*]\s+\[)(?P<mark>[ xX])(?P<suffix>\]\s+)(?P<text>.+?)\s*$")


def roadmaps_dir(workspace_root: Path) -> Path:
    return workspace_root / ".cody" / "roadmaps"


def ensure_roadmaps_dir(workspace_root: Path) -> Path:
    path = roadmaps_dir(workspace_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_roadmap_path(workspace_root: Path) -> Path | None:
    path = roadmaps_dir(workspace_root)
    if not path.is_dir():
        return None
    roadmaps = sorted(item for item in path.glob("*.md") if item.is_file())
    return roadmaps[-1] if roadmaps else None


def resolve_roadmap_path(workspace_root: Path, path: str) -> Path:
    root = workspace_root.expanduser().resolve()
    candidate = root / path if not Path(path).is_absolute() else Path(path)
    resolved = candidate.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"roadmap path escapes workspace root: {path}") from exc
    if not resolved.is_file():
        raise ValueError(f"roadmap not found: {path}")
    if resolved.suffix != ".md":
        raise ValueError(f"roadmap must be a markdown file: {path}")
    return resolved


def save_roadmap(workspace_root: Path, task: str, content: str) -> Path:
    directory = ensure_roadmaps_dir(workspace_root)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    slug = slugify(task) or "task"
    path = directory / f"{timestamp}-{slug}.md"
    counter = 2
    while path.exists():
        path = directory / f"{timestamp}-{slug}-{counter}.md"
        counter += 1

    normalized = normalize_roadmap_content(content)
    path.write_text(normalized, encoding="utf-8")
    return path


def normalize_roadmap_content(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        cleaned = ROADMAP_TEMPLATE.strip()

    missing = [section for section in ROADMAP_SECTIONS if section not in cleaned]
    if missing:
        cleaned = cleaned.rstrip() + "\n\n" + "\n\n".join(f"{section}\n\n" for section in missing).rstrip()

    return cleaned.rstrip() + "\n"


def ensure_loaded_skills_record(content: str, loaded_skills: str) -> str:
    record = loaded_skills.strip() or "- none"
    if "# Loaded Skills" in content:
        return content.rstrip() + "\n"

    insertion = f"# Loaded Skills\n\n{record}\n\n"
    marker = "# Background"
    if marker not in content:
        return insertion + content.rstrip() + "\n"

    return content.replace(marker, insertion + marker, 1).rstrip() + "\n"


def active_step(content: str) -> tuple[int, str] | None:
    for index, line in enumerate(content.splitlines()):
        match = STEP_PATTERN.match(line)
        if match is None:
            continue
        if match.group("mark") == " ":
            return index, match.group("text")
    return None


def mark_step_complete(content: str, line_index: int) -> str:
    lines = content.splitlines()
    if line_index < 0 or line_index >= len(lines):
        raise ValueError("step line index is out of range")
    match = STEP_PATTERN.match(lines[line_index])
    if match is None or match.group("mark") != " ":
        raise ValueError("line is not an active unchecked step")
    lines[line_index] = f"{match.group('prefix')}x{match.group('suffix')}{match.group('text')}"
    return "\n".join(lines).rstrip() + "\n"


def append_execution_note(content: str, note: str, heading: str = "Execution Notes") -> str:
    cleaned = note.strip()
    if not cleaned:
        return content.rstrip() + "\n"

    timestamp = datetime.now().isoformat(timespec="seconds")
    section_heading = f"# {heading}"
    base = content.rstrip()
    if section_heading not in base:
        base += f"\n\n{section_heading}\n"
    return f"{base}\n- {timestamp}: {cleaned}\n"


def slugify(text: str, max_length: int = 48) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    slug = "-".join(words)[:max_length].strip("-")
    return slug or "task"
