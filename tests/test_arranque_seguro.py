"""Que el editor no muera en silencio al arrancar.

El ejecutable de Windows va sin consola: un error antes de la ventana era
doble clic y nada. Y la flechita de los combos vivía en /tmp con nombre fijo.
"""

import os
from pathlib import Path

import pytest

from vortex_studio import app as app_mod


def test_un_error_al_arrancar_queda_apuntado(tmp_path, monkeypatch):
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(app_mod, "_main",
                        lambda argv=None: (_ for _ in ()).throw(RuntimeError("tronó feo")))
    monkeypatch.setattr(app_mod, "_show_crash", lambda *a: None)

    assert app_mod.main([]) == 1
    registro = (tmp_path / "vortex-studio" / "error.log").read_text(encoding="utf-8")
    assert "tronó feo" in registro and "RuntimeError" in registro


def test_el_aviso_no_impide_que_termine(tmp_path, monkeypatch):
    """Si hasta el aviso falla, main devuelve 1 en vez de arrastrar el error."""
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(app_mod, "_main",
                        lambda argv=None: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(app_mod, "_show_crash",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("ni el aviso")))
    with pytest.raises(RuntimeError):
        app_mod.main([])


def test_sin_poder_escribir_el_registro_igual_termina(tmp_path, monkeypatch):
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(tmp_path / "no" / "se" / "puede"))
    monkeypatch.setattr(app_mod, "error_log",
                        lambda: (_ for _ in ()).throw(OSError("sin permiso")))
    monkeypatch.setattr(app_mod, "_main",
                        lambda argv=None: (_ for _ in ()).throw(RuntimeError("igual truena")))
    monkeypatch.setattr(app_mod, "_show_crash", lambda *a: None)
    assert app_mod.main([]) == 1


def test_la_flechita_vive_en_la_cache_del_usuario(tmp_path, monkeypatch):
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(tmp_path))
    from vortex_studio.ui import theme

    ruta = Path(theme._flecha())
    assert ruta.is_file()
    assert tmp_path in ruta.parents
    assert ruta.read_text(encoding="utf-8").startswith("<svg")


def test_una_flechita_corrupta_no_tumba_el_arranque(tmp_path, monkeypatch):
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(tmp_path))
    from vortex_studio.ui import theme

    destino = tmp_path / "vortex-studio" / "flecha.svg"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"\xff\xfe\x00basura binaria")
    assert theme._flecha()      # la reescribe en vez de tronar


def test_sin_carpeta_de_cache_el_tema_sigue_sirviendo(tmp_path, monkeypatch):
    """Sin poder escribir, el combo se queda sin adorno pero el editor abre."""
    monkeypatch.setenv("VORTEX_CACHE_DIR", os.devnull)
    from vortex_studio.ui import theme

    assert theme._flecha() == ""
