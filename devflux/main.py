"""DevFlux entrypoint — `devflux` command starts the TUI."""

from __future__ import annotations

import sys

from .core.config import DevFluxConfig, CONFIG_PATH, DEVFLUX_DIR


def main() -> None:
    """Entry point for the `devflux` command."""
    # Ensure ~/.devflux/ exists
    DEVFLUX_DIR.mkdir(parents=True, exist_ok=True)

    # Import here to avoid loading Textual for CLI-only paths
    from .tui.app import DevFluxApp

    app = DevFluxApp()
    app.run()


if __name__ == "__main__":
    main()