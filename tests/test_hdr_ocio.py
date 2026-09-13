"""Material HDR (PQ y HLG) y espacios de OCIO convertidos a Rec.709 con un LUT horneado."""

import shutil
import subprocess

import numpy as np
import pytest

from vortex_studio.media import colorspace as cs
from vortex_studio.model.color import SPACE_HLG, SPACE_NONE, SPACE_OCIO, SPACE_PQ, ColorAdjust

FFMPEG = shutil.which("ffmpeg")


def _pq(nits):
    """Lo contrario de `pq_to_nits`, para escribir los valores de prueba."""
    m1, m2 = 2610 / 16384, 2523 / 4096 * 128
    c1, c2, c3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
    y = np.power(np.asarray(nits, float) / 10000.0, m1)
    return np.power((c1 + c2 * y) / (1 + c3 * y), m2)


def _gris(valor):
    return np.full((1, 3), valor, dtype=float)


# --- curvas -----------------------------------------------------------------------------

def test_pq_devuelve_los_nits_de_la_norma():
    assert cs.pq_to_nits(np.array([0.0]))[0] == pytest.approx(0.0)
    assert cs.pq_to_nits(np.array([1.0]))[0] == pytest.approx(10000.0)
    assert cs.pq_to_nits(np.array([0.508]))[0] == pytest.approx(100.0, rel=0.03)


def test_hlg_al_75_por_ciento_es_el_blanco_de_referencia():
    assert cs.hlg_to_nits(_gris(0.75))[0, 0] == pytest.approx(203.0, rel=0.03)
    assert cs.hlg_to_nits(_gris(0.0))[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert cs.hlg_to_nits(_gris(1.0))[0, 0] == pytest.approx(1000.0, rel=0.01)


def test_el_tonemapping_lleva_el_pico_al_blanco_y_conserva_el_orden():
    niveles = np.linspace(0, 1000, 50)[:, None].repeat(3, axis=1)
    salida = cs.tonemap(niveles)[:, 0]
    assert salida[-1] == pytest.approx(1.0, abs=1e-6)
    assert np.all(np.diff(salida) > 0)
    assert cs.tonemap(np.array([[203.0, 203.0, 203.0]]))[0, 0] == pytest.approx(0.52, abs=0.02)


# --- conversión completa ------------------------------------------------------------------------

def test_pq_negro_blanco_y_gris_de_referencia():
    negro, gris, pico = (cs.convert(_gris(_pq(n)), SPACE_PQ)[0, 0] for n in (0, 203, 1000))
    assert negro == pytest.approx(0.0, abs=0.01)
    assert 0.6 < gris < 0.85
    assert pico > 0.97


def test_hlg_y_pq_ponen_el_blanco_de_referencia_en_el_mismo_lugar():
    hlg = cs.convert(_gris(0.75), SPACE_HLG)[0, 0]
    pq = cs.convert(_gris(_pq(203)), SPACE_PQ)[0, 0]
    assert hlg == pytest.approx(pq, abs=0.03)


def test_un_rojo_hdr_sigue_siendo_rojo():
    rojo = np.array([[_pq(600), _pq(5), _pq(5)]])
    r, g, b = cs.convert(rojo, SPACE_PQ)[0]
    assert r > 0.8 and g < 0.2 and b < 0.2
    assert np.array_equal(cs.convert(rojo, SPACE_NONE), np.clip(rojo, 0, 1))


# --- el LUT horneado ------------------------------------------------------------------------------

def test_el_lut_se_hornea_una_vez_y_se_reusa():
    ajuste = ColorAdjust(input_space=SPACE_PQ)
    ruta = cs.input_lut(ajuste)
    assert ruta is not None and ruta.exists()
    lineas = ruta.read_text().splitlines()
    assert "LUT_3D_SIZE 33" in lineas and len(lineas) == 2 + 33 ** 3
    fecha = ruta.stat().st_mtime_ns
    assert cs.input_lut(ColorAdjust(input_space=SPACE_PQ)) == ruta
    assert ruta.stat().st_mtime_ns == fecha
    assert cs.input_lut(ColorAdjust(input_space=SPACE_HLG)) != ruta


def test_el_lut_se_lee_con_el_lector_de_luts():
    from vortex_studio.model.lut import read_cube

    cubo = read_cube(cs.input_lut(ColorAdjust(input_space=SPACE_HLG)))
    assert cubo.size == 33
    assert cubo.table[0] == pytest.approx((0, 0, 0), abs=1e-3)


def test_sin_espacio_o_con_uno_imposible_no_hay_lut():
    assert cs.input_lut(ColorAdjust()) is None
    ajuste = ColorAdjust(input_space=SPACE_OCIO, ocio_space="No Existe", ocio_config="/no/hay.ocio")
    assert cs.input_lut(ajuste) is None


def test_el_procesador_convierte_el_material_hdr(media):
    import av

    from vortex_studio.media.color import ColorProcessor

    with av.open(str(media["gris"])) as contenedor:
        cuadro = next(contenedor.decode(video=0))
    ajuste = ColorAdjust(input_space=SPACE_PQ)
    assert not ajuste.is_neutral
    salida = ColorProcessor().apply(cuadro, ajuste).to_ndarray()
    # PQ al 50 % son unos 92 nits: menos que el blanco de referencia, oscurece.
    esperado = cs.convert(_gris(128 / 255), SPACE_PQ)[0, 0] * 255
    assert float(salida.mean()) == pytest.approx(esperado, abs=6)


def test_guardar_limpia_un_espacio_desconocido():
    from vortex_studio.model import Clip
    from vortex_studio.model.serialize import item_from_dict, item_to_dict

    clip = Clip("a.mp4", 0, 1)
    clip.color.input_space = SPACE_HLG
    datos = item_to_dict(clip)
    assert item_from_dict(datos).color.input_space == SPACE_HLG
    datos["color"]["input_space"] = "Dolby Magia"
    assert item_from_dict(datos).color.input_space == SPACE_NONE


# --- detectar HDR al sondear ------------------------------------------------------------------------

def test_la_curva_del_archivo_dice_el_espacio():
    assert cs.space_for_transfer("smpte2084") == SPACE_PQ
    assert cs.space_for_transfer("ARIB-STD-B67") == SPACE_HLG
    assert cs.space_for_transfer("bt709") == SPACE_NONE and cs.space_for_transfer(None) == ""


def test_el_sondeo_lee_la_curva_hdr(tmp_path, media):
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    from vortex_studio.media import probe_media

    ruta = tmp_path / "hdr.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=160x90:rate=30:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p10le",
                    # Sin esto libx264 no escribe la curva en el archivo.
                    "-x264-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                    "-color_primaries", "bt2020", "-color_trc", "smpte2084",
                    "-colorspace", "bt2020nc", str(ruta)], check=True)
    assert probe_media(ruta).color_transfer == "smpte2084"
    assert probe_media(media["mudo"]).color_transfer in ("", "bt709", "unknown", "unspecified")


# --- OCIO ---------------------------------------------------------------------------------------------

requiere_ocio = pytest.mark.skipif(not cs.has_ocio(), reason="opencolorio no está instalado")


@requiere_ocio
def test_ocio_lista_los_espacios_de_la_configuracion_de_estudio():
    espacios = cs.ocio_spaces()
    assert "ACEScct" in espacios and cs.OCIO_DISPLAY in espacios
    assert cs.ocio_spaces("/no/existe.ocio") == []


@requiere_ocio
def test_ocio_de_la_pantalla_a_la_pantalla_no_cambia_nada():
    rejilla = cs.lattice(5)
    salida = cs.convert(rejilla, SPACE_OCIO, "", cs.OCIO_DISPLAY)
    assert np.abs(salida - rejilla).max() < 1e-3


@requiere_ocio
def test_ocio_desde_acescct_cambia_la_imagen_y_hornea_su_lut():
    rejilla = cs.lattice(5)
    salida = cs.convert(rejilla, SPACE_OCIO, "", "ACEScct")
    assert np.abs(salida - rejilla).max() > 0.05
    ruta = cs.input_lut(ColorAdjust(input_space=SPACE_OCIO, ocio_space="ACEScct"))
    assert ruta is not None and ruta.exists()
