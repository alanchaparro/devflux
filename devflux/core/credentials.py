"""Credentials store — API keys in YAML with chmod 600."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .config import DEVFLUX_DIR

CREDS_PATH = DEVFLUX_DIR / "credentials.yaml"


class CredentialsStore:
    """Manages API keys in ~/.devflux/credentials.yaml (chmod 600)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not CREDS_PATH.exists():
            return
        try:
            with open(CREDS_PATH, "r", encoding="utf-8") as fh:
                self._data = yaml.safe_load(fh) or {}
        except Exception:
            self._data = {}

    def save(self) -> None:
        DEVFLUX_DIR.mkdir(parents=True, exist_ok=True)
        with open(CREDS_PATH, "w", encoding="utf-8") as fh:
            yaml.dump(self._data, fh, default_flow_style=False)
        os.chmod(CREDS_PATH, 0o600)

    def get(self, provider: str) -> str | None:
        """Get API key for a provider."""
        return (
            self._data.get(f"{provider}_key")
            or self._data.get("api_key")
            or self._data.get(provider)  # fallback: key stored under provider name
        )

    def set(self, provider: str, key: str) -> None:
        """Store API key for a provider."""
        self._data[f"{provider}_key"] = key
        self.save()

    def has_key(self, provider: str) -> bool:
        """Check if a key exists for provider."""
        val = self.get(provider)
        return val is not None and val.strip() != ""