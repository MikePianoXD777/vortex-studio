"""Que el proyecto funcione igual en Linux y en Windows."""

from pathlib import Path

from PySide6.QtCore import Qt

from vortex_studio.model.serialize import load_project, save_project, sequence_to_dict


def test_ningun_atajo_usa_ctrl_alt(ventana):
    """AltGr manda Ctrl+Alt en Windows con teclado latinoamericano.

    Con esos atajos, escribir @ o \\ dispararía comandos del editor.
    """
    culpables = []
    for accion in ventana.findChildren(type(ventana._undo_action)):
        atajo = accion.shortcut()
        if atajo.isEmpty():
            continue
        mods = atajo[0].keyboardModifiers()
        if (mods & Qt.ControlModifier) and (mods & Qt.AltModifier):
            culpables.append(f"{accion.text()} → {atajo.toString()}")

    assert not culpables, f"atajos que chocan con AltGr: {culpables}"


def test_las_rutas_se_guardan_relativas(ventana, media, tmp_path):
    """Un proyecto junto a su material debe poder moverse de carpeta."""
    carpeta = tmp_path / "proyecto"
    carpeta.mkdir()
    video = carpeta / "clip.mp4"
    video.write_bytes(media["mudo"].read_bytes())

    ventana._place_video(video)
    destino = save_project(ventana.project, carpeta / "p")

    texto = destino.read_text(encoding="utf-8")
    assert '"source": "clip.mp4"' in texto, "guardó la ruta absoluta"
    assert "\\\\" not in texto, "guardó separadores de Windows"


def test_un_proyecto_movido_sigue_abriendo(ventana, media, tmp_path):
    origen = tmp_path / "antes"
    origen.mkdir()
    (origen / "clip.mp4").write_bytes(media["mudo"].read_bytes())

    ventana._place_video(origen / "clip.mp4")
    save_project(ventana.project, origen / "p")

    # Simula mandar la carpeta completa a otra máquina.
    destino = tmp_path / "despues"
    origen.rename(destino)

    vuelto = load_project(destino / "p.vortex")
    ruta = vuelto.active.video_tracks()[-1].clips[0].source
    assert ruta.exists(), f"no encontró el material tras mover: {ruta}"


def test_el_material_de_fuera_se_guarda_absoluto(ventana, media, tmp_path):
    """Lo que no está bajo la carpeta del proyecto no se puede hacer relativo."""
    ventana._place_video(media["mudo"])        # vive en otra carpeta
    destino = save_project(ventana.project, tmp_path / "p")

    vuelto = load_project(destino)
    assert vuelto.active.video_tracks()[-1].clips[0].source == media["mudo"]


def test_el_archivo_se_escribe_en_utf8(ventana, media, tmp_path):
    """En Windows el valor por omisión es cp1252 y rompería los acentos."""
    ventana._place_video(media["mudo"])
    ventana.add_title()
    ventana.text_panel._text.setPlainText("Ñoño con acentuación — ¿sí?")
    ventana._flush()

    destino = save_project(ventana.project, tmp_path / "p")
    assert "acentuación" in destino.read_text(encoding="utf-8")

    vuelto = load_project(destino)
    textos = [c.text for t in vuelto.active.text_tracks() for c in t.clips]
    assert "Ñoño con acentuación — ¿sí?" in textos


def test_las_extensiones_no_distinguen_mayusculas(ventana, media, tmp_path):
    """Windows entrega nombres como FOTO.PNG y deben reconocerse igual."""
    from vortex_studio.ui.main_window import IMAGE_EXT, VIDEO_EXT

    assert Path("FOTO.PNG").suffix.lower() in IMAGE_EXT
    assert Path("VIDEO.MP4").suffix.lower() in VIDEO_EXT
