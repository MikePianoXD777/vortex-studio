"""Ajustes de foto: identidad, dirección de cada control y casos raros."""

from __future__ import annotations

import numpy as np
import pytest
from ayuda_photo import colorido, degradado, lum, ruido, solido

from vortex_studio.photo.adjust import apply_adjustments, curve_lut, pchip
from vortex_studio.photo.document import Adjustments


def aplicar(px, scale=1.0, **kw):
    return apply_adjustments(px, Adjustments(**kw), scale)


def test_ajustes_neutros_no_cambian_nada():
    px = ruido()
    out = apply_adjustments(px, Adjustments())
    assert np.array_equal(out, px)
    assert out is px


def test_ajustes_con_valores_que_no_hacen_nada_son_identidad():
    px = ruido()
    # curva recta, HSL en cero y franjas desconocidas no deben tocar un bit
    adj = Adjustments(curve=[(0, 0), (0.5, 0.5), (1, 1)], hsl={"red": (0, 0, 0)})
    assert np.array_equal(apply_adjustments(px, adj), px)


def test_el_alfa_nunca_se_toca():
    px = colorido()
    px[..., 3] = np.linspace(0, 255, px.shape[1]).astype(np.uint8)[None, :]
    out = aplicar(px, exposure=50, saturation=40, clarity=30, vignette=40, grain=30, blur=10)
    assert np.array_equal(out[..., 3], px[..., 3])


def test_no_modifica_la_imagen_de_entrada():
    px = ruido()
    copia = px.copy()
    aplicar(px, exposure=40, contrast=30, blur=20, saturation=-50)
    assert np.array_equal(px, copia)


def test_exposicion_sube_y_baja_el_brillo():
    px = solido(8, 8, (100, 100, 100, 255))
    assert lum(aplicar(px, exposure=100)).mean() > lum(px).mean() + 20
    assert lum(aplicar(px, exposure=-100)).mean() < lum(px).mean() - 20


def test_exposicion_100_duplica_la_luz_lineal():
    px = solido(2, 2, (100, 100, 100, 255))
    out = aplicar(px, exposure=100)
    lin = lambda v: ((v / 255 + 0.055) / 1.055) ** 2.4
    assert lin(out[0, 0, 0]) / lin(100) == pytest.approx(2.0, rel=0.06)


def test_contraste_abre_o_cierra_el_histograma():
    px = degradado()
    assert aplicar(px, contrast=60)[..., 0].std() > px[..., 0].std()
    assert aplicar(px, contrast=-60)[..., 0].std() < px[..., 0].std()


def test_contraste_deja_el_gris_medio_casi_igual():
    px = solido(4, 4, (128, 128, 128, 255))
    assert abs(int(aplicar(px, contrast=80)[0, 0, 0]) - 128) <= 3


def test_altas_luces_actuan_en_lo_claro_y_no_en_lo_oscuro():
    px = degradado()
    out = aplicar(px, highlights=-80)
    claro, oscuro = px[..., 0] > 200, px[..., 0] < 40
    assert (out[..., 0][claro].astype(int) - px[..., 0][claro]).mean() < -10
    assert abs((out[..., 0][oscuro].astype(int) - px[..., 0][oscuro]).mean()) < 3
    assert (aplicar(px, highlights=80)[..., 0][claro].astype(int) - px[..., 0][claro]).mean() > 0


def test_sombras_actuan_en_lo_oscuro_y_no_en_lo_claro():
    px = degradado()
    out = aplicar(px, shadows=80)
    claro, oscuro = px[..., 0] > 220, px[..., 0] < 60
    assert (out[..., 0][oscuro].astype(int) - px[..., 0][oscuro]).mean() > 8
    assert abs((out[..., 0][claro].astype(int) - px[..., 0][claro]).mean()) < 3
    assert (aplicar(px, shadows=-80)[..., 0][oscuro].astype(int) - px[..., 0][oscuro]).mean() < 0


def test_blancos_y_negros_mueven_los_extremos():
    px = degradado()
    assert aplicar(px, blacks=100)[0, 0, 0] > px[0, 0, 0] + 10
    assert aplicar(px, whites=-100)[0, -1, 0] < 255 - 30
    assert aplicar(px, whites=100)[0, 40, 0] >= px[0, 40, 0]
    assert aplicar(px, blacks=-100)[0, 8, 0] <= px[0, 8, 0]


def test_temperatura_calienta_y_enfria():
    px = solido(4, 4, (120, 120, 120, 255))
    c = aplicar(px, temperature=60)[0, 0]
    f = aplicar(px, temperature=-60)[0, 0]
    assert c[0] > c[2] and f[2] > f[0]


def test_tinte_positivo_es_magenta_y_negativo_verde():
    px = solido(4, 4, (120, 120, 120, 255))
    m = aplicar(px, tint=60)[0, 0]
    v = aplicar(px, tint=-60)[0, 0]
    assert m[1] < m[0] and v[1] > v[0]


def test_saturacion_menos_100_deja_gris_y_mas_sube_el_color():
    px = colorido()
    gris = aplicar(px, saturation=-100)
    assert np.abs(gris[..., 0].astype(int) - gris[..., 1]).max() <= 1
    assert np.abs(gris[..., 1].astype(int) - gris[..., 2]).max() <= 1
    croma = lambda a: (a[..., :3].max(axis=2).astype(int) - a[..., :3].min(axis=2)).mean()
    assert croma(aplicar(px, saturation=50)) > croma(px) > croma(aplicar(px, saturation=-50))


def test_intensidad_sube_mas_los_colores_apagados():
    apagado = solido(2, 2, (130, 120, 120, 255))
    vivo = solido(2, 2, (250, 20, 20, 255))
    croma = lambda a: int(a[0, 0, :3].max()) - int(a[0, 0, :3].min())
    # ganancia relativa: lo apagado debe crecer mucho más (en proporción) que lo vivo
    gana_apagado = croma(aplicar(apagado, vibrance=100)) / croma(apagado) - 1
    gana_vivo = croma(aplicar(vivo, vibrance=100)) / croma(vivo) - 1
    assert gana_apagado > 0
    assert gana_apagado > gana_vivo


def test_hsl_solo_toca_su_franja():
    px = np.zeros((2, 2, 4), np.uint8)
    px[0, 0] = (60, 200, 60, 255)      # verde
    px[0, 1] = (220, 40, 40, 255)      # rojo
    px[1, 0] = (40, 40, 220, 255)      # azul
    px[1, 1] = (128, 128, 128, 255)    # gris
    out = aplicar(px, hsl={"green": (0, -100, 0)})
    croma = lambda p: int(p[:3].max()) - int(p[:3].min())
    assert croma(out[0, 0]) < croma(px[0, 0]) * 0.3
    assert np.array_equal(out[0, 1], px[0, 1]) or np.abs(out[0, 1].astype(int) - px[0, 1]).max() <= 2
    assert np.abs(out[1, 0].astype(int) - px[1, 0]).max() <= 2
    assert np.array_equal(out[1, 1], px[1, 1])


def test_hsl_tono_mueve_el_color_y_luminosidad_aclara():
    rojo = solido(2, 2, (220, 40, 40, 255))
    mov = aplicar(rojo, hsl={"red": (100, 0, 0)})[0, 0]
    assert mov[1] > 100 and mov[0] > 150            # el rojo se va hacia el amarillo
    clar = aplicar(rojo, hsl={"red": (0, 0, 100)})[0, 0]
    osc = aplicar(rojo, hsl={"red": (0, 0, -100)})[0, 0]
    assert lum(clar[None, None]).item() > lum(rojo[:1, :1]).item() > lum(osc[None, None]).item()


def test_hsl_las_franjas_se_mezclan_sin_saltos():
    # Un barrido de tonos con un cambio de saturación solo en el verde:
    # entre un tono y el siguiente el resultado no debe saltar de golpe.
    h = np.linspace(0, 1, 360, endpoint=False)
    k = (np.array([5.0, 3.0, 1.0])[None, :] + h[:, None] * 6) % 6
    rgb = 1 - np.clip(np.minimum(k, 4 - k), 0, 1)
    px = np.zeros((1, 360, 4), np.uint8)
    px[0, :, :3] = (rgb * 255).astype(np.uint8)
    px[..., 3] = 255
    out = aplicar(px, hsl={"green": (0, -100, 0)})
    salto = np.abs(np.diff(out[0, :, :3].astype(int), axis=0)).max()
    assert salto <= 12


def test_claridad_aumenta_el_contraste_local():
    # Una rampa suave con un detalle pequeño encima
    px = degradado(96, 96)
    px[40:56, 40:56, :3] = 140
    px[44:52, 44:52, :3] = 160
    base = px[44:52, 44:52, 0].astype(int).mean() - px[36:40, 36:40, 0].astype(int).mean()
    out = aplicar(px, clarity=100)
    nuevo = out[44:52, 44:52, 0].astype(int).mean() - out[36:40, 36:40, 0].astype(int).mean()
    assert abs(nuevo - base) > 1
    suave = aplicar(px, clarity=-100)
    assert suave[..., 0].astype(int).std() <= px[..., 0].astype(int).std() + 1


def test_enfoque_aumenta_el_borde_y_desenfoque_lo_baja():
    px = solido(40, 40, (60, 60, 60, 255))
    px[:, 20:, :3] = 190
    borde = lambda a: abs(int(a[20, 21, 0]) - int(a[20, 18, 0]))
    assert borde(aplicar(px, sharpen=100)) >= borde(px)
    assert aplicar(px, sharpen=100)[20, 22, 0] > 190 - 2        # se pasa un poco = halo de enfoque
    assert borde(aplicar(px, blur=60)) < borde(px)


def test_desenfoque_baja_la_varianza_del_ruido():
    px = ruido(64, 64)
    assert aplicar(px, blur=30)[..., 0].std() < px[..., 0].std() * 0.5


def test_las_cosas_espaciales_siguen_a_la_escala():
    px = ruido(64, 64)
    asimismo = aplicar(px, scale=0.02, blur=100)
    assert np.abs(asimismo[..., 0].astype(int) - px[..., 0]).max() <= 2     # a 0,02 el radio es de ~0 px
    fuerte = aplicar(px, scale=1.0, blur=100)
    assert fuerte[..., 0].std() < px[..., 0].std() * 0.2


def test_vineta_oscurece_las_esquinas_y_no_el_centro():
    px = solido(80, 60, (200, 200, 200, 255))
    out = aplicar(px, vignette=80)
    assert out[0, 0, 0] < 150
    assert abs(int(out[30, 40, 0]) - 200) <= 3
    assert out[0, 0, 0] < out[15, 20, 0] <= out[30, 40, 0]


def test_grano_es_determinista_y_cambia_la_imagen():
    px = solido(80, 60, (128, 128, 128, 255))
    a = aplicar(px, grain=60)
    b = aplicar(px, grain=60)
    assert np.array_equal(a, b)
    assert a[..., 0].std() > 2
    assert abs(float(a[..., 0].mean()) - 128) < 3


def test_grano_mas_fuerte_se_nota_mas():
    px = solido(80, 60, (128, 128, 128, 255))
    assert aplicar(px, grain=100)[..., 0].std() > aplicar(px, grain=20)[..., 0].std()


def test_curva_pasa_por_sus_puntos():
    px = degradado(256, 4)
    out = aplicar(px, curve=[(0, 0), (0.5, 0.75), (1, 1)])
    assert abs(int(out[0, 128, 0]) - 191) <= 2
    assert out[0, 0, 0] == 0 and out[0, 255, 0] == 255


def test_curva_es_monotona_y_sin_sobretiros():
    # Puntos que obligarían a un spline normal a pasarse de 0…1
    puntos = [(0, 0.0), (0.1, 0.0), (0.2, 0.9), (0.3, 0.95), (0.9, 1.0), (1, 1.0)]
    lut = curve_lut(puntos, 1024)
    assert np.all(np.diff(lut) >= -1e-6)
    assert lut.min() >= 0.0 and lut.max() <= 1.0
    out = aplicar(degradado(256, 2), curve=puntos)[0, :, 0].astype(int)
    assert np.all(np.diff(out) >= 0)


def test_curva_acepta_puntos_desordenados_o_repetidos():
    out = aplicar(degradado(64, 2), curve=[(1, 1), (0.5, 0.2), (0.5, 0.3), (0, 0), (2.0, 5.0)])
    assert out.shape == (2, 64, 4)


def test_pchip_no_se_pasa_entre_puntos():
    xs, ys = [0, 0.3, 0.6, 1.0], [0.0, 0.05, 0.9, 1.0]
    v = pchip(xs, ys, np.linspace(0, 1, 500))
    assert v.min() >= 0 and v.max() <= 1
    assert np.all(np.diff(v) >= -1e-9)


def test_imagen_de_un_pixel_con_todos_los_ajustes():
    px = solido(1, 1, (30, 90, 200, 255))
    out = aplicar(px, exposure=30, contrast=20, highlights=10, shadows=10, whites=5, blacks=5,
                  temperature=10, tint=5, vibrance=20, saturation=10, clarity=30, sharpen=40,
                  blur=30, vignette=40, grain=20, curve=[(0, 0.1), (1, 0.9)],
                  hsl={"blue": (10, 10, 10)})
    assert out.shape == (1, 1, 4)


def test_imagen_de_una_fila_o_columna():
    for forma in ((1, 50), (50, 1)):
        px = ruido(forma[1], forma[0])
        out = aplicar(px, clarity=50, sharpen=50, blur=40, vignette=30, grain=20)
        assert out.shape == px.shape


def test_escala_extrema_no_truena():
    px = ruido(32, 32)
    for s in (0.0001, 0.01, 8.0):
        assert aplicar(px, scale=s, blur=50, sharpen=50, clarity=50).shape == px.shape


def test_valores_fuera_de_rango_se_recortan_sin_error():
    px = colorido()
    out = aplicar(px, exposure=900, contrast=500, saturation=900, temperature=-900, hsl={"red": (900, 900, 900)})
    assert out.dtype == np.uint8 and out.shape == px.shape
