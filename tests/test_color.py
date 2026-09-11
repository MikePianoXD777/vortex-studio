"""Corrección de color con los filtros de FFmpeg."""

import pytest

from vortex_studio.media import VideoSource
from vortex_studio.model import ColorAdjust


def medio(frame, muestras=30000):
    return sum(frame.data[:muestras]) / muestras


@pytest.fixture
def gris(media):
    """Gris medio: el único fondo donde gamma y contraste se pueden medir.

    Sobre barras de color no sirve — son valores puros en 0 y 255, donde
    esos dos ajustes no mueven nada y parecería que están rotos.
    """
    fuente = VideoSource(media["gris"])
    yield fuente
    fuente.close()


def test_neutro_no_toca_nada(gris):
    assert abs(medio(gris.frame_at(1.0, ColorAdjust())) - 128) < 2


def test_brillo(gris):
    assert medio(gris.frame_at(1.0, ColorAdjust(brightness=40))) > 150
    assert medio(gris.frame_at(1.0, ColorAdjust(brightness=-40))) < 106


def test_gamma(gris):
    assert medio(gris.frame_at(1.0, ColorAdjust(gamma=220))) > 170
    assert medio(gris.frame_at(1.0, ColorAdjust(gamma=50))) < 90


def test_el_contraste_gira_alrededor_del_gris(gris):
    """El gris medio es el punto fijo del contraste: no debe moverse."""
    assert abs(medio(gris.frame_at(1.0, ColorAdjust(contrast=180))) - 128) < 3
    assert abs(medio(gris.frame_at(1.0, ColorAdjust(contrast=30))) - 128) < 3


def test_saturacion(media):
    fuente = VideoSource(media["mudo"])
    try:
        def separacion(frame):
            px = frame.data[:30000]
            r, g, b = px[0::3], px[1::3], px[2::3]
            return sum(max(a, b, c) - min(a, b, c) for a, b, c in zip(r, g, b)) / len(r)

        normal = separacion(fuente.frame_at(2.0, ColorAdjust()))
        assert separacion(fuente.frame_at(2.0, ColorAdjust(saturation=0))) == 0
        assert separacion(fuente.frame_at(2.0, ColorAdjust(saturation=190))) > normal
    finally:
        fuente.close()


def test_volver_a_neutro_reproduce_el_original(gris):
    base = bytes(gris.frame_at(1.0, ColorAdjust()).data)
    gris.frame_at(1.0, ColorAdjust(brightness=50, saturation=30))
    assert bytes(gris.frame_at(1.0, ColorAdjust()).data) == base


def test_es_neutro():
    assert ColorAdjust().is_neutral
    assert not ColorAdjust(brightness=1).is_neutral
    a = ColorAdjust(brightness=30, gamma=200)
    a.reset()
    assert a.is_neutral
