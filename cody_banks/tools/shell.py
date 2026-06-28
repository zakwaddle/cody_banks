"""Shell command tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import time


@dataclass(frozen=True, slots=True)
class ShellResult:
    cmd: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float


def run_shell(cmd: str, workspace_root: Path, timeout_seconds: float = 120.0) -> ShellResult:
    """Run a shell command from the workspace root and capture its result."""
    start = time.monotonic()
    try:
        completed = subprocess.run(
            cmd,
            cwd=workspace_root,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ShellResult(
            cmd=cmd,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_seconds=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as exc:
        return ShellResult(
            cmd=cmd,
            exit_code=124,
            stdout=exc.stdout or "",
            stderr=f"Command timed out after {timeout_seconds:.0f} seconds.",
            elapsed_seconds=time.monotonic() - start,
        )


def cd_target_outside_workspace(cmd: str, workspace_root: Path) -> str | None:
    """Return the escaped cd target if a shell command changes outside the workspace."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None

    root = workspace_root.resolve()
    for index, part in enumerate(parts):
        if part != "cd":
            continue
        target = parts[index + 1] if index + 1 < len(parts) else str(root)
        candidate = (root / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return target
    return None
