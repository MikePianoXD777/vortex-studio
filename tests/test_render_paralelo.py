"""Render por segmentos en paralelo, unidos sin recodificar."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from vortex_studio.media.segments import frame_ranges, render_segments
from vortex_studio.model import Clip, Sequence


def _secuencia(media, segundos=2.0):
    secuencia = Sequence.default()
    secuencia.width, secuencia.height = 320, 180
    secuencia.track_named("V1").add(Clip(media["sonoro"], 0.0, segundos))
    secuencia.track_named("A1").add(Clip(media["sonoro"], 0.0, segundos))
    return secuencia


def _armador(secuencia):
    from vortex_studio.ui.renderer import SequenceRenderer

    return lambda: SequenceRenderer(secuencia)


def _cuadros(ruta):
    import av

    with av.open(str(ruta)) as contenedor:
        return [f.to_ndarray(format="rgb24") for f in contenedor.decode(video=0)]


def _carpetas_temporales():
    return set(Path(tempfile.gettempdir()).glob("vortex-segmentos-*"))


# --- partir ------------------------------------------------------------------------------------

def test_los_tramos_caen_en_cuadros_exactos_y_no_dejan_huecos():
    tramos = frame_ranges(1.0, 3.0, 30, 4)
    assert len(tramos) == 4 and tramos[0][0] == 1.0 and tramos[-1][1] == pytest.approx(3.0)
    for (_, fin), (inicio, _) in zip(tramos, tramos[1:]):
        assert fin == inicio
    assert all(abs(round(a * 30) - a * 30) < 1e-9 for a, _ in tramos)


def test_mas_partes_que_cuadros_da_un_tramo_por_cuadro():
    assert len(frame_ranges(0.0, 0.1, 30, 16)) == 3
    assert frame_ranges(0.0, 0.0, 30, 4) == [(0.0, 1 / 30)]


def test_un_tramo_largo_se_reparte_parejo():
    largos = [round((b - a) * 24) for a, b in frame_ranges(0, 10.0, 24, 7)]
    assert sum(largos) == 240 and max(largos) - min(largos) <= 1


# --- exportar ------------------------------------------------------------------------------------

def test_en_paralelo_sale_lo_mismo_que_en_orden(tmp_path, media):
    from vortex_studio.media.encoder import export_video

    secuencia = _secuencia(media)
    paralelo = render_segments(_armador(secuencia), tmp_path / "paralelo.mp4", 0.0, 2.0,
                               (320, 180), 30, workers=3)
    render = _armador(secuencia)()
    export_video(tmp_path / "orden.mp4", render.frames(0.0, 2.0, 30, (320, 180)), 60, 320, 180, 30)
    render.close()
    a, b = _cuadros(paralelo), _cuadros(tmp_path / "orden.mp4")
    assert len(a) == len(b) == 60
    for n in (0, 19, 20, 21, 40, 59):          # incluye las uniones
        assert np.abs(a[n].astype(int) - b[n].astype(int)).mean() < 4


def test_en_paralelo_lleva_el_audio_completo(tmp_path, media):
    import av

    from vortex_studio.media.mixer import AudioMixer

    secuencia = _secuencia(media)
    ruta = render_segments(_armador(secuencia), tmp_path / "con_audio.mp4", 0.0, 2.0, (320, 180),
                           30, audio=AudioMixer(secuencia.audio_clips()).stream(0.0, 2.0),
                           workers=2)
    with av.open(str(ruta)) as contenedor:
        muestras = sum(f.samples for f in contenedor.decode(audio=0))
    assert muestras == pytest.approx(2.0 * 48000, rel=0.03)


def test_el_progreso_llega_al_total(tmp_path, media):
    avances = []
    render_segments(_armador(_secuencia(media, 1.0)), tmp_path / "p.mp4", 0.0, 1.0, (320, 180),
                    30, workers=3, progress=lambda h, t: avances.append((h, t)) or True)
    assert avances[-1] == (30, 30) or max(h for h, _ in avances) == 30
    assert all(t == 30 for _, t in avances)


def test_cancelar_no_deja_archivos(tmp_path, media):
    from vortex_studio.media.encoder import Cancelled

    antes = _carpetas_temporales()
    with pytest.raises(Cancelled):
        render_segments(_armador(_secuencia(media)), tmp_path / "c.mp4", 0.0, 2.0, (320, 180), 30,
                        workers=2, progress=lambda h, t: h < 10)
    assert not (tmp_path / "c.mp4").exists()
    assert _carpetas_temporales() == antes


def test_un_segmento_que_falla_hace_fallar_todo_sin_basura(tmp_path, media):
    class Roto:
        def frames(self, *args):
            raise RuntimeError("se cayó el disco")
            yield

        def close(self):
            pass

    antes = _carpetas_temporales()
    with pytest.raises(RuntimeError, match="disco"):
        render_segments(lambda: Roto(), tmp_path / "f.mp4", 0.0, 2.0, (320, 180), 30, workers=2)
    assert not (tmp_path / "f.mp4").exists()
    assert _carpetas_temporales() == antes


def test_la_cola_de_render_en_paralelo(qapp, tmp_path, media):
    from vortex_studio.media.presets import DEFAULT
    from vortex_studio.model.serialize import sequence_to_dict
    from vortex_studio.ui.render_queue import DONE, RenderJob, RenderQueue

    cola = RenderQueue()
    trabajo = cola.add(RenderJob(path=tmp_path / "cola.mp4", sequence=sequence_to_dict(_secuencia(media)),
                                 media={}, start=0.0, end=2.0, preset=DEFAULT, parallel=True))
    assert cola.wait(120)
    assert trabajo.status == DONE, trabajo.error
    assert len(_cuadros(trabajo.path)) == 60
