"""Autoguardado y recuperación después de un cierre de golpe."""

import json
import os
import shutil
import time

import pytest
from PySide6.QtWidgets import QMessageBox

from vortex_studio.model import Clip, Project
from vortex_studio.model.autosave import (
    AUTOSAVE_SECONDS,
    autosave_dir,
    autosave_path,
    discard,
    list_recoverable,
    load_recovery,
    write_autosave,
)
from vortex_studio.model.serialize import save_project, sequence_to_dict


@pytest.fixture
def datos(tmp_path, monkeypatch):
    carpeta = tmp_path / "datos"
    monkeypatch.setenv("VORTEX_DATA_DIR", str(carpeta))
    return carpeta


def proyecto_con_clip(fuente="/v.mp4", nombre="demo"):
    p = Project(name=nombre)
    p.active.video_tracks()[-1].add(Clip(source=fuente, start=0.0, duration=3.0))
    return p


# --- el modelo ------------------------------------------------------------

def test_la_copia_va_a_la_carpeta_de_datos(datos):
    ruta = write_autosave(proyecto_con_clip(), None, "abc")
    assert ruta.parent == datos / "autoguardado"
    assert ruta.exists()


def test_la_copia_se_puede_leer_igual(datos):
    original = proyecto_con_clip()
    ruta = write_autosave(original, None, "abc")
    copia = list_recoverable()[0]
    assert copia.path == ruta
    assert sequence_to_dict(load_recovery(copia).active) == sequence_to_dict(original.active)


def test_nunca_se_escribe_encima_del_proyecto(datos, tmp_path):
    proyecto = tmp_path / "mio.vortex"
    save_project(proyecto_con_clip(), proyecto)
    antes = proyecto.read_bytes()

    write_autosave(Project(name="cambiado"), proyecto, "abc")
    assert proyecto.read_bytes() == antes


def test_un_proyecto_guardado_tiene_una_sola_copia(datos, tmp_path):
    proyecto = tmp_path / "mio.vortex"
    save_project(proyecto_con_clip(), proyecto)
    a = write_autosave(proyecto_con_clip(), proyecto, "sesion-1")
    b = write_autosave(proyecto_con_clip(), proyecto, "sesion-2")
    assert a == b
    assert len(list(autosave_dir().glob("*.vortex"))) == 1


def test_dos_proyectos_sin_guardar_no_se_pisan(datos):
    a = write_autosave(proyecto_con_clip(nombre="uno"), None, "sesion-1")
    b = write_autosave(proyecto_con_clip(nombre="dos"), None, "sesion-2")
    assert a != b
    assert {c.name for c in list_recoverable()} == {"uno", "dos"}


def test_la_copia_guarda_de_donde_salio(datos, tmp_path):
    proyecto = tmp_path / "mio.vortex"
    save_project(proyecto_con_clip(), proyecto)
    time.sleep(0.02)
    write_autosave(proyecto_con_clip(), proyecto, "x")
    copia = list_recoverable()[0]
    assert copia.original == proyecto.resolve()
    assert copia.saved_at == pytest.approx(time.time(), abs=5)


def test_una_copia_mas_vieja_que_el_proyecto_no_se_ofrece(datos, tmp_path):
    """Si el usuario guardó después, la copia ya no tiene nada que salvar."""
    proyecto = tmp_path / "mio.vortex"
    save_project(proyecto_con_clip(), proyecto)
    ruta = write_autosave(proyecto_con_clip(), proyecto, "x")

    time.sleep(0.02)
    save_project(proyecto_con_clip(), proyecto)     # guardó después
    assert list_recoverable() == []
    assert not ruta.exists()


def test_si_el_proyecto_desaparecio_la_copia_se_ofrece(datos, tmp_path):
    proyecto = tmp_path / "mio.vortex"
    save_project(proyecto_con_clip(), proyecto)
    time.sleep(0.02)
    write_autosave(proyecto_con_clip(), proyecto, "x")
    proyecto.unlink()
    assert len(list_recoverable()) == 1


def test_una_copia_danada_no_truena(datos):
    autosave_dir().mkdir(parents=True)
    (autosave_dir() / "rota.vortex").write_text("{no es json", encoding="utf-8")
    write_autosave(proyecto_con_clip(nombre="buena"), None, "x")
    assert [c.name for c in list_recoverable()] == ["buena"]


def test_la_mas_nueva_va_primero(datos):
    write_autosave(proyecto_con_clip(nombre="vieja"), None, "a")
    time.sleep(0.02)
    write_autosave(proyecto_con_clip(nombre="nueva"), None, "b")
    assert [c.name for c in list_recoverable()] == ["nueva", "vieja"]


def test_descartar_borra_la_copia(datos):
    ruta = write_autosave(proyecto_con_clip(), None, "x")
    discard(ruta)
    assert not ruta.exists()
    discard(ruta)           # dos veces no truena
    discard(None)


def test_la_copia_usa_rutas_absolutas(datos, tmp_path, media):
    """Vive en otra carpeta: con rutas relativas los clips apuntarían mal."""
    carpeta = tmp_path / "proyecto"
    carpeta.mkdir()
    video = carpeta / "video.mp4"
    shutil.copy(media["mudo"], video)
    proyecto_archivo = carpeta / "p.vortex"
    proyecto = proyecto_con_clip(fuente=video)
    save_project(proyecto, proyecto_archivo)

    time.sleep(0.02)
    ruta = write_autosave(proyecto, proyecto_archivo, "x")
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    fuente = guardado["sequences"][0]["tracks"][2]["clips"][0]["source"]
    assert os.path.isabs(fuente)

    recuperado = load_recovery(list_recoverable()[0])
    assert recuperado.active.video_tracks()[-1].clips[0].source.exists()


def test_no_quedan_temporales(datos):
    write_autosave(proyecto_con_clip(), None, "x")
    assert not list(autosave_dir().glob("*.tmp"))


# --- la ventana -----------------------------------------------------------

def test_sin_cambios_no_se_autoguarda(datos, ventana):
    ventana._dirty = False
    assert ventana.autosave() is None
    assert not autosave_dir().exists() or not list(autosave_dir().iterdir())


def test_con_cambios_se_autoguarda(datos, ventana, media):
    ventana._place_video(media["mudo"])
    ruta = ventana.autosave()
    assert ruta is not None and ruta.exists()


def test_el_reloj_corre_cada_30_segundos(ventana):
    assert AUTOSAVE_SECONDS == 30
    assert ventana._autosave_timer.interval() == 30_000
    assert ventana._autosave_timer.isActive()


def test_lo_que_se_esta_tecleando_tambien_se_salva(datos, ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    ventana.text_panel._text.setPlainText("sin terminar de escribir")

    ruta = ventana.autosave()
    assert "sin terminar de escribir" in ruta.read_text(encoding="utf-8")


def test_guardar_borra_la_copia(datos, ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    ruta = ventana.autosave()
    ventana._path = tmp_path / "p.vortex"
    assert ventana.save()
    assert not ruta.exists()


def test_cerrar_normal_borra_la_copia(datos, qapp, media):
    from vortex_studio.ui import MainWindow

    w = MainWindow()
    w._place_video(media["mudo"])
    ruta = w.autosave()
    w._dirty = False            # el usuario eligió descartar al cerrar
    w.close()
    assert not ruta.exists()


def test_guardar_como_otro_nombre_no_deja_copias_viejas(datos, ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    sin_titulo = ventana.autosave()

    ventana._path = tmp_path / "nuevo.vortex"
    ventana._place_video(media["mudo"])             # otro cambio, sigue sucio
    con_nombre = ventana.autosave()
    assert con_nombre != sin_titulo
    assert not sin_titulo.exists()


# --- recuperar al arrancar ------------------------------------------------

def simular_cierre_de_golpe(qapp, media, preparar=None):
    """Una ventana que autoguarda y "truena": su copia se queda en disco."""
    from vortex_studio.ui import MainWindow

    w = MainWindow()
    w._place_video(media["mudo"])
    if preparar:
        preparar(w)
    ruta = w.autosave()
    w._autosave_path = None     # así cerrarla no borra la copia, como si tronara
    w._dirty = False
    w.close()
    return ruta


@pytest.mark.permite_dialogos
def test_recuperar_trae_el_trabajo(datos, qapp, media, monkeypatch):
    from vortex_studio.ui import MainWindow

    simular_cierre_de_golpe(qapp, media)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    w = MainWindow()
    try:
        assert w.offer_recovery()
        assert len(w.sequence.video_tracks()[-1].clips) == 1
        assert w._dirty, "lo recuperado todavía no está guardado"
        assert w.windowTitle().startswith("*")
        assert "Recuperado" in w.statusBar().currentMessage()
    finally:
        w._dirty = False
        w.close()


@pytest.mark.permite_dialogos
def test_no_recuperar_tira_la_copia(datos, qapp, media, monkeypatch):
    from vortex_studio.ui import MainWindow

    ruta = simular_cierre_de_golpe(qapp, media)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    w = MainWindow()
    try:
        assert not w.offer_recovery()
        assert not ruta.exists()
        assert not w.sequence.video_tracks()[-1].clips
    finally:
        w._dirty = False
        w.close()


def test_sin_copias_no_pregunta_nada(datos, ventana):
    """El candado de diálogos del banco tronaría si preguntara."""
    assert not ventana.offer_recovery()


@pytest.mark.permite_dialogos
def test_lo_recuperado_se_guarda_en_su_proyecto(datos, qapp, media, monkeypatch, tmp_path):
    from vortex_studio.ui import MainWindow

    proyecto = tmp_path / "mio.vortex"

    def con_ruta(w):
        w._path = proyecto
        save_project(w.project, proyecto)
        time.sleep(0.02)
        w._place_video(media["mudo"])       # un cambio después de guardar

    simular_cierre_de_golpe(qapp, media, con_ruta)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    w = MainWindow()
    try:
        assert w.offer_recovery()
        assert w._path == proyecto.resolve()
        assert len(w.sequence.video_tracks()[-1].clips) == 2
        assert w.save()
        assert list_recoverable() == []
    finally:
        w._dirty = False
        w.close()


@pytest.mark.permite_dialogos
def test_despues_de_recuperar_no_hay_nada_que_deshacer(datos, qapp, media, monkeypatch):
    from vortex_studio.ui import MainWindow

    simular_cierre_de_golpe(qapp, media)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    w = MainWindow()
    try:
        w.offer_recovery()
        assert not w.history.can_undo
    finally:
        w._dirty = False
        w.close()
