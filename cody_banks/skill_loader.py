"""Simple markdown skill inference and loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True, slots=True)
class SkillContext:
    name: str
    path: str
    reason: str
    content: str


SKILL_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "python.md": {
        "keywords": ("python", "pytest", "unittest", "compileall", "pip", "pyproject", "cli", "dataclass"),
        "patterns": (".py", "pyproject.toml", "requirements.txt", "pytest.ini"),
    },
    "git.md": {
        "keywords": ("git", "commit", "branch", "diff", "merge", "rebase", "uncommitted", "dirty"),
        "patterns": (".git", ".gitignore"),
    },
    "react.md": {
        "keywords": ("react", "jsx", "tsx", "component", "frontend", "browser", "vite", "next.js", "accessibility"),
        "patterns": (".jsx", ".tsx", "package.json", "vite.config", "next.config"),
    },
    "local_llm.md": {
        "keywords": ("llm", "local model", "openai-compatible", "chat completion", "llama.cpp", "model endpoint", "base_url"),
        "patterns": ("llm.py", "start_llm_server", "chat/completions"),
    },
}


def infer_and_load_skills(workspace_root: Path, task_text: str, limit: int = 4) -> list[SkillContext]:
    selected: list[tuple[str, str]] = []
    lowered = task_text.lower()
    for skill_name, rule in SKILL_RULES.items():
        reason = _match_reason(lowered, rule)
        if reason is not None:
            selected.append((skill_name, reason))
        if len(selected) >= limit:
            break
    return load_skills(workspace_root, selected)


def load_skills_from_roadmap(workspace_root: Path, roadmap_content: str) -> list[SkillContext]:
    requested: list[tuple[str, str]] = []
    for line in roadmap_content.splitlines():
        match = re.match(r"\s*[-*]\s+`?(?P<name>[a-z0-9_./-]+\.md)`?\s*[:-]\s*(?P<reason>.+)\s*$", line, flags=re.IGNORECASE)
        if match is None:
            continue
        name = Path(match.group("name")).name
        if name in SKILL_RULES:
            requested.append((name, match.group("reason").strip()))
    return load_skills(workspace_root, requested)


def load_skills(workspace_root: Path, requested: list[tuple[str, str]]) -> list[SkillContext]:
    contexts: list[SkillContext] = []
    seen: set[str] = set()
    for skill_name, reason in requested:
        if skill_name in seen:
            continue
        seen.add(skill_name)
        path = workspace_root / "cody_banks" / "skills" / skill_name
        if not path.is_file():
            continue
        contexts.append(
            SkillContext(
                name=skill_name,
                path=str(path.relative_to(workspace_root)),
                reason=reason,
                content=path.read_text(encoding="utf-8"),
            )
        )
    return contexts


def format_loaded_skills(skills: list[SkillContext]) -> str:
    if not skills:
        return "- none"
    return "\n\n".join(
        f"## {skill.name}\nPath: {skill.path}\nReason: {skill.reason}\n\n{skill.content.strip()}"
        for skill in skills
    )


def format_loaded_skills_record(skills: list[SkillContext]) -> str:
    if not skills:
        return "- none"
    return "\n".join(f"- `{skill.name}`: {skill.reason}" for skill in skills)


def _match_reason(text: str, rule: dict[str, tuple[str, ...]]) -> str | None:
    for pattern in rule["patterns"]:
        if pattern.lower() in text:
            return f"matched file pattern `{pattern}`"
    for keyword in rule["keywords"]:
        if keyword.lower() in text:
            return f"matched keyword `{keyword}`"
    return None
