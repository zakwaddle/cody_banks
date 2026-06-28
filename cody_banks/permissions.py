"""Permission mode definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import shlex


class PermissionMode(StrEnum):
    ASK = "ask"
    READ_ONLY = "read-only"
    AUTO = "auto"


@dataclass(slots=True)
class PermissionDecision:
    requires_prompt: bool
    blocked: bool = False
    manual_override_allowed: bool = False
    reason: str = ""


SAFE_INSPECTION_COMMANDS = {
    "cat",
    "find",
    "grep",
    "head",
    "ls",
    "pwd",
    "rg",
    "tail",
    "wc",
}

MUTATING_COMMANDS = {
    "chmod",
    "chown",
    "cp",
    "mkdir",
    "mv",
    "rm",
    "rmdir",
    "sed",
    "tee",
    "touch",
    "truncate",
}

PACKAGE_INSTALL_COMMANDS = {
    "apt",
    "apt-get",
    "brew",
    "cargo",
    "gem",
    "go",
    "npm",
    "pnpm",
    "pip",
    "pip3",
    "poetry",
    "uv",
    "yarn",
}

TEST_COMMANDS = {
    "cargo",
    "go",
    "make",
    "npm",
    "pnpm",
    "pytest",
    "python",
    "python3",
    "tox",
    "uv",
    "yarn",
}


def evaluate_shell_command(cmd: str, mode: str, workspace_root: Path | None = None) -> PermissionDecision:
    """Classify a shell command for the Phase 5 permission gate."""
    lowered = cmd.lower()
    manual_block_reason = _manual_block_reason(lowered)
    if manual_block_reason is not None:
        return PermissionDecision(
            requires_prompt=True,
            blocked=True,
            manual_override_allowed=True,
            reason=manual_block_reason,
        )

    try:
        parts = shlex.split(cmd)
    except ValueError:
        return PermissionDecision(requires_prompt=True, reason="could not parse command safely")

    executable = parts[0] if parts else ""
    normalized_mode = mode if mode in {item.value for item in PermissionMode} else PermissionMode.ASK

    destructive_outside_reason = _destructive_outside_workspace_reason(parts, workspace_root)
    if destructive_outside_reason is not None:
        return PermissionDecision(
            requires_prompt=True,
            blocked=True,
            manual_override_allowed=True,
            reason=destructive_outside_reason,
        )

    reason = _prompt_reason(parts, workspace_root)

    if normalized_mode == PermissionMode.READ_ONLY and (reason is not None or executable not in SAFE_INSPECTION_COMMANDS):
        return PermissionDecision(
            requires_prompt=False,
            blocked=True,
            reason="permission mode is read-only",
        )

    if reason is None and executable in SAFE_INSPECTION_COMMANDS:
        return PermissionDecision(requires_prompt=False, reason="safe inspection command")

    if reason is None:
        reason = "command is not recognized as safe inspection"

    if normalized_mode == PermissionMode.AUTO and _auto_can_allow(parts, reason):
        return PermissionDecision(requires_prompt=False, reason=reason)

    return PermissionDecision(requires_prompt=True, reason=reason)


def _manual_block_reason(lowered: str) -> str | None:
    if "rm -rf /" in lowered or "rm -fr /" in lowered:
        return "destructive root removal command"
    if ":(){ :|:& };:" in lowered or ":(){:|:&};:" in lowered:
        return "fork bomb pattern"
    if any(secret in lowered for secret in ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".ssh/")):
        return "command reads private key material"
    if any(pattern in lowered for pattern in ("curl ", "wget ", "nc ", "netcat ", "scp ", "rsync ")):
        if any(secret in lowered for secret in ("secret", "token", "key", "credential", ".env")):
            return "possible credential exfiltration pattern"
    return None


def _prompt_reason(parts: list[str], workspace_root: Path | None) -> str | None:
    executable = parts[0] if parts else ""
    lowered_parts = [part.lower() for part in parts]

    if "sudo" in lowered_parts:
        return "sudo command"

    if executable == "git" and len(parts) > 1 and parts[1] in {"add", "commit", "push", "reset", "checkout", "clean"}:
        return f"git {parts[1]} requires confirmation"

    package_reason = _package_install_reason(parts)
    if package_reason is not None:
        return package_reason

    if _looks_like_long_test(parts):
        return "test command may take a while"

    if executable in MUTATING_COMMANDS:
        return f"{executable} command may modify files"

    outside_path = _outside_workspace_path(parts[1:], workspace_root)
    if outside_path is not None:
        return f"command touches path outside the workspace: {outside_path}"

    if any(_looks_like_shell_write(token) for token in parts):
        return "command contains shell write syntax"

    return None


def _package_install_reason(parts: list[str]) -> str | None:
    if not parts:
        return None
    executable = parts[0]
    lowered = [part.lower() for part in parts]
    install_words = {"add", "install", "i", "sync"}

    if executable in {"pip", "pip3"} and "install" in lowered:
        return "package install requires confirmation"
    if executable in {"npm", "pnpm", "yarn"} and any(word in lowered[1:] for word in install_words):
        return "package install requires confirmation"
    if executable in {"apt", "apt-get", "brew", "gem"} and "install" in lowered:
        return "package install requires confirmation"
    if executable == "uv" and any(word in lowered[1:] for word in {"add", "sync", "pip"}):
        return "package install requires confirmation"
    if executable == "poetry" and any(word in lowered[1:] for word in {"add", "install"}):
        return "package install requires confirmation"
    if executable == "cargo" and "install" in lowered:
        return "package install requires confirmation"
    if executable == "go" and "install" in lowered:
        return "package install requires confirmation"
    if executable in PACKAGE_INSTALL_COMMANDS and "install" in lowered:
        return "package install requires confirmation"
    return None


def _looks_like_long_test(parts: list[str]) -> bool:
    if not parts:
        return False
    executable = parts[0]
    lowered = [part.lower() for part in parts]
    if executable in {"pytest", "tox"}:
        return True
    if executable in {"python", "python3", "uv"} and "pytest" in lowered:
        return True
    if executable in {"npm", "pnpm", "yarn"} and "test" in lowered:
        return True
    if executable == "cargo" and "test" in lowered:
        return True
    if executable == "go" and "test" in lowered:
        return True
    if executable == "make" and any(part in {"test", "check"} for part in lowered[1:]):
        return True
    return executable in TEST_COMMANDS and any(part in {"test", "check"} for part in lowered[1:])


def _outside_workspace_path(tokens: list[str], workspace_root: Path | None) -> str | None:
    if workspace_root is None:
        return next((token for token in tokens if token.startswith("/")), None)

    root = workspace_root.expanduser().resolve()
    for token in tokens:
        if token.startswith("-") or _looks_like_assignment(token):
            continue
        path = Path(token).expanduser()
        if not path.is_absolute() and not token.startswith(".."):
            continue
        candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return token
    return None


def _destructive_outside_workspace_reason(parts: list[str], workspace_root: Path | None) -> str | None:
    if not parts:
        return None
    executable = parts[0]
    if executable not in MUTATING_COMMANDS and executable not in {"git"}:
        return None
    outside_path = _outside_workspace_path(parts[1:], workspace_root)
    if outside_path is None:
        return None
    return f"destructive command touches path outside the workspace: {outside_path}"


def _looks_like_assignment(token: str) -> bool:
    return "=" in token and not token.startswith(("/", "../", "./"))


def _looks_like_shell_write(token: str) -> bool:
    return token in {">", ">>", "2>", "2>>"} or token.startswith((">", ">>", "2>", "2>>"))


def _auto_can_allow(parts: list[str], reason: str) -> bool:
    executable = parts[0] if parts else ""
    if "sudo" in reason or "outside the workspace" in reason:
        return False
    if executable == "git" and len(parts) > 1 and parts[1] in {"push", "reset", "checkout", "clean"}:
        return False
    if "package install" in reason:
        return False
    return True
