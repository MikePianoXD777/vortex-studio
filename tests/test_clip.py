"""Fundidos, velocidad y congelar cuadro."""

import pytest

from vortex_studio.model import Clip, ImageOverlay, Title


def clips(ventana):
    return ventana.sequence.video_tracks()[-1].clips


# --- fundidos -------------------------------------------------------------

def test_sin_fundidos_siempre_opaco():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    assert all(c.fade_at(t) == 1.0 for t in (0, 1, 2, 3.99))


def test_fundido_de_entrada():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0, fade_in=1.0)
    assert c.fade_at(0.0) == 0.0
    assert c.fade_at(0.5) == pytest.approx(0.5)
    assert c.fade_at(1.0) == 1.0
    assert c.fade_at(3.0) == 1.0


def test_fundido_de_salida():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0, fade_out=1.0)
    assert c.fade_at(0.0) == 1.0
    assert c.fade_at(3.5) == pytest.approx(0.5)
    assert c.fade_at(4.0) == pytest.approx(0.0)


def test_fundidos_que_no_caben_se_reparten():
    """Encimados dan un bajón al centro que se ve como parpadeo."""
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=1.0, fade_in=2.0, fade_out=2.0)
    assert c.fade_at(0.0) == 0.0
    assert c.fade_at(0.5) == pytest.approx(1.0)     # llega a opaco justo al centro
    assert c.fade_at(1.0) == pytest.approx(0.0)


def test_el_fundido_respeta_donde_empieza_el_clip():
    c = Clip(source="/tmp/a.mp4", start=10.0, duration=4.0, fade_in=1.0)
    assert c.fade_at(10.0) == 0.0
    assert c.fade_at(11.0) == 1.0


def test_los_textos_y_las_imagenes_tambien_se_funden():
    assert Title(start=0.0, duration=2.0, fade_in=1.0).fade_at(0.5) == pytest.approx(0.5)
    assert ImageOverlay(start=0.0, duration=2.0, fade_out=1.0,
                        source="/tmp/l.png").fade_at(1.5) == pytest.approx(0.5)


# --- velocidad ------------------------------------------------------------

def test_velocidad_normal_no_cambia_nada():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    assert c.source_time(2.0) == 2.0


def test_camara_rapida_consume_mas_material():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    c.retime(2.0)
    assert c.duration == 2.0                 # cabe en la mitad de pista
    assert c.source_time(1.0) == 2.0         # pero va al doble en el archivo


def test_camara_lenta_estira():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    c.retime(0.5)
    assert c.duration == 8.0
    assert c.source_time(2.0) == 1.0


def test_cambiar_de_velocidad_no_pierde_material():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    for v in (2.0, 0.25, 4.0, 1.0):
        c.retime(v)
    assert c.duration == pytest.approx(4.0)


def test_la_velocidad_respeta_el_punto_de_entrada():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0, in_point=5.0)
    c.retime(2.0)
    assert c.source_time(0.0) == 5.0
    assert c.source_time(1.0) == 7.0


def test_la_velocidad_tiene_topes():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    c.retime(1000.0)
    assert c.speed <= 10.0
    c.retime(0.0001)
    assert c.speed >= 0.1


# --- en la aplicación -----------------------------------------------------

def test_aplicar_fundido_desde_el_menu(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.select(clips(ventana)[0])
    ventana.set_fade(entrada=1.0, salida=1.0)

    clip = clips(ventana)[0]
    assert clip.fade_in == 1.0 and clip.fade_out == 1.0
    assert ventana.history.undo_label == "Fundido"


def test_el_fundido_no_puede_pasar_del_clip(ventana, media):
    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    ventana.timeline.select(clip)
    ventana.set_fade(entrada=999.0)
    assert clip.fade_in <= clip.duration


def test_cambiar_velocidad_desde_el_menu(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.select(clips(ventana)[0])
    ventana.set_clip_speed(2.0)

    assert clips(ventana)[0].speed == 2.0
    assert "2×" in ventana.history.undo_label


def test_la_velocidad_no_aplica_a_los_textos(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    titulo = ventana.timeline.selected
    ventana.set_clip_speed(2.0)
    assert not hasattr(titulo, "speed")


def test_congelar_cuadro(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.freeze_frame()

    piezas = clips(ventana)
    assert len(piezas) == 2
    congelado = piezas[1]
    assert congelado.speed == 0.0
    # Con velocidad cero el archivo se queda parado en el mismo instante.
    assert congelado.source_time(2.0) == congelado.source_time(3.5)


def test_los_fundidos_sobreviven_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    ventana.timeline.select(clip)
    ventana.set_fade(entrada=0.5, salida=0.75)
    ventana.set_clip_speed(2.0)

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.video_tracks()[-1].clips[0]

    assert vuelto.fade_in == 0.5
    assert vuelto.fade_out == 0.75
    assert vuelto.speed == 2.0


# --- que se vea, no solo que el número esté bien -------------------------

def brillo(imagen, paso=8):
    total = 0
    for y in range(0, imagen.height(), paso):
        for x in range(0, imagen.width(), paso):
            c = imagen.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
    return total


def test_el_fundido_oscurece_de_verdad_la_imagen(ventana, media):
    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    clip.fade_in = 2.0

    ventana._seek(0.0)
    arranque = brillo(ventana.preview.current_image())
    ventana._seek(1.0)
    medio = brillo(ventana.preview.current_image())
    ventana._seek(3.0)
    pleno = brillo(ventana.preview.current_image())

    assert arranque < medio < pleno, "el fundido no llegó a los pixeles"
    assert arranque < pleno * 0.1, "el inicio debería estar casi negro"


def test_el_fundido_del_texto_llega_a_los_pixeles(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(0.0)
    ventana.add_title()
    titulo = ventana.timeline.selected
    titulo.text = "PRUEBA"
    titulo.size = 0.3
    titulo.fade_in = 2.0
    ventana._flush()

    ventana._seek(0.02)
    sin_texto = brillo(ventana.preview.current_image())
    ventana._seek(2.5)
    con_texto = brillo(ventana.preview.current_image())

    assert con_texto != sin_texto


def test_el_fundido_se_exporta(ventana, media, tmp_path):
    """Lo que se ve al editar tiene que ser lo que sale en el archivo."""
    from vortex_studio.media import VideoSource
    from vortex_studio.media.encoder import export_video

    ventana._place_video(media["mudo"])
    clips(ventana)[0].fade_in = 2.0

    salida = tmp_path / "fundido.mp4"
    total = int(round(3 * ventana.sequence.fps))
    export_video(salida, ventana._frames(0.0, 3.0, ventana.sequence.fps), total,
                 ventana.sequence.width, ventana.sequence.height,
                 ventana.sequence.fps, "Borrador")

    fuente = VideoSource(salida)
    try:
        def nivel(t):
            f = fuente.frame_at(t)
            return sum(f.data[:9000]) / 9000

        assert nivel(0.1) < nivel(1.0) < nivel(2.5)
    finally:
        fuente.close()
