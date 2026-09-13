"""Keyframes: interpolación, cualquier parámetro y el editor de curvas."""

import numpy as np
import pytest
from PySide6.QtGui import QColor

from vortex_studio.model import Clip, ImageOverlay, Sequence, Title, animate
from vortex_studio.model import keyframes as kf
from vortex_studio.model.transform import Transform


# --- interpolación ----------------------------------------------------------

def puntos(interp=None, handles=None):
    a = [0.0, 0.0] + ([interp] if interp else []) + ([list(handles)] if handles else [])
    return [a, [2.0, 10.0]]


def test_lineal_va_parejo():
    assert kf.evaluate(puntos(kf.LINEAR), 0.5) == pytest.approx(2.5)
    assert kf.evaluate(puntos(kf.LINEAR), 1.0) == pytest.approx(5.0)


def test_suave_arranca_lento_y_se_encuentra_a_la_mitad():
    assert kf.evaluate(puntos(kf.EASE), 0.2) < 1.0
    assert kf.evaluate(puntos(kf.EASE), 1.0) == pytest.approx(5.0)


def test_sostenida_salta_al_llegar():
    p = puntos(kf.HOLD)
    assert kf.evaluate(p, 1.99) == 0.0
    assert kf.evaluate(p, 2.0) == 10.0


def test_bezier_sigue_sus_manijas():
    rapida = puntos(kf.BEZIER, (0.0, 0.9, 0.1, 1.0))      # llega casi de golpe
    lenta = puntos(kf.BEZIER, (0.9, 0.0, 1.0, 0.1))       # espera y sale al final
    assert kf.evaluate(rapida, 0.4) > 8.0
    assert kf.evaluate(lenta, 1.6) < 2.0
    lineal = puntos(kf.BEZIER, (1 / 3, 1 / 3, 2 / 3, 2 / 3))
    assert kf.evaluate(lineal, 1.3) == pytest.approx(6.5, abs=0.01)


def test_la_version_numpy_da_lo_mismo():
    for interp, manijas in ((kf.LINEAR, None), (kf.EASE, None), (kf.HOLD, None),
                            (kf.BEZIER, (0.2, 0.8, 0.4, 1.0))):
        p = puntos(interp, manijas)
        instantes = np.linspace(-0.5, 2.5, 61)
        uno_por_uno = [kf.evaluate(p, float(t)) for t in instantes]
        assert kf.evaluate_many(p, instantes) == pytest.approx(uno_por_uno, abs=1e-6)


def test_los_keyframes_viejos_siguen_igual():
    """Un proyecto de la 0.4 guardaba [t, v]: tiene que moverse igual."""
    tr = Transform(ease=False)
    tr.keys["x"] = [[0.0, 0.0], [1.0, 1.0]]
    assert tr.at("x", 0.25) == pytest.approx(0.25)
    tr.ease = True
    assert tr.at("x", 0.25) < 0.25


def test_poner_encima_conserva_la_interpolacion():
    p = kf.set_interpolation(puntos(), 0.0, kf.HOLD)
    p = kf.set_key(p, 0.0, 3.0)
    assert kf.interp_of(p[0]) == kf.HOLD and kf.value_of(p[0]) == 3.0


def test_mover_un_keyframe_lo_reordena_y_conserva_la_curva():
    p = kf.set_interpolation([[0.0, 0.0], [1.0, 5.0], [2.0, 9.0]], 1.0, kf.LINEAR)
    p = kf.move_key(p, 1.0, 1.5, 7.0)
    assert [kf.time_of(k) for k in p] == [0.0, 1.5, 2.0]
    assert kf.interp_of(p[1]) == kf.LINEAR and kf.value_of(p[1]) == 7.0


# --- cualquier parámetro -------------------------------------------------------

def test_animar_color_mascara_y_volumen():
    clip = Clip("/tmp/a.mp4", 0.0, 4.0)
    animate.add_key(clip, "color.saturation", 0.0, 0)
    animate.add_key(clip, "color.saturation", 2.0, 200)
    animate.add_key(clip, "mask.x", 0.0, 0.2)
    animate.add_key(clip, "mask.x", 2.0, 0.8)
    vista = animate.view(clip, 1.0)
    assert vista.color.saturation == pytest.approx(100)
    assert vista.mask.x == pytest.approx(0.5)
    assert clip.color.saturation == 100 and clip.mask.x == 0.5      # el original intacto
    assert vista is not clip and animate.view(Clip("/tmp/b.mp4", 0, 1), 0.5).name == "b"


def test_imagen_y_texto_tambien():
    img = ImageOverlay(start=1.0, duration=2.0, source="/tmp/l.png")
    animate.add_key(img, "opacity", 0.0, 0.0)
    animate.add_key(img, "opacity", 2.0, 1.0)
    titulo = Title(start=0.0, duration=2.0)
    animate.add_key(titulo, "size", 0.0, 0.05)
    animate.add_key(titulo, "size", 1.0, 0.15)
    assert animate.view(img, 1.0).opacity == pytest.approx(0.5)
    assert animate.view(titulo, 0.5).size == pytest.approx(0.10)
    assert {p.path for p in animate.params_for(titulo)} >= {"x", "y", "size"}


def test_bake_y_absorb_convierten_el_deslizador_en_keyframe():
    clip = Clip("/tmp/a.mp4", 0.0, 4.0)
    animate.add_key(clip, "color.brightness", 0.0, -50)
    animate.add_key(clip, "color.brightness", 4.0, 50)
    animate.bake(clip, 2.0)
    assert clip.color.brightness == 0
    assert animate.absorb(clip, 2.0) == []            # nadie movió nada
    clip.color.brightness = 30                        # el usuario mueve el deslizador
    assert animate.absorb(clip, 2.0) == ["color.brightness"]
    assert animate.value_at(clip, "color.brightness", 2.0) == pytest.approx(30)
    assert len(animate.keys_for(clip, "color.brightness")) == 3


def test_quitar_el_ultimo_congela_el_valor():
    clip = Clip("/tmp/a.mp4", 0.0, 4.0)
    animate.add_key(clip, "gain", 1.0, 0.4)
    assert animate.remove_key(clip, "gain", 1.0)
    assert not animate.is_animated(clip, "gain") and clip.gain == pytest.approx(0.4)


def test_dividir_recorre_los_keyframes_de_todo():
    from vortex_studio.model.commands import split_item

    seq = Sequence.default()
    clip = seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 6.0))
    animate.add_key(clip, "color.saturation", 0.0, 0, kf.LINEAR)
    animate.add_key(clip, "color.saturation", 6.0, 200)
    antes = animate.value_at(clip, "color.saturation", 4.5)
    segunda = split_item(seq, clip, 3.0)
    assert animate.value_at(segunda, "color.saturation", 1.5) == pytest.approx(antes)


def test_se_guarda_con_su_interpolacion(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    clip = proyecto.active.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 2.0))
    animate.add_key(clip, "mask.feather", 0.0, 0.0, kf.BEZIER)
    animate.add_key(clip, "mask.feather", 2.0, 0.2)
    clip.transform.set_key("x", 0.0, 0.0, kf.HOLD)
    leido = load_project(save_project(proyecto, tmp_path / "p")).active.video_tracks()[-1].clips[0]
    assert kf.interp_of(animate.keys_for(leido, "mask.feather")[0]) == kf.BEZIER
    assert kf.interp_of(leido.transform.keys["x"][0]) == kf.HOLD


# --- que se vea y se oiga ---------------------------------------------------------

def test_la_saturacion_animada_llega_a_los_pixeles(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    animate.add_key(clip, "color.saturation", 0.0, 0)
    animate.add_key(clip, "color.saturation", 1.0, 0, kf.HOLD)
    animate.add_key(clip, "color.saturation", 3.0, 200)

    def colorido(t):
        ventana._seek(t)
        img = ventana.preview.current_image()
        c = [QColor(img.pixel(x, 60)) for x in range(20, 300, 20)]
        return sum(max(q.red(), q.green(), q.blue()) - min(q.red(), q.green(), q.blue())
                   for q in c)

    assert colorido(0.5) < 40, "a saturación 0 tenía que verse gris"
    assert colorido(4.0) > colorido(0.5) * 5


def test_la_mascara_animada_se_mueve_en_la_exportacion(ventana, media):
    ventana._place_video(media["gris"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    clip.mask.shape = "Rectángulo"
    clip.mask.width, clip.mask.height, clip.mask.feather = 0.3, 1.0, 0.0
    animate.add_key(clip, "mask.x", 0.0, 0.2, kf.LINEAR)
    animate.add_key(clip, "mask.x", 1.0, 0.8)
    inicio = next(ventana._frames(0.0, 0.1, 30))
    final = next(ventana._frames(0.99, 1.1, 30))
    brillo = lambda img, x: QColor(img.pixel(x, 60)).lightness()
    assert brillo(inicio, 32) > 100 and brillo(inicio, 128) < 20
    assert brillo(final, 128) > 100 and brillo(final, 32) < 20


def test_el_volumen_animado_sube_muestra_por_muestra(media):
    from vortex_studio.media.audio import RATE, AudioRenderer

    clip = Clip(source=media["tono"], start=0.0, duration=2.0)
    animate.add_key(clip, "gain", 0.0, 0.0, kf.LINEAR)
    animate.add_key(clip, "gain", 2.0, 1.0)
    datos = np.concatenate([f.to_ndarray()[0] for f in AudioRenderer([clip]).stream(0.0, 2.0)])
    nivel = lambda a, b: float(np.abs(datos[int(a * RATE):int(b * RATE)]).mean())
    assert nivel(0.0, 0.1) < nivel(0.9, 1.1) * 0.2
    assert nivel(0.9, 1.1) == pytest.approx(nivel(1.8, 2.0) * 0.53, rel=0.15)


# --- el editor y los paneles --------------------------------------------------------

def test_mover_el_deslizador_de_algo_animado_pone_keyframe(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    animate.add_key(clip, "color.contrast", 0.0, 80)
    animate.add_key(clip, "color.contrast", 4.0, 120)
    ventana._seek(2.0)
    assert ventana.color_panel._contrast.value() == 100          # el valor de este instante
    ventana.color_panel._contrast._slider.setValue(150)
    ventana._flush()
    assert animate.value_at(clip, "color.contrast", 2.0) == pytest.approx(150)
    assert len(animate.keys_for(clip, "color.contrast")) == 3


def test_el_editor_pone_mueve_y_cambia_interpolacion(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana.open_keyframe_editor("color.temperature")
    editor = ventana.keyframe_editor
    assert editor.param.currentData() == "color.temperature"

    ventana._seek(1.0)
    editor.add_key_here()
    assert ventana.history.undo_label == "Keyframe"
    editor.graph.move_key(1.0, 2.0, 60.0)
    editor.graph.add_key(4.0)
    editor.graph.selected = 2.0
    assert editor.graph.set_interpolation(kf.HOLD)
    puntos_ = animate.keys_for(clip, "color.temperature")
    assert [kf.time_of(k) for k in puntos_] == [2.0, 4.0]
    assert kf.interp_of(puntos_[0]) == kf.HOLD
    assert editor.param.currentText().startswith("◆")


def test_arrastrar_la_manija_bezier(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    animate.add_key(clip, "gain", 0.0, 0.0)
    animate.add_key(clip, "gain", 2.0, 1.0)
    ventana.timeline.select(clip)
    ventana.open_keyframe_editor("gain")
    grafica = ventana.keyframe_editor.graph
    grafica.move_handle(0.0, 1, 0.0, 0.9)
    k = animate.keys_for(clip, "gain")[0]
    assert kf.interp_of(k) == kf.BEZIER and kf.handles_of(k)[:2] == pytest.approx((0.0, 0.9))
    assert animate.value_at(clip, "gain", 0.4) > 0.6


def test_los_rombos_del_timeline_incluyen_cualquier_parametro():
    clip = Clip("/tmp/a.mp4", 0.0, 4.0)
    clip.transform.set_key("x", 1.0, 0.2)
    animate.add_key(clip, "color.exposure", 3.0, 50)
    assert animate.all_key_times(clip) == [1.0, 3.0]
