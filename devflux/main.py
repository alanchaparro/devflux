"""DevFlux entrypoint — `devflux` command starts the TUI."""

from __future__ import annotations

import argparse
import shutil
import sys

from .core.config import DEVFLUX_DIR
from . import __version__


def _cmd_version() -> None:
    """Print DevFlux version and exit."""
    print(f"DevFlux v{__version__}")
    sys.exit(0)


def _cmd_uninstall() -> None:
    """Remove ~/.devflux/ directory (config, credentials, runs, sessions) after confirmation."""
    confirm = input(
        "¿Seguro que queres desinstalar DevFlux? "
        "Se borraran config y credenciales. [s/N]: "
    ).strip().lower()

    if confirm not in ("s", "si", "sí", "y", "yes"):
        print("Cancelado.")
        sys.exit(0)

    if DEVFLUX_DIR.exists():
        shutil.rmtree(DEVFLUX_DIR, ignore_errors=True)
        print(f"✔ Borrado: {DEVFLUX_DIR}")
    else:
        print(f"ℹ No existe: {DEVFLUX_DIR} (nada que borrar).")

    print("DevFlux desinstalado. Ejecuta: pip uninstall devflux")
    sys.exit(0)


def main() -> None:
    """Entry point for the `devflux` command."""
    parser = argparse.ArgumentParser(
        prog="devflux",
        description="DevFlux — TUI multi-agente para crear proyectos desde cero.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Mostrar la version de DevFlux y salir.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Borrar ~/.devflux/ (config, credenciales, runs, sesiones) y salir.",
    )
    args = parser.parse_args()

    if args.version:
        _cmd_version()

    if args.uninstall:
        _cmd_uninstall()

    # Ensure ~/.devflux/ exists
    DEVFLUX_DIR.mkdir(parents=True, exist_ok=True)

    # Import here to avoid loading Textual for CLI-only paths
    from .tui.app import DevFluxApp

    app = DevFluxApp()
    app.run()


if __name__ == "__main__":
    main()
