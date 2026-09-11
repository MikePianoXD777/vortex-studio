"""Transformación y animación por keyframes."""

import pytest

from vortex_studio.model import PROPS
from vortex_studio.model.transform import Transform


def clips(ventana):
    return ventana.sequence.video_tracks()[-1].clips


# --- el modelo ------------------------------------------------------------

def test_sin_tocar_es_neutro():
    assert Transform().is_neutral


def test_un_valor_fijo_no_es_neutro():
    assert not Transform(scale=1.5).is_neutral


def test_interpola_entre_dos_keyframes():
    tr = Transform(ease=False)
    tr.set_key("scale", 0.0, 1.0)
    tr.set_key("scale", 2.0, 2.0)
    assert tr.at("scale", 1.0) == pytest.approx(1.5)


def test_la_suavidad_arranca_y_frena():
    """Lineal delata que lo hizo una máquina; suave se ve intencional."""
    tr = Transform(ease=True)
    tr.set_key("x", 0.0, 0.0)
    tr.set_key("x", 1.0, 1.0)

    assert tr.at("x", 0.1) < 0.1        # arranca más lento que lineal
    assert tr.at("x", 0.5) == pytest.approx(0.5)
    assert tr.at("x", 0.9) > 0.9        # y frena al final


def test_fuera_del_rango_se_sostiene():
    tr = Transform()
    tr.set_key("scale", 1.0, 3.0)
    tr.set_key("scale", 2.0, 4.0)
    assert tr.at("scale", 0.0) == 3.0
    assert tr.at("scale", 99.0) == 4.0


def test_dos_keyframes_en_el_mismo_instante_se_reemplazan():
    tr = Transform()
    tr.set_key("x", 1.0, 5.0)
    tr.set_key("x", 1.0, 9.0)
    assert tr.keys["x"] == [[1.0, 9.0]]


def test_quitar_el_ultimo_keyframe_congela_el_valor():
    """Si no, la propiedad pegaría un salto al volver a su número fijo."""
    tr = Transform()
    tr.set_key("scale", 0.0, 2.5)
    tr.remove_key("scale", 0.0)

    assert not tr.animated("scale")
    assert tr.scale == 2.5


def test_todos_los_instantes_animados():
    tr = Transform()
    tr.set_key("x", 0.0, 0.0)
    tr.set_key("y", 1.0, 0.0)
    tr.set_key("x", 1.0, 1.0)
    assert tr.all_keys() == [0.0, 1.0]


def test_restablecer_deja_todo_en_neutro():
    tr = Transform(scale=3.0, rotation=45.0)
    tr.set_key("x", 0.0, 5.0)
    tr.reset()
    assert tr.is_neutral and not tr.keys


# --- en la aplicación -----------------------------------------------------

def brillo(imagen, paso=6):
    return sum(sum(imagen.pixelColor(x, y).getRgb()[:3])
               for y in range(0, imagen.height(), paso)
               for x in range(0, imagen.width(), paso))


def test_achicar_el_clip_deja_negro_alrededor(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    completo = brillo(ventana.preview.current_image())

    clips(ventana)[0].transform.scale = 0.4
    ventana._refresh()
    chico = brillo(ventana.preview.current_image())

    assert chico < completo * 0.5, "achicar no dejó fondo negro"


def test_la_opacidad_oscurece(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    lleno = brillo(ventana.preview.current_image())

    clips(ventana)[0].transform.opacity = 0.25
    ventana._refresh()
    assert brillo(ventana.preview.current_image()) < lleno * 0.5


def test_la_animacion_cambia_la_imagen_con_el_tiempo(ventana, media):
    """Lo importante: que el keyframe mueva pixeles, no solo números."""
    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    clip.transform.set_key("scale", 0.0, 0.2)
    clip.transform.set_key("scale", 4.0, 1.0)

    ventana._seek(0.0)
    chico = brillo(ventana.preview.current_image())
    ventana._seek(4.0)
    grande = brillo(ventana.preview.current_image())

    assert grande > chico * 1.5


def test_el_keyframe_va_pegado_al_clip(ventana, media):
    """Mover el clip debe llevarse su animación, no dejarla atrás."""
    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    clip.transform.set_key("scale", 0.0, 0.3)
    clip.transform.set_key("scale", 2.0, 1.0)

    antes = clip.transform.at("scale", clip.local(1.0))
    clip.start = 10.0
    despues = clip.transform.at("scale", clip.local(11.0))
    assert antes == pytest.approx(despues)


def test_poner_keyframe_de_todo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.key_all_transform()

    transform = clips(ventana)[0].transform
    assert all(transform.animated(p) for p in PROPS)
    assert ventana.history.undo_label == "Keyframe de todo"


def test_el_panel_pone_keyframes(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.timeline.select(clips(ventana)[0])

    ventana.transform_panel._keys["scale"].click()
    assert clips(ventana)[0].transform.animated("scale")

    ventana.transform_panel._keys["scale"].click()
    assert not clips(ventana)[0].transform.animated("scale")


def test_mover_el_deslizador_escribe_el_keyframe_de_aqui(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    clip = clips(ventana)[0]
    ventana.timeline.select(clip)

    ventana.transform_panel._keys["scale"].click()      # se vuelve animada
    ventana._seek(3.0)
    ventana.transform_panel._rows["scale"]._slider.setValue(200)

    assert clip.transform.at("scale", clip.local(3.0)) == pytest.approx(2.0)
    assert clip.transform.at("scale", clip.local(1.0)) == pytest.approx(1.0)


def test_sobrevive_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    clip.transform.set_key("rotation", 0.0, 0.0)
    clip.transform.set_key("rotation", 2.0, 45.0)
    clip.transform.x = 0.25

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.video_tracks()[-1].clips[0]

    assert vuelto.transform.x == 0.25
    assert vuelto.transform.at("rotation", 2.0) == 45.0
    assert vuelto.transform.animated("rotation")


def test_la_animacion_se_exporta(ventana, media, tmp_path):
    from vortex_studio.media import VideoSource
    from vortex_studio.media.encoder import export_video

    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    clip.transform.set_key("scale", 0.0, 0.15)
    clip.transform.set_key("scale", 3.0, 1.0)

    salida = tmp_path / "animado.mp4"
    total = int(round(3 * ventana.sequence.fps))
    export_video(salida, ventana._frames(0.0, 3.0, ventana.sequence.fps), total,
                 ventana.sequence.width, ventana.sequence.height,
                 ventana.sequence.fps, "Borrador")

    fuente = VideoSource(salida)
    try:
        def nivel(t):
            f = fuente.frame_at(t)
            return sum(f.data[:9000]) / 9000
        assert nivel(0.1) < nivel(2.8), "la animación no llegó al archivo"
    finally:
        fuente.close()
