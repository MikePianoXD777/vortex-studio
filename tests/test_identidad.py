"""Que dos elementos con los mismos datos sigan siendo cosas distintas.

Los clips se comparan por identidad y no por valor. Con la igualdad por
valor que da un dataclass, el clip de video y el de audio que salen del
mismo archivo resultaban iguales, y todo lo que usa `==` por dentro
—`lista.remove(x)`, `x in lista`, `lista.index(x)`— agarraba el equivocado.
"""

from vortex_studio.model import Clip, ImageOverlay, Title


def video_y_audio(ventana, media):
    """Video y audio del mismo archivo, **desenlazados**.

    Desde la 0.4 entran enlazados y borrar uno se lleva al otro a propósito
    (eso lo prueba `test_enlace.py`). Aquí se sueltan para que estas pruebas
    sigan cuidando lo suyo: que dos clips con los mismos datos no se
    confundan entre sí.
    """
    ventana._place_video(media["sonoro"])
    video = ventana.sequence.video_tracks()[-1].clips[0]
    audio = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(video)
    ventana.toggle_link()
    assert not video.link and not audio.link
    return video, audio


def test_dos_clips_con_los_mismos_datos_no_son_iguales():
    a = Clip(source="/tmp/x.mp4", start=0.0, duration=5.0)
    b = Clip(source="/tmp/x.mp4", start=0.0, duration=5.0)
    assert a != b
    assert a == a


def test_dos_textos_iguales_son_distintos():
    a = Title(start=0.0, duration=2.0, text="hola")
    b = Title(start=0.0, duration=2.0, text="hola")
    assert a != b


def test_dos_imagenes_iguales_son_distintas():
    a = ImageOverlay(start=0.0, duration=2.0, source="/tmp/l.png")
    b = ImageOverlay(start=0.0, duration=2.0, source="/tmp/l.png")
    assert a != b


def test_el_video_y_su_audio_estan_en_pistas_distintas(ventana, media):
    video, audio = video_y_audio(ventana, media)
    assert video != audio
    assert ventana._track_of(video).name == "V1"
    assert ventana._track_of(audio).name == "A1"


def test_borrar_el_audio_no_se_lleva_el_video(ventana, media):
    video, audio = video_y_audio(ventana, media)

    ventana.timeline.select(audio)
    ventana.delete_selected()

    assert len(ventana.sequence.video_tracks()[-1].clips) == 1
    assert len(ventana.sequence.audio_tracks()[0].clips) == 0


def test_borrar_el_video_no_se_lleva_el_audio(ventana, media):
    video, audio = video_y_audio(ventana, media)

    ventana.timeline.select(video)
    ventana.delete_selected()

    assert len(ventana.sequence.video_tracks()[-1].clips) == 0
    assert len(ventana.sequence.audio_tracks()[0].clips) == 1


def test_cortar_el_audio_no_corta_el_video(ventana, media):
    video, audio = video_y_audio(ventana, media)

    ventana._seek(2.0)
    ventana.timeline.select(audio)
    ventana.cut_at_playhead()

    assert len(ventana.sequence.audio_tracks()[0].clips) == 2
    assert len(ventana.sequence.video_tracks()[-1].clips) == 1


def test_duplicar_el_audio_no_duplica_el_video(ventana, media):
    video, audio = video_y_audio(ventana, media)

    ventana.timeline.select(audio)
    ventana.duplicate_selected()

    assert len(ventana.sequence.audio_tracks()[0].clips) == 2
    assert len(ventana.sequence.video_tracks()[-1].clips) == 1


def test_dos_textos_identicos_se_borran_por_separado(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.add_title()
    primero = ventana.timeline.selected
    ventana.add_title()

    ventana.delete_title(primero)
    quedan = [c for t in ventana.sequence.text_tracks() for c in t.clips]
    assert len(quedan) == 1
    assert quedan[0] is not primero
