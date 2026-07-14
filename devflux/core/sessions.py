"""Session records — save and list pipeline runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

RUNS_DIR = Path.home() / ".devflux" / "runs"


class SessionRecord:
    """Record of a completed pipeline run."""

    def __init__(
        self,
        user_input: str = "",
        teams: list[str] | None = None,
        complexity: str = "medium",
        roles: list[str] | None = None,
        files: list[str] | None = None,
        tokens: int = 0,
        elapsed: float = 0.0,
        model: str = "",
        project_dir: str = "",
    ) -> None:
        self.timestamp = datetime.now().isoformat()
        self.user_input = user_input
        self.teams = teams or []
        self.complexity = complexity
        self.roles = roles or []
        self.files = files or []
        self.tokens = tokens
        self.elapsed = elapsed
        self.model = model
        self.project_dir = project_dir

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "user_input": self.user_input,
            "teams": self.teams,
            "complexity": self.complexity,
            "roles": self.roles,
            "files": self.files,
            "tokens": self.tokens,
            "elapsed": self.elapsed,
            "model": self.model,
            "project_dir": self.project_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        rec = cls(
            user_input=data.get("user_input", ""),
            teams=data.get("teams", []),
            complexity=data.get("complexity", "medium"),
            roles=data.get("roles", []),
            files=data.get("files", []),
            tokens=data.get("tokens", 0),
            elapsed=data.get("elapsed", 0.0),
            model=data.get("model", ""),
            project_dir=data.get("project_dir", ""),
        )
        rec.timestamp = data.get("timestamp", rec.timestamp)
        return rec

    def save(self) -> Path:
        """Save session to ~/.devflux/runs/<timestamp>.json"""
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        # Safe filename from timestamp
        safe = self.timestamp.replace(":", "-").replace(".", "-")
        path = RUNS_DIR / f"{safe}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        return path

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """List all saved sessions (newest first)."""
        if not RUNS_DIR.exists():
            return []
        sessions: list[dict[str, Any]] = []
        for p in sorted(RUNS_DIR.glob("*.json"), reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    data["file"] = p.name
                    sessions.append(data)
            except Exception:
                continue
        return sessions

    @staticmethod
    def load_last() -> "SessionRecord | None":
        """Load the most recent session."""
        sessions = SessionRecord.list_all()
        if not sessions:
            return None
        return SessionRecord.from_dict(sessions[0])

    def summary(self) -> str:
        """Human-readable session summary."""
        files_str = ", ".join(self.files[:5]) if self.files else "(sin archivos)"
        if len(self.files) > 5:
            files_str += f" ... +{len(self.files) - 5} mas"
        return (
            f"Sesion: {self.timestamp}\n"
            f"  Pedido: {self.user_input[:80]}\n"
            f"  Equipos: {', '.join(self.teams)}\n"
            f"  Complejidad: {self.complexity}\n"
            f"  Roles: {len(self.roles)} ejecutados\n"
            f"  Archivos: {files_str}\n"
            f"  Carpeta: {self.project_dir or '(no registrada)'}\n"
            f"  Tokens: {self.tokens} | Tiempo: {self.elapsed:.1f}s | Modelo: {self.model}"
        )
