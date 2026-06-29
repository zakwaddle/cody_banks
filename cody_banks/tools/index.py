"""Local project indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from cody_banks.tools.files import ToolError, display_path, resolve_workspace_path
from cody_banks.tools.search import search_text


INDEX_RELATIVE_PATH = ".cody/index/project_index.json"

SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

IGNORED_DIRS = {
    ".cody/index",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    path: str
    kind: str
    summary: str
    line_count: int
    byte_count: int


def build_project_index(workspace_root: Path) -> dict[str, object]:
    """Build and store a keyword-oriented project index under .cody/index."""
    documents = [
        _document_to_record(document)
        for document in _iter_indexed_documents(workspace_root)
    ]
    payload = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "retrieval": {
            "keyword": True,
            "vector": False,
            "rule": "Use keyword search first; vector search is not implemented yet.",
        },
        "document_count": len(documents),
        "documents": documents,
    }
    index_path = _index_path(workspace_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": display_path(workspace_root, index_path),
        "document_count": len(documents),
        "vector_search": False,
    }


def retrieve_context(query: str, workspace_root: Path, limit: int = 8) -> dict[str, object]:
    """Retrieve context with keyword search first, then indexed summaries."""
    if not query.strip():
        raise ToolError("query must not be empty")

    keyword_result = search_text(query, ".", workspace_root, limit=limit)
    keyword_matches = keyword_result.get("matches", [])
    if isinstance(keyword_matches, list) and keyword_matches:
        return {
            "query": query,
            "strategy": "keyword",
            "matches": keyword_matches,
            "truncated": keyword_result.get("truncated", False),
            "vector_search": "not implemented",
        }

    index = load_project_index(workspace_root)
    if index is None:
        build_project_index(workspace_root)
        index = load_project_index(workspace_root)

    documents = [] if index is None else index.get("documents", [])
    if not isinstance(documents, list):
        documents = []

    ranked = _rank_documents(query, documents)[:limit]
    return {
        "query": query,
        "strategy": "summary",
        "matches": ranked,
        "truncated": False,
        "vector_search": "not implemented",
    }


def load_project_index(workspace_root: Path) -> dict[str, Any] | None:
    path = _index_path(workspace_root)
    if not path.is_file():
        return None
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError("project index is invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ToolError("project index root must be a JSON object")
    return decoded


def _iter_indexed_documents(workspace_root: Path) -> list[IndexedDocument]:
    documents = [_summarize_file(path, workspace_root) for path in _iter_indexable_files(workspace_root)]
    documents.extend(_summarize_sessions(workspace_root))
    return documents


def _iter_indexable_files(workspace_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(workspace_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace_root)
        if _is_ignored(relative):
            continue
        if _is_indexable_file(path, relative):
            files.append(path)
    return files


def _is_indexable_file(path: Path, relative: Path) -> bool:
    name = path.name.lower()
    if name.startswith("readme") or name == "roadmap.md":
        return True
    if "skills" in relative.parts and path.suffix == ".md":
        return True
    return path.suffix.lower() in SOURCE_SUFFIXES


def _is_ignored(relative: Path) -> bool:
    parts = relative.parts
    joined = "/".join(parts)
    return any(part in IGNORED_DIRS for part in parts) or joined.startswith(".cody/index/")


def _summarize_file(path: Path, workspace_root: Path) -> IndexedDocument:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = ""

    relative = display_path(workspace_root, path)
    lines = content.splitlines()
    summary_lines = _interesting_lines(lines)
    summary = "\n".join(summary_lines) if summary_lines else _first_nonempty_lines(lines)
    return IndexedDocument(
        path=relative,
        kind=_document_kind(path, Path(relative)),
        summary=summary,
        line_count=len(lines),
        byte_count=len(content.encode("utf-8")),
    )


def _summarize_sessions(workspace_root: Path) -> list[IndexedDocument]:
    sessions_dir = resolve_workspace_path(workspace_root, "data/sessions")
    if not sessions_dir.exists():
        return []

    documents: list[IndexedDocument] = []
    for path in sorted(sessions_dir.glob("*.jsonl")):
        events = _read_session_events(path)
        if not events:
            continue
        summary = _session_summary(events)
        documents.append(
            IndexedDocument(
                path=display_path(workspace_root, path),
                kind="session_summary",
                summary=summary,
                line_count=len(events),
                byte_count=path.stat().st_size,
            )
        )
    return documents


def _read_session_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            events.append(decoded)
    return events


def _session_summary(events: list[dict[str, Any]]) -> str:
    event_counts: dict[str, int] = {}
    snippets: list[str] = []
    for event in events:
        event_type = str(event.get("event", "unknown"))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        content = event.get("content")
        if isinstance(content, str) and content.strip() and len(snippets) < 4:
            snippets.append(_single_line(content))

    counts = ", ".join(f"{key}={value}" for key, value in sorted(event_counts.items()))
    snippet_text = "\n".join(snippets)
    return f"events: {counts}\n{snippet_text}".strip()


def _interesting_lines(lines: list[str], limit: int = 24) -> list[str]:
    patterns = (
        re.compile(r"^\s*#"),
        re.compile(r"^\s*(class|def|async def)\s+"),
        re.compile(r"^\s*(function|const|let|var|export|import)\s+"),
        re.compile(r"^\s*\[[A-Za-z0-9_.-]+\]"),
    )
    selected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(line) for pattern in patterns):
            selected.append(stripped)
        if len(selected) >= limit:
            break
    return selected


def _first_nonempty_lines(lines: list[str], limit: int = 8) -> str:
    return "\n".join(line.strip() for line in lines if line.strip())[:1200]


def _document_kind(path: Path, relative: Path) -> str:
    name = path.name.lower()
    if name.startswith("readme"):
        return "readme"
    if name == "roadmap.md":
        return "roadmap"
    if "skills" in relative.parts and path.suffix == ".md":
        return "skill"
    if path.suffix == ".md":
        return "markdown"
    return "source"


def _rank_documents(query: str, documents: list[object]) -> list[dict[str, object]]:
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query)}
    ranked: list[tuple[int, dict[str, object]]] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        haystack = f"{document.get('path', '')}\n{document.get('kind', '')}\n{document.get('summary', '')}".lower()
        score = sum(haystack.count(term) for term in query_terms)
        if score <= 0:
            continue
        ranked.append(
            (
                score,
                {
                    "path": document.get("path", ""),
                    "kind": document.get("kind", ""),
                    "summary": document.get("summary", ""),
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("path", ""))))
    return [item for _, item in ranked]


def _document_to_record(document: IndexedDocument) -> dict[str, object]:
    return {
        "path": document.path,
        "kind": document.kind,
        "summary": document.summary,
        "line_count": document.line_count,
        "byte_count": document.byte_count,
    }


def _index_path(workspace_root: Path) -> Path:
    return resolve_workspace_path(workspace_root, INDEX_RELATIVE_PATH)


def _single_line(text: str, limit: int = 180) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 3] + "..."
