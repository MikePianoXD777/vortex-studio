"""Ajustes del editor que no son del proyecto: se quedan entre sesiones.

Por ahora solo el interruptor de proxies. Es del editor y no del proyecto
porque depende de la máquina: el mismo proyecto se edita con proxies en la
laptop y sin ellos en la de escritorio.
"""

from __future__ import annotations

import json

from vortex_studio.ui.shortcuts import config_dir


def settings_path():
    return config_dir() / "ajustes.json"


def load_settings() -> dict:
    try:
        datos = json.loads(settings_path().read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(cambios: dict) -> None:
    datos = load_settings()
    datos.update(cambios)
    ruta = settings_path()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass        # sin permiso de escritura, el ajuste vale solo esta sesión
