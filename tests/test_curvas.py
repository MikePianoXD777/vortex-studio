"""Curva de color de cinco puntos y viñeta."""

import pytest

from vortex_studio.media import VideoSource
from vortex_studio.model import CURVE_LOOKS, Curves
from vortex_studio.model.color import LOOKS, ColorAdjust
from vortex_studio.model.curves import SAMPLES


@pytest.fixture
def gris(media):
    fuente = VideoSource(media["gris"])
    yield fuente
    fuente.close()


def pixel(frame, x: int, y: int) -> int:
    """La suma de los tres canales en un punto del cuadro."""
    i = y * frame.stride + x * 3
    return sum(frame.data[i:i + 3])


# --- la curva -------------------------------------------------------------

def test_sin_tocar_es_la_diagonal():
    c = Curves()
    assert c.is_neutral
    for i in range(11):
        assert c.at(i / 10) == pytest.approx(i / 10, abs=1e-6)


def test_pasa_por_sus_anclajes():
    c = Curves(shadows=40, highs=-40)
    for x, y in c.points():
        assert c.at(x) == pytest.approx(y, abs=1e-6)


def test_subir_los_medios_aclara_el_medio():
    assert Curves(mids=50).at(0.5) > 0.5


def test_bajar_las_luces_oscurece_arriba_y_no_abajo():
    c = Curves(highs=-50)
    assert c.at(0.75) < 0.75
    assert c.at(0.10) == pytest.approx(0.10, abs=0.03)


def test_la_curva_en_s_es_monotona():
    """Sin monotonía aparece un rebote de brillo donde nadie puso nada."""
    c = Curves(shadows=-40, highs=40)
    valores = [c.at(i / 60) for i in range(61)]
    assert all(a <= b + 1e-9 for a, b in zip(valores, valores[1:]))


def test_nunca_se_sale_de_rango():
    for c in (Curves(blacks=100, whites=-100), Curves(blacks=-100, whites=100),
              Curves(shadows=100, highs=-100), Curves(mids=-100)):
        assert all(0.0 <= c.at(i / 50) <= 1.0 for i in range(51)), c


def test_fuera_del_rango_se_sostiene():
    c = Curves(mids=30)
    assert c.at(-1.0) == pytest.approx(c.at(0.0))
    assert c.at(2.0) == pytest.approx(c.at(1.0))


def test_restablecer_la_deja_neutra():
    c = Curves(blacks=20, mids=-10)
    c.reset()
    assert c.is_neutral


def test_copiar_no_comparte():
    c = Curves(mids=20)
    otra = c.copy()
    otra.mids = 90
    assert c.mids == 20


def test_lo_que_se_le_manda_a_ffmpeg_esta_muestreado():
    """Mandando la curva muestreada, la gráfica del panel no miente:
    FFmpeg interpola distinto y con cinco puntos no coincidirían."""
    arg = Curves(shadows=-20).ffmpeg_points()
    pares = arg.split(" ")
    assert len(pares) == SAMPLES
    assert pares[0].startswith("0.0000/")
    assert pares[-1].startswith("1.0000/")
    assert all("/" in p for p in pares)


def test_las_curvas_listas_se_portan_bien():
    for nombre, c in CURVE_LOOKS.items():
        assert all(0.0 <= c.at(i / 20) <= 1.0 for i in range(21)), nombre
    assert CURVE_LOOKS["Ninguna"].is_neutral


def test_la_s_sube_el_contraste():
    s = CURVE_LOOKS["Contraste en S"]
    assert s.at(0.25) < 0.25       # sombras más abajo
    assert s.at(0.75) > 0.75       # luces más arriba


def test_los_negros_lavados_levantan_el_negro():
    assert CURVE_LOOKS["Negros lavados"].at(0.0) > 0.05


# --- dentro del ajuste de color -------------------------------------------

def test_una_curva_tocada_rompe_el_neutro():
    """Si no, el procesador se saltaría el filtro y la curva no se vería."""
    adjust = ColorAdjust()
    assert adjust.is_neutral
    adjust.curves.mids = 20
    assert not adjust.is_neutral


def test_la_vinieta_rompe_el_neutro():
    assert not ColorAdjust(vignette=30).is_neutral


def test_copiar_el_color_no_comparte_la_curva():
    """Compartida, ajustar un clip movería la curva de otro."""
    original = ColorAdjust(vignette=10)
    original.curves.mids = 25
    copia = original.copy()
    copia.curves.mids = 90
    assert original.curves.mids == 25


def test_aplicar_un_look_no_muta_el_look(media):
    """Los looks son constantes del módulo: mutarlos los rompería para todos."""
    adjust = ColorAdjust()
    adjust.apply(LOOKS["Cine"])
    adjust.curves.blacks = 99
    assert LOOKS["Cine"].curves.blacks != 99


def test_restablecer_tambien_limpia_curva_y_vinieta():
    adjust = ColorAdjust(vignette=40)
    adjust.curves.highs = -30
    adjust.reset()
    assert adjust.is_neutral


# --- llega a los pixeles --------------------------------------------------

def test_la_curva_aclara_el_gris(gris):
    ajuste = ColorAdjust()
    ajuste.curves.mids = 60
    claro = pixel(gris.frame_at(1.0, ajuste), 80, 60)
    normal = pixel(gris.frame_at(1.0, ColorAdjust()), 80, 60)
    assert claro > normal + 30


def test_la_curva_oscurece_el_gris(gris):
    ajuste = ColorAdjust()
    ajuste.curves.mids = -60
    oscuro = pixel(gris.frame_at(1.0, ajuste), 80, 60)
    assert oscuro < pixel(gris.frame_at(1.0, ColorAdjust()), 80, 60) - 30


def test_la_vinieta_oscurece_las_esquinas_y_no_el_centro(gris):
    """El centro tiene que quedarse igual, o el deslizador sería un brillo."""
    limpio = gris.frame_at(1.0, ColorAdjust())
    centro_limpio = pixel(limpio, 80, 60)

    con = gris.frame_at(1.0, ColorAdjust(vignette=70))
    assert pixel(con, 80, 60) == pytest.approx(centro_limpio, abs=6)
    assert pixel(con, 3, 3) < centro_limpio * 0.7


def test_mas_vinieta_oscurece_mas(gris):
    poca = pixel(gris.frame_at(1.0, ColorAdjust(vignette=25)), 3, 3)
    mucha = pixel(gris.frame_at(1.0, ColorAdjust(vignette=90)), 3, 3)
    assert mucha < poca


def test_vinieta_en_cero_no_hace_nada(gris):
    con = pixel(gris.frame_at(1.0, ColorAdjust(vignette=0)), 3, 3)
    sin = pixel(gris.frame_at(1.0, ColorAdjust()), 3, 3)
    assert con == sin


def test_todos_los_looks_siguen_aplicandose(gris):
    """Ahora traen curva y viñeta: si algo no cuadrara, tronaría aquí."""
    for nombre, look in LOOKS.items():
        assert gris.frame_at(1.0, look) is not None, nombre


def test_el_look_de_cine_oscurece_las_esquinas(gris):
    """Los negros lavados y las esquinas cerradas son el "se ve como cine"."""
    cine = gris.frame_at(1.0, LOOKS["Cine"])
    assert pixel(cine, 3, 3) < pixel(cine, 80, 60)


# --- guardado -------------------------------------------------------------

def test_sobrevive_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(media["mudo"])
    clip = ventana.sequence.top_clip_at(1.0)
    clip.color.vignette = 44
    clip.color.curves.blacks = 18
    clip.color.curves.highs = -22

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.video_tracks()[-1].clips[0]

    assert vuelto.color.vignette == 44
    assert vuelto.color.curves.blacks == 18
    assert vuelto.color.curves.highs == -22
    assert isinstance(vuelto.color.curves, Curves)
