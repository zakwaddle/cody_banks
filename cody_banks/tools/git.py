"""Read-only git helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True, slots=True)
class GitState:
    is_repo: bool
    branch: str | None = None
    dirty_files: tuple[str, ...] = ()
    diff_summary: str = ""


def inspect_git_state(workspace_root: Path) -> GitState:
    """Return current git state without mutating the repository."""
    if _git(workspace_root, "rev-parse", "--is-inside-work-tree").exit_code != 0:
        return GitState(is_repo=False)

    branch_result = _git(workspace_root, "branch", "--show-current")
    branch = branch_result.stdout.strip() or "HEAD"
    status_result = _git(workspace_root, "status", "--short")
    dirty_files = tuple(_status_path(line) for line in status_result.stdout.splitlines() if line.strip())
    diff_summary_result = _git(workspace_root, "diff", "--stat")
    staged_summary_result = _git(workspace_root, "diff", "--cached", "--stat")
    diff_parts = [
        part.strip()
        for part in (staged_summary_result.stdout, diff_summary_result.stdout)
        if part.strip()
    ]
    return GitState(
        is_repo=True,
        branch=branch,
        dirty_files=dirty_files,
        diff_summary="\n".join(diff_parts),
    )


def format_git_state(state: GitState) -> str:
    if not state.is_repo:
        return "Git: not a repository"

    dirty = "\n".join(f"- {path}" for path in state.dirty_files) or "- clean"
    diff_summary = state.diff_summary or "No diff."
    return f"Git branch: {state.branch}\nDirty files:\n{dirty}\nDiff summary:\n{diff_summary}"


def suggest_commit_message(state: GitState) -> str | None:
    if not state.is_repo or not state.dirty_files:
        return None

    names = [Path(path).name for path in state.dirty_files[:3]]
    if len(names) == 1:
        return f"Update {names[0]}"
    if len(names) == 2:
        return f"Update {names[0]} and {names[1]}"
    return f"Update {', '.join(names[:-1])}, and {names[-1]}"


def _git(workspace_root: Path, *args: str) -> "_GitResult":
    completed = subprocess.run(
        ["git", *args],
        cwd=workspace_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return _GitResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@dataclass(frozen=True, slots=True)
class _GitResult:
    exit_code: int
    stdout: str
    stderr: str


def _status_path(line: str) -> str:
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path
