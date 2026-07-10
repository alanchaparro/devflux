"""Configuration management — DevFluxConfig dataclass + YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

DEVFLUX_DIR = Path.home() / ".devflux"
CONFIG_PATH = DEVFLUX_DIR / "config.yaml"

PROVIDERS = {
    "ollama-local": {
        "label": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
        "models": ["llama3.2", "qwen2.5-coder", "deepseek-r1"],
    },
    "ollama-cloud": {
        "label": "Ollama Cloud",
        "base_url": "https://ollama.com/v1",
        "needs_key": True,
        "models": ["deepseek-v4-pro", "gpt-oss-120b", "qwen3-coder"],
    },
}


@dataclass
class DevFluxConfig:
    """Runtime configuration for DevFlux."""

    provider: str = "ollama-local"
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434/v1"
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict[str, Any] = field(default_factory=dict)

    # --- persistence ---

    @classmethod
    def load(cls) -> "DevFluxConfig | None":
        """Load config from YAML. Returns None if file doesn't exist."""
        if not CONFIG_PATH.exists():
            return None
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return cls(
                provider=data.get("provider", "ollama-local"),
                model=data.get("model", "llama3.2"),
                base_url=data.get("base_url", "http://localhost:11434/v1"),
                temperature=float(data.get("temperature", 0.7)),
                max_tokens=int(data.get("max_tokens", 4096)),
                extra={k: v for k, v in data.items() if k not in
                       ("provider", "model", "base_url", "temperature", "max_tokens")},
            )
        except Exception:
            return None

    def save(self) -> None:
        """Save config to YAML with chmod 600."""
        DEVFLUX_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # Flatten: remove 'extra' key and merge its contents
        extra = data.pop("extra", {})
        data.update(extra)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
        os.chmod(CONFIG_PATH, 0o600)

    def as_dict(self) -> dict[str, Any]:
        """Return config as flat dict."""
        data = asdict(self)
        extra = data.pop("extra", {})
        data.update(extra)
        return data

    @staticmethod
    def exists() -> bool:
        """Check if config file exists."""
        return CONFIG_PATH.exists()

    @staticmethod
    def delete() -> None:
        """Delete config file (uninstall)."""
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        creds_path = DEVFLUX_DIR / "credentials.yaml"
        if creds_path.exists():
            creds_path.unlink()