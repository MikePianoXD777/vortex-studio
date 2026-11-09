"""Control del editor desde fuera: lo que usa el MCP para que Claude edite.

El editor abierto escucha en un socket local (`server.ControlServer`) y cada
orden se aplica en la ventana como si la hiciera uno con el mouse: se ve en
vivo, entra al historial y se deshace con Ctrl+Z. `vortex_studio.mcp` es el
otro lado: el servidor MCP que Claude arranca y que habla con ese socket.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def socket_path() -> Path:
    """Dónde escucha el editor. Solo tu usuario puede entrar a esa carpeta."""
    propio = os.environ.get("VORTEX_CONTROL_SOCKET")
    if propio:
        return Path(propio)
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / "vortex-studio" / "control.sock"
    uid = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "yo")
    return Path(tempfile.gettempdir()) / f"vortex-studio-{uid}" / "control.sock"
