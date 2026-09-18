"""Máscaras: dejar ver solo una parte de la capa."""

import pytest

from vortex_studio.model import Mask
from vortex_studio.ui.compositor import clear_mask_cache, mask_image


@pytest.fixture(autouse=True)
def sin_cache():
    """Cada prueba arranca sin máscaras guardadas.

    El caché es por tamaño y por valores, así que en uso normal no estorba;
    en las pruebas sí, porque dos pruebas seguidas pedirían la misma clave.
    """
    clear_mask_cache()
    yield
    clear_mask_cache()


def alfa(img, x: float, y: float) -> int:
    """La opacidad en un punto dado en fracciones de la imagen."""
    px = min(img.width() - 1, int(img.width() * x))
    py = min(img.height() - 1, int(img.height() * y))
    return img.pixelColor(px, py).alpha()


# --- el modelo ------------------------------------------------------------

def test_sin_forma_no_hay_mascara(qapp):
    assert Mask().is_off


def test_una_forma_desconocida_se_trata_como_ninguna(qapp):
    """Un proyecto más nuevo puede traer una forma que esta versión no tenga."""
    assert Mask(shape="Estrella de ocho picos").is_off


def test_la_lineal_no_usa_tamano(qapp):
    assert not Mask(shape="Lineal").uses_size
    assert Mask(shape="Círculo").uses_size
    assert Mask(shape="Rectángulo").uses_size


def test_restablecer_la_apaga(qapp):
    m = Mask(shape="Círculo", invert=True, feather=0.2)
    m.reset()
    assert m.is_off and not m.invert


# --- el mapa de opacidad --------------------------------------------------

def test_el_circulo_deja_ver_el_centro_y_tapa_las_esquinas(qapp):
    img = mask_image(120, 120, Mask(shape="Círculo", feather=0.0))
    assert alfa(img, 0.5, 0.5) > 250
    assert alfa(img, 0.02, 0.02) < 5


def test_el_rectangulo_respeta_su_ancho(qapp):
    img = mask_image(200, 100, Mask(shape="Rectángulo", width=0.4,
                                    height=1.0, feather=0.0))
    assert alfa(img, 0.50, 0.5) > 250     # dentro
    assert alfa(img, 0.05, 0.5) < 5       # fuera, a la izquierda
    assert alfa(img, 0.95, 0.5) < 5       # fuera, a la derecha


def test_la_lineal_parte_el_cuadro(qapp):
    img = mask_image(120, 120, Mask(shape="Lineal", feather=0.0))
    assert alfa(img, 0.5, 0.1) > 250      # arriba se ve
    assert alfa(img, 0.5, 0.9) < 5        # abajo no


def test_girar_la_lineal_cambia_de_lado(qapp):
    img = mask_image(120, 120, Mask(shape="Lineal", rotation=180.0, feather=0.0))
    assert alfa(img, 0.5, 0.1) < 5
    assert alfa(img, 0.5, 0.9) > 250


def test_invertir_es_cosa_del_dibujado_no_del_mapa(qapp):
    """El mapa es el mismo; lo que cambia es el modo de composición.

    Voltear los pixeles de una imagen premultiplicada da basura, así que
    invertir se resuelve con `DestinationOut` en vez de `DestinationIn`.
    """
    normal = mask_image(80, 80, Mask(shape="Círculo", feather=0.0))
    volteada = mask_image(80, 80, Mask(shape="Círculo", feather=0.0, invert=True))
    assert alfa(normal, 0.5, 0.5) == alfa(volteada, 0.5, 0.5)


def test_la_posicion_mueve_la_forma(qapp):
    img = mask_image(120, 120, Mask(shape="Círculo", x=0.2, y=0.2,
                                    width=0.3, height=0.3, feather=0.0))
    assert alfa(img, 0.2, 0.2) > 250
    assert alfa(img, 0.8, 0.8) < 5


# --- el suavizado del borde -----------------------------------------------

def test_el_suavizado_deja_un_borde_a_medias(qapp):
    img = mask_image(200, 200, Mask(shape="Círculo", width=0.5, height=0.5,
                                    feather=0.12))
    medios = [alfa(img, 0.25 + i / 400, 0.5) for i in range(60)]
    assert any(40 < v < 215 for v in medios), "el borde salió duro"


def test_sin_suavizado_el_borde_es_duro(qapp):
    img = mask_image(200, 200, Mask(shape="Círculo", width=0.5, height=0.5,
                                    feather=0.0))
    fila = [alfa(img, i / 200, 0.5) for i in range(200)]
    a_medias = [v for v in fila if 40 < v < 215]
    assert len(a_medias) <= 4       # solo el antialias de la orilla


def test_el_suavizado_no_lava_las_orillas_del_cuadro(qapp):
    """Era el detalle fino: el desenfoque también difuminaba los bordes.

    Una máscara lineal que tapa media pantalla salía con los cuatro bordes
    lavados en vez de solo la línea del corte. Se arregla dibujando la
    forma en un lienzo más grande y recortando después.
    """
    img = mask_image(160, 160, Mask(shape="Lineal", feather=0.15))
    assert alfa(img, 0.5, 0.005) > 250      # el borde de arriba, entero
    assert alfa(img, 0.01, 0.05) > 250      # la esquina de arriba, también
    assert alfa(img, 0.99, 0.05) > 250


def test_el_cache_no_devuelve_una_mascara_vieja(qapp):
    """Mueves la máscara y tiene que cambiar, no quedarse pegada."""
    primera = mask_image(100, 100, Mask(shape="Círculo", x=0.2, y=0.2,
                                        width=0.3, height=0.3, feather=0.0))
    segunda = mask_image(100, 100, Mask(shape="Círculo", x=0.8, y=0.8,
                                        width=0.3, height=0.3, feather=0.0))
    assert alfa(primera, 0.2, 0.2) > 250
    assert alfa(segunda, 0.2, 0.2) < 5


def test_la_misma_mascara_se_reutiliza(qapp):
    """Recalcularla cada cuadro sería un desenfoque por cuadro."""
    m = Mask(shape="Círculo", feather=0.05)
    assert mask_image(100, 100, m) is mask_image(100, 100, m)


# --- llega a los pixeles del cuadro ---------------------------------------

def gris_medio(ventana, media, **mascara):
    from vortex_studio.model import Mask as M

    ventana._place_video(media["gris"])
    clip = ventana.sequence.top_clip_at(0.5)
    clip.mask = M(**mascara)
    ventana._seek(0.5)
    return ventana.preview.current_image()


def luz(img, x: float, y: float) -> int:
    px = min(img.width() - 1, int(img.width() * x))
    py = min(img.height() - 1, int(img.height() * y))
    return sum(img.pixelColor(px, py).getRgb()[:3])


def test_la_mascara_recorta_el_cuadro_de_verdad(ventana, media):
    img = gris_medio(ventana, media, shape="Círculo", width=0.5,
                     height=0.5, feather=0.0)
    assert luz(img, 0.5, 0.5) > 300         # el centro sigue gris
    assert luz(img, 0.02, 0.02) < 30        # la esquina quedó negra


def test_invertida_tapa_lo_de_dentro(ventana, media):
    img = gris_medio(ventana, media, shape="Círculo", width=0.5,
                     height=0.5, feather=0.0, invert=True)
    assert luz(img, 0.5, 0.5) < 30
    assert luz(img, 0.02, 0.02) > 300


def test_sin_mascara_el_cuadro_va_entero(ventana, media):
    img = gris_medio(ventana, media)
    assert luz(img, 0.5, 0.5) > 300
    assert luz(img, 0.02, 0.02) > 300


def test_sobrevive_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(media["mudo"])
    clip = ventana.sequence.top_clip_at(1.0)
    clip.mask.shape = "Círculo"
    clip.mask.feather = 0.11
    clip.mask.invert = True

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.video_tracks()[-1].clips[0]

    assert vuelto.mask.shape == "Círculo"
    assert vuelto.mask.feather == pytest.approx(0.11)
    assert vuelto.mask.invert is True
    assert not vuelto.mask.is_off


def test_el_preview_se_pinta_con_mascara(ventana, media):
    """El preview dibuja sobre el widget, no sobre un lienzo del tamaño de
    la secuencia. Es otro camino de código y hay que pisarlo: aquí es donde
    un rectángulo mal medido se vería como un recorte torcido."""
    from PySide6.QtGui import QPixmap

    ventana._place_video(media["gris"])
    clip = ventana.sequence.top_clip_at(0.5)
    clip.mask.shape = "Círculo"
    clip.mask.feather = 0.06
    ventana._seek(0.5)
    # En una máquina lenta el cuadro puede no haber llegado: sin esperarlo se
    # mide el mensaje vacío del monitor y no la imagen.
    ventana._settle_preview()
    ventana._render(0.5)

    lienzo = QPixmap(ventana.preview.size())
    ventana.preview.render(lienzo)              # dispara paintEvent de verdad
    assert not lienzo.isNull()

    img = lienzo.toImage()
    centro = img.pixelColor(img.width() // 2, img.height() // 2)
    assert sum(centro.getRgb()[:3]) > 200       # el centro se sigue viendo
