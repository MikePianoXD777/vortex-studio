"""La onda de audio: mínimo y máximo por cubo, con caché en disco."""

import os
import shutil

import numpy as np
import pytest

from vortex_studio.media import waveform
from vortex_studio.media.audio import peaks
from vortex_studio.media.waveform import cache_path, compute, load_or_compute


@pytest.fixture
def cache(tmp_path, monkeypatch):
    carpeta = tmp_path / "cache"
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(carpeta))
    return carpeta


# --- el cálculo -----------------------------------------------------------

def test_trae_minimos_y_maximos(media):
    datos = compute(media["tono"], 60)
    assert datos.shape[0] == 2
    assert datos.shape[1] == pytest.approx(180, abs=2)      # 3 s × 60
    assert (datos[0] <= datos[1]).all()
    assert datos[0].min() < -0.2 and datos[1].max() > 0.2


def test_la_onda_de_un_seno_es_simetrica(media):
    """Un seno sube lo mismo que baja: si no, se está perdiendo un lado."""
    datos = compute(media["tono"], 60)
    medio = slice(10, -10)
    assert abs(datos[0, medio].mean() + datos[1, medio].mean()) < 0.05


def test_se_queda_en_rango(media):
    datos = compute(media["sonoro"], 40)
    assert datos.min() >= -1.0 and datos.max() <= 1.0


def test_un_video_mudo_da_onda_vacia(media):
    assert compute(media["mudo"], 60).shape == (2, 0)


def test_un_archivo_inexistente_da_onda_vacia(tmp_path):
    assert compute(tmp_path / "no-existe.wav", 60).shape == (2, 0)


def test_los_picos_de_siempre_salen_de_la_onda(media):
    datos = compute(media["tono"], 40)
    picos = peaks(media["tono"], 40)
    assert len(picos) == datos.shape[1]
    assert max(picos) == pytest.approx(max(-datos[0].min(), datos[1].max()), abs=1e-5)


# --- la caché en disco ----------------------------------------------------

def test_se_guarda_en_disco(cache, media):
    datos = load_or_compute(media["tono"], 60)
    archivo = cache_path(media["tono"], 60)
    assert archivo.exists()
    assert archivo.parent == cache / "ondas"
    assert np.array_equal(np.load(archivo), datos)


def test_la_segunda_vez_no_decodifica(cache, media, monkeypatch):
    primera = load_or_compute(media["tono"], 60)

    def prohibido(*a, **k):
        raise AssertionError("volvió a decodificar teniendo la onda en disco")
    monkeypatch.setattr(waveform.av, "open", prohibido)

    segunda = load_or_compute(media["tono"], 60)
    assert np.array_equal(primera, segunda)


def test_si_el_archivo_cambia_se_recalcula(cache, media, tmp_path):
    copia = tmp_path / "copia.wav"
    shutil.copy(media["tono"], copia)
    antes = cache_path(copia, 60)
    load_or_compute(copia, 60)

    os.utime(copia, ns=(1_000_000_000_000_000, 1_000_000_000_000_000))
    despues = cache_path(copia, 60)
    assert despues != antes
    load_or_compute(copia, 60)
    assert despues.exists()


def test_otra_resolucion_es_otra_onda(cache, media):
    assert cache_path(media["tono"], 60) != cache_path(media["tono"], 30)


def test_un_cache_corrupto_se_recalcula(cache, media):
    archivo = cache_path(media["tono"], 60)
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(b"esto no es un .npy")

    datos = load_or_compute(media["tono"], 60)
    assert datos.shape[1] > 100
    assert np.load(archivo).shape == datos.shape      # y quedó arreglado


def test_una_onda_vacia_no_se_guarda(cache, media):
    load_or_compute(media["mudo"], 60)
    assert not cache_path(media["mudo"], 60).exists()


def test_no_quedan_temporales(cache, media):
    load_or_compute(media["tono"], 60)
    assert not list((cache / "ondas").glob("*.tmp.npy"))


# --- en el timeline -------------------------------------------------------

@pytest.fixture
def contar(monkeypatch):
    import vortex_studio.ui.waveforms as modulo

    llamadas = []
    real = modulo.load_or_compute
    monkeypatch.setattr(modulo, "load_or_compute",
                        lambda p, s: llamadas.append(p) or real(p, s))
    return llamadas


def test_importar_pide_la_onda_de_una_vez(ventana, media, contar):
    ventana._place_video(media["sonoro"])
    ventana.timeline.waves.wait()
    assert len(contar) == 1


def test_importar_audio_suelto_tambien(ventana, media, contar):
    ventana._place_audio(media["tono"])
    ventana.timeline.waves.wait()
    assert len(contar) == 1


def test_un_video_mudo_no_pide_onda(ventana, media, contar):
    ventana._place_video(media["mudo"])
    ventana.timeline.waves.wait()
    assert contar == []


def test_el_zoom_no_recalcula(ventana, media, contar, qapp):
    ventana._place_video(media["sonoro"])
    ventana.timeline.waves.wait()
    qapp.processEvents()

    for zoom in (4.0, 30.0, 300.0, 2000.0):
        ventana.timeline.pixels_per_second = zoom
        ventana.timeline.repaint()
    assert len(contar) == 1


def test_la_onda_se_dibuja_en_la_pista(ventana, media, qapp, monkeypatch):
    """Que la onda llegue a los pixeles del timeline, no solo al arreglo.

    Se compara el timeline con onda contra el mismo timeline sin onda. La
    primera versión de esta prueba contaba pixeles "claros", y el verde de
    la onda sobre el clip queda justo en el umbral: fallaba con la onda
    perfectamente dibujada. Comparar contra la ausencia no depende de
    colores.
    """
    from PySide6.QtGui import QPixmap

    from vortex_studio.media.waveform import empty

    ventana._place_video(media["sonoro"])
    ventana.timeline.waves.wait()
    qapp.processEvents()

    timeline = ventana.timeline
    pista = timeline.sequence.tracks.index(timeline.sequence.audio_tracks()[0])
    arriba = int(timeline._track_top(pista))

    def banda():
        lienzo = QPixmap(timeline.size())
        timeline.render(lienzo)
        img = lienzo.toImage()
        return [img.pixel(x, y) for x in range(150, 400)
                for y in range(arriba + 4, arriba + 36)]

    con_onda = banda()
    monkeypatch.setattr(timeline, "_wave_for", lambda source: empty())
    sin_onda = banda()

    distintos = sum(1 for a, b in zip(con_onda, sin_onda) if a != b)
    assert distintos > 1500, f"la onda casi no cambia la pista ({distintos} pixeles)"
