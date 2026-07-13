"""Credentials store — API keys in YAML with chmod 600."""

from __future__ import annotations

import os

import yaml

from .config import DEVFLUX_DIR, normalize_provider

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
        """Get a provider's key, including a valid legacy Unicode key name."""
        canonical = normalize_provider(provider)
        if canonical is None:
            return None
        direct = self._data.get(f"{canonical}_key") or self._data.get("api_key")
        if direct:
            return direct
        for field, value in self._data.items():
            prefix = field[:-4] if field.endswith("_key") else field
            if normalize_provider(prefix) == canonical and value:
                return value
        return None

    def set(self, provider: str, key: str) -> None:
        """Store an API key using a canonical provider name."""
        canonical = normalize_provider(provider)
        if canonical is None:
            raise ValueError("Provider inválido; no se puede guardar su API key.")
        self._data[f"{canonical}_key"] = key
        self.save()

    def has_key(self, provider: str) -> bool:
        """Check if a key exists for provider."""
        val = self.get(provider)
        return val is not None and val.strip() != ""
