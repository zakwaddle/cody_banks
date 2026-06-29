"""Session persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionPaths:
    root: Path

    @property
    def sessions_dir(self) -> Path:
        return self.root / "data" / "sessions"

    @property
    def logs_dir(self) -> Path:
        return self.root / "data" / "logs"


@dataclass(frozen=True, slots=True)
class SessionRecorder:
    path: Path

    @classmethod
    def create(cls, workspace_root: Path) -> "SessionRecorder":
        paths = SessionPaths(workspace_root)
        paths.sessions_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return cls(paths.sessions_dir / f"{timestamp}.jsonl")

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event_type,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as session_file:
            session_file.write(json.dumps(record, sort_keys=True) + "\n")
