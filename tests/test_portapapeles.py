"""Copiar, cortar, pegar y pegar atributos."""

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from vortex_studio.model import ATTRIBUTES, Clip, Sequence, Title
from vortex_studio.model.commands import Paste, PasteAttributes, copy_items
from vortex_studio.ui.dialogs import PasteAttributesDialog


def test_copiar_y_pegar_lleva_video_y_audio(ventana, media):
    ventana._place_video(media["sonoro"])
    video = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(video)
    assert ventana.copy_selected() == 2

    ventana._seek(6.0)
    ventana.paste()
    v1 = ventana.sequence.video_tracks()[-1].clips
    a1 = ventana.sequence.audio_tracks()[0].clips
    assert len(v1) == len(a1) == 2
    assert v1[1].start == pytest.approx(6.0) == a1[1].start
    assert v1[1].link == a1[1].link != v1[0].link
    assert ventana.timeline.playhead == pytest.approx(12.0)
    assert ventana.history.undo_label == "Pegar"


def test_pegar_dos_veces_pone_una_tras_otra(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana.copy_selected()
    ventana._seek(6.0)
    ventana.paste()
    ventana.paste()
    inicios = [c.start for c in ventana.sequence.video_tracks()[-1].clips]
    assert inicios == pytest.approx([0.0, 6.0, 12.0])


def test_pegar_encima_parte_lo_de_abajo():
    seq = Sequence.default()
    v1 = seq.video_tracks()[-1]
    largo = v1.add(Clip("/tmp/a.mp4", 0.0, 10.0))
    corto = Clip("/tmp/b.mp4", 20.0, 2.0)
    v1.add(corto)
    Paste(entries=copy_items(seq, [corto]), time=4.0).apply(seq)
    tramos = [(c.start, c.end, c.source.name) for c in v1.clips]
    assert tramos[:3] == [(0.0, 4.0, "a.mp4"), (4.0, 6.0, "b.mp4"), (6.0, 10.0, "a.mp4")]
    assert v1.clips[2].in_point == pytest.approx(6.0)


def test_cortar_al_portapapeles(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana.cut_to_clipboard()
    assert not ventana.sequence.video_tracks()[-1].clips
    assert ventana.history.undo_label == "Cortar"
    ventana._seek(0.0)
    ventana.paste()
    assert len(ventana.sequence.video_tracks()[-1].clips) == 1


def test_un_texto_se_pega_en_la_pista_de_texto(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    ventana.copy_selected()
    ventana._seek(4.0)
    ventana.paste()
    textos = ventana.sequence.text_tracks()[0].clips
    assert len(textos) == 2 and textos[1].start == pytest.approx(4.0)


def test_pegar_atributos_de_color_y_transformacion(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._place_video(media["mudo"])
    a, b = ventana.sequence.video_tracks()[-1].clips
    a.color.saturation = 160
    a.transform.scale = 0.5
    a.gain = 0.3
    ventana.timeline.select(a)
    ventana.copy_selected()

    ventana.timeline.select(b)
    assert ventana.paste_attributes_with(("Color",))
    assert b.color.saturation == 160 and b.transform.scale == 1.0
    assert ventana.paste_attributes_with(("Transformación",))
    assert b.transform.scale == 0.5
    assert b.color is not a.color and b.transform is not a.transform
    assert ventana.history.undo_label == "Pegar atributos"


def test_pegar_velocidad_cambia_la_duracion():
    seq = Sequence.default()
    a = seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 4.0))
    b = seq.video_tracks()[-1].add(Clip("/tmp/b.mp4", 4.0, 4.0))
    a.retime(2.0)
    assert PasteAttributes(source=a, targets=[b], groups=("Velocidad",)).apply(seq)
    assert b.speed == 2.0 and b.duration == pytest.approx(2.0)


def test_el_dialogo_apaga_lo_que_no_aplica(qapp):
    titulo = Title(start=0.0, duration=2.0)
    dialogo = PasteAttributesDialog(None, titulo)
    assert not dialogo._boxes["Color"].isEnabled()
    assert not dialogo._boxes["Velocidad"].isEnabled()
    assert "Fundidos" in dialogo.groups()
    assert "Color" not in dialogo.groups()

    clip = Clip("/tmp/a.mp4", 0.0, 2.0)
    dialogo = PasteAttributesDialog(None, clip)
    assert set(dialogo.groups()) == set(ATTRIBUTES) - {"Velocidad"}
    dialogo.set_checked("Velocidad", True)
    assert "Velocidad" in dialogo.groups()


def test_escribiendo_copiar_y_pegar_son_del_cuadro_de_texto(ventana, media):
    campo = QLineEdit()
    ventana._focus_changed(None, campo)
    assert not ventana._actions["editar.pegar"].isEnabled()
    assert not ventana._actions["editar.copiar"].isEnabled()
    ventana._focus_changed(campo, ventana.timeline)
    assert ventana._actions["editar.pegar"].isEnabled()


def test_sin_nada_copiado_avisa(ventana):
    ventana.paste()
    assert "copiado" in ventana.statusBar().currentMessage()
