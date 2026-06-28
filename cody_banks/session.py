"""Session persistence placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionPaths:
    root: Path

    @property
    def sessions_dir(self) -> Path:
        return self.root / "data" / "sessions"

    @property
    def logs_dir(self) -> Path:
        return self.root / "data" / "logs"

