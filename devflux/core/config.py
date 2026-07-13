"""Configuration management — DevFluxConfig dataclass + YAML."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEVFLUX_DIR = Path.home() / ".devflux"
CONFIG_PATH = DEVFLUX_DIR / "config.yaml"

PROVIDERS = {
    "ollama-local": {
        "label": "Ollama Local",
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

# Hyphens users commonly paste from browsers, chat apps and word processors.
_UNICODE_HYPHENS = "‐‑‒–—−"
_HYPHEN_TRANSLATION = str.maketrans({character: "-" for character in _UNICODE_HYPHENS})


def normalize_provider(value: object) -> str | None:
    """Return a supported canonical provider name, or ``None`` when invalid.

    Provider values can arrive from Textual input, clipboard paste and persisted
    YAML. Normalize all of those at this boundary so comparisons and storage
    always use the ASCII canonical name.
    """
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).translate(_HYPHEN_TRANSLATION)
    normalized = re.sub(r"\s*-\s*", "-", normalized.strip()).casefold()
    return normalized if normalized in PROVIDERS else None


@dataclass
class DevFluxConfig:
    """Runtime configuration for DevFlux."""

    provider: str = "ollama-local"
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434/v1"
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Canonicalize valid providers created by code as well as YAML input."""
        provider = normalize_provider(self.provider)
        if provider is not None:
            self.provider = provider

    # --- persistence ---

    @classmethod
    def load(cls) -> "DevFluxConfig | None":
        """Load a valid config from YAML, normalizing legacy provider spelling."""
        if not CONFIG_PATH.exists():
            return None
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            provider = normalize_provider(data.get("provider", "ollama-local"))
            if provider is None:
                return None
            info = PROVIDERS[provider]
            config = cls(
                provider=provider,
                model=data.get("model", info["models"][0]),
                base_url=data.get("base_url", info["base_url"]),
                temperature=float(data.get("temperature", 0.7)),
                max_tokens=int(data.get("max_tokens", 4096)),
                extra={
                    k: v
                    for k, v in data.items()
                    if k not in ("provider", "model", "base_url", "temperature", "max_tokens")
                },
            )
            # Upgrade a valid legacy spelling so subsequent launches remain canonical.
            if data.get("provider") != provider:
                config.save()
            return config
        except Exception:
            return None

    def save(self) -> None:
        """Save a valid canonical config to YAML with chmod 600."""
        provider = normalize_provider(self.provider)
        if provider is None:
            raise ValueError("Provider inválido; usa 'ollama-local' u 'ollama-cloud'.")
        self.provider = provider
        DEVFLUX_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
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
