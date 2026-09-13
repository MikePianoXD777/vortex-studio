"""Compone el cuadro final: video de fondo, imágenes encima, texto hasta arriba.

Vive aparte porque lo usan dos cosas con necesidades distintas: el preview,
que dibuja sobre el widget al tamaño que tenga la ventana, y la exportación,
que dibuja sobre un lienzo del tamaño real de la secuencia.

Tener una sola implementación es lo que garantiza que lo exportado se vea
igual que lo que viste al editar. Si fueran dos, tarde o temprano un
subtítulo saldría en otro lugar en el archivo final.

Aquí es también donde se traduce el modelo a Qt: los nombres de los modos de
fusión a modos de composición, y las máscaras a mapas de opacidad. El modelo
sigue sin saber que Qt existe.
"""

from __future__ import annotations

from typing import NamedTuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen

from vortex_studio.media import Frame
from vortex_studio.model import ImageOverlay, Mask, Title
from vortex_studio.model.animation import AnimState, anim_state, visible_text
from vortex_studio.model.blend import NORMAL, is_normal
from vortex_studio.model.transform import FILL, FIT, STRETCH

OUTLINE = QColor(0, 0, 0, 235)
CAPTION_BOX = QColor(0, 0, 0, 150)

ALIGN_OFFSET = {
    "izquierda": 0.0,
    "centro": 0.5,
    "derecha": 1.0,
}

# Nombre del modelo -> modo de composición de Qt. Qt los trae de fábrica, así
# que un modo de fusión no cuesta más que un dibujo normal: el trabajo lo
# hace el mismo código en C++ que ya pinta todo lo demás.
BLEND_MODES = {
    "Multiplicar": QPainter.CompositionMode_Multiply,
    "Oscurecer": QPainter.CompositionMode_Darken,
    "Subexponer": QPainter.CompositionMode_ColorBurn,
    "Trama": QPainter.CompositionMode_Screen,
    "Aclarar": QPainter.CompositionMode_Lighten,
    "Sobreexponer": QPainter.CompositionMode_ColorDodge,
    "Sumar": QPainter.CompositionMode_Plus,
    "Superponer": QPainter.CompositionMode_Overlay,
    "Luz fuerte": QPainter.CompositionMode_HardLight,
    "Luz suave": QPainter.CompositionMode_SoftLight,
    "Diferencia": QPainter.CompositionMode_Difference,
    "Exclusión": QPainter.CompositionMode_Exclusion,
}

MASK_CACHE_LIMIT = 12
_mask_cache: dict[tuple, QImage] = {}


class Layer(NamedTuple):
    """Una capa de video lista para pintar.

    Es una tupla con nombres a propósito: el código que ya existía armaba
    capas como tuplas de dos o tres elementos, y así sigue funcionando sin
    tocarlo.
    """

    frame: Frame | None
    alpha: float = 1.0
    values: dict | None = None
    blend: str = NORMAL
    mask: Mask | None = None
    fill: str | None = None       # color liso en vez de cuadro (fundido a color)
    framing: dict | None = None   # encuadre, recorte y ancla; ver `framing_of`


def framing_of(transform) -> dict:
    """Lo que dice dónde cae la imagen, sacado del `Transform` del clip.

    Se copia a un diccionario y no se pasa el objeto: la exportación en
    segundo plano pinta mientras el usuario sigue editando el original.
    """
    return {
        "fit": transform.fit,
        "crop": transform.crop,
        "anchor": (transform.anchor_x, transform.anchor_y),
    }


def frame_to_image(frame: Frame) -> QImage:
    """Envuelve los bytes del cuadro sin copiarlos."""
    formato = QImage.Format_RGBA8888 if getattr(frame, "alpha", False) else QImage.Format_RGB888
    return QImage(frame.data, frame.width, frame.height, frame.stride, formato)


# --- máscaras -------------------------------------------------------------

def mask_image(width: int, height: int, mask: Mask) -> QImage:
    """Mapa de opacidad del tamaño pedido: opaco donde la capa se ve.

    El suavizado del borde se hace **encogiendo y volviendo a estirar** la
    imagen. Suena a truco pero es exactamente un desenfoque de caja, lo hace
    Qt en C++ y sale gratis; el filtro `boxblur` de FFmpeg, que sería la
    otra opción, no viene en las ruedas de PyAV.

    La forma se dibuja sobre un lienzo más grande y luego se recorta. Sin
    ese margen, el desenfoque también difumina las orillas del cuadro: una
    máscara lineal que tapa media pantalla salía con los cuatro bordes
    lavados en vez de solo la línea del corte.
    """
    clave = (width, height, mask.shape, round(mask.x, 4), round(mask.y, 4),
             round(mask.width, 4), round(mask.height, 4),
             round(mask.rotation, 2), round(mask.feather, 4))
    listo = _mask_cache.get(clave)
    if listo is not None:
        return listo

    radio = max(0.0, mask.feather) * height
    margen = int(radio * 2) + 2

    lienzo = QImage(width + margen * 2, height + margen * 2,
                    QImage.Format_ARGB32_Premultiplied)
    lienzo.fill(Qt.transparent)

    painter = QPainter(lienzo)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    painter.translate(margen + width * mask.x, margen + height * mask.y)
    painter.rotate(mask.rotation)
    _draw_shape(painter, width, height, mask)
    painter.end()

    if radio >= 1.0:
        lienzo = _soften(lienzo, radio)

    recorte = lienzo.copy(margen, margen, width, height)

    if len(_mask_cache) >= MASK_CACHE_LIMIT:
        _mask_cache.clear()
    _mask_cache[clave] = recorte
    return recorte


def _draw_shape(painter: QPainter, width: int, height: int, mask: Mask) -> None:
    """La forma, centrada en el origen y ya girada por quien llama."""
    if mask.shape == "Lineal":
        # Un corte recto: se tapa todo lo que quede de un lado de la línea.
        # El rectángulo se hace más grande que la diagonal del cuadro para
        # que su propio borde nunca entre en escena al girarlo.
        largo = (width * width + height * height) ** 0.5 * 1.5
        painter.drawRect(QRectF(-largo, -largo, largo * 2, largo))
        return

    medio_ancho = width * max(0.0, mask.width) / 2
    medio_alto = height * max(0.0, mask.height) / 2
    caja = QRectF(-medio_ancho, -medio_alto, medio_ancho * 2, medio_alto * 2)

    if mask.shape == "Círculo":
        painter.drawEllipse(caja)
    else:
        painter.drawRect(caja)


def _soften(image: QImage, radio: float) -> QImage:
    """Desenfoque de caja hecho con dos escalados suaves."""
    ancho, alto = image.width(), image.height()
    chico_w = max(1, int(ancho / radio))
    chico_h = max(1, int(alto / radio))
    chico = image.scaled(chico_w, chico_h, Qt.IgnoreAspectRatio,
                         Qt.SmoothTransformation)
    return chico.scaled(ancho, alto, Qt.IgnoreAspectRatio,
                        Qt.SmoothTransformation)


def clear_mask_cache() -> None:
    """Tira las máscaras guardadas. Se usa al cambiar de proyecto."""
    _mask_cache.clear()


def _apply_mask(painter: QPainter, width: int, height: int, mask: Mask) -> None:
    """Recorta lo ya dibujado con la máscara.

    `DestinationIn` conserva el destino donde la máscara es opaca;
    `DestinationOut` hace lo contrario. Por eso invertir una máscara no
    necesita voltear pixeles: es el otro modo de composición y ya.
    """
    painter.setCompositionMode(
        QPainter.CompositionMode_DestinationOut if mask.invert
        else QPainter.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, mask_image(width, height, mask))
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


# --- capas de video -------------------------------------------------------

def _place(painter: QPainter, target: QRectF, valores: dict | None,
           anchor: tuple[float, float] = (0.0, 0.0)) -> None:
    """Aplica desplazamiento, tamaño y giro alrededor del punto de anclaje.

    El ancla va por omisión en el centro del cuadro, que es lo que uno
    espera al rotar algo. Movida a una esquina, la imagen crece y gira
    desde esa esquina, y el desplazamiento sigue siendo el mismo: el ancla
    no mueve la imagen por sí sola.
    """
    if not valores:
        return
    pivote_x = target.center().x() + target.width() * anchor[0]
    pivote_y = target.center().y() + target.height() * anchor[1]
    painter.translate(pivote_x + target.width() * valores.get("x", 0.0),
                      pivote_y + target.height() * valores.get("y", 0.0))
    painter.rotate(valores.get("rotation", 0.0))
    escala = max(0.01, valores.get("scale", 1.0))
    painter.scale(escala, escala)
    painter.translate(-pivote_x, -pivote_y)


def fit_rect(target: QRectF, width: int, height: int, mode: str = FIT) -> QRectF:
    """Dónde cae un material de `width` × `height` dentro del cuadro.

    - **Ajustar**: entero y centrado; si la proporción no coincide queda
      negro a los lados o arriba y abajo;
    - **Rellenar**: centrado y cubriendo todo; lo que sobra se sale del
      cuadro, que es como se hace un vertical a partir de un horizontal;
    - **Estirar**: llena deformando.

    Antes todo se estiraba, y un video horizontal en una secuencia vertical
    salía con la gente flaca y alargada.
    """
    if mode == STRETCH or width <= 0 or height <= 0 or target.height() <= 0:
        return QRectF(target)

    material = width / height
    cuadro = target.width() / target.height()
    if abs(material - cuadro) < 1e-6:
        return QRectF(target)

    cubre = mode == FILL
    if (material > cuadro) != cubre:
        ancho, alto = target.width(), target.width() / material
    else:
        ancho, alto = target.height() * material, target.height()
    return QRectF(target.center().x() - ancho / 2, target.center().y() - alto / 2,
                  ancho, alto)


def _draw_frame(painter: QPainter, target: QRectF, frame: Frame,
                valores: dict | None, framing: dict | None) -> None:
    """Pinta un cuadro con su encuadre, su recorte y su transformación.

    El recorte se hace pintando solo un pedazo de la imagen en el pedazo
    correspondiente del destino: nada se copia ni se escala dos veces.
    """
    framing = framing or {}
    destino = fit_rect(target, frame.width, frame.height, framing.get("fit", FIT))
    izquierda, arriba, derecha, abajo = framing.get("crop", (0.0, 0.0, 0.0, 0.0))

    fuente = QRectF(frame.width * izquierda, frame.height * arriba,
                    frame.width * (1.0 - izquierda - derecha),
                    frame.height * (1.0 - arriba - abajo))
    pedazo = QRectF(destino.left() + destino.width() * izquierda,
                    destino.top() + destino.height() * arriba,
                    destino.width() * (1.0 - izquierda - derecha),
                    destino.height() * (1.0 - arriba - abajo))
    if fuente.width() <= 0 or fuente.height() <= 0:
        return

    _place(painter, target, valores, framing.get("anchor", (0.0, 0.0)))
    painter.drawImage(pedazo, frame_to_image(frame), fuente)


def draw_layers(painter: QPainter, target: QRectF, layers: list) -> None:
    """Pinta las capas de video de abajo hacia arriba.

    Normalmente hay una sola. Durante una transición cruzada hay dos: la que
    sale con opacidad decreciente y la que entra encima con la creciente. Y
    con material en V1 y V2 hay una por pista, que es lo que permite el
    cuadro dentro del cuadro.

    Cada capa puede traer su transformación, su modo de fusión y su máscara.
    """
    for capa in layers:
        frame, alpha = capa[0], capa[1]
        valores = capa[2] if len(capa) > 2 else None
        blend = capa[3] if len(capa) > 3 else NORMAL
        mask = capa[4] if len(capa) > 4 else None
        fill = capa[5] if len(capa) > 5 else None
        framing = capa[6] if len(capa) > 6 else None

        if fill is not None:
            if alpha > 0:
                painter.save()
                painter.setOpacity(max(0.0, min(1.0, alpha)))
                painter.fillRect(target, QColor(fill))
                painter.restore()
            continue

        if frame is None or alpha <= 0:
            continue

        opacidad = alpha * (valores.get("opacity", 1.0) if valores else 1.0)
        if opacidad <= 0:
            continue

        painter.save()
        # Nada se pinta fuera del cuadro. En el preview el cuadro es un
        # pedazo del widget, y un clip en Rellenar o crecido se saldría
        # sobre las franjas negras de alrededor.
        painter.setClipRect(target, Qt.IntersectClip)
        painter.setOpacity(max(0.0, min(1.0, opacidad)))
        if not is_normal(blend):
            painter.setCompositionMode(BLEND_MODES[blend])

        if mask is not None and not mask.is_off:
            painter.drawImage(target, _masked_layer(target, frame, valores, mask, framing))
        else:
            _draw_frame(painter, target, frame, valores, framing)

        painter.restore()

    painter.setOpacity(1.0)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


def _masked_layer(target: QRectF, frame: Frame,
                  valores: dict | None, mask: Mask,
                  framing: dict | None = None) -> QImage:
    """La capa ya transformada y recortada, en una imagen aparte.

    Hay que pasar por una imagen intermedia porque la máscara se mide sobre
    el cuadro de salida, no sobre la capa: el usuario la coloca mirando el
    preview, como en CapCut. Si se midiera sobre la capa —como en After
    Effects— la máscara se movería junto con el clip al animarlo, y eso es
    justo lo contrario de lo que uno quiere al tapar algo que está quieto.
    """
    ancho = max(1, round(target.width()))
    alto = max(1, round(target.height()))

    capa = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
    capa.fill(Qt.transparent)

    dentro = QRectF(0, 0, ancho, alto)
    painter = QPainter(capa)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.save()
    _draw_frame(painter, dentro, frame, valores, framing)
    painter.restore()
    _apply_mask(painter, ancho, alto, mask)
    painter.end()

    return capa


# --- imágenes encima ------------------------------------------------------

def draw_overlay(painter: QPainter, target: QRectF, overlay: ImageOverlay,
                 image: QImage, alpha: float = 1.0,
                 t: float | None = None) -> None:
    if image.isNull() or alpha <= 0:
        return

    estado = anim_state(overlay, t) if t is not None else AnimState()
    if estado.opacity <= 0:
        return

    width = target.width() * overlay.scale * estado.scale
    height = width * (image.height() / image.width())
    rect = QRectF(
        target.left() + target.width() * (overlay.x + estado.dx) - width / 2,
        target.top() + target.height() * (overlay.y + estado.dy) - height / 2,
        width, height)

    mask = getattr(overlay, "mask", None)
    blend = getattr(overlay, "blend", NORMAL)

    painter.save()
    painter.setOpacity(max(0.0, min(1.0, overlay.opacity * alpha * estado.opacity)))
    if not is_normal(blend):
        painter.setCompositionMode(BLEND_MODES[blend])

    if mask is not None and not mask.is_off:
        ancho = max(1, round(target.width()))
        alto = max(1, round(target.height()))
        capa = QImage(ancho, alto, QImage.Format_ARGB32_Premultiplied)
        capa.fill(Qt.transparent)
        interno = QPainter(capa)
        interno.setRenderHint(QPainter.SmoothPixmapTransform)
        interno.drawImage(rect.translated(-target.left(), -target.top()), image)
        _apply_mask(interno, ancho, alto, mask)
        interno.end()
        painter.drawImage(target, capa)
    else:
        painter.drawImage(rect, image)

    painter.restore()
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


# --- texto ----------------------------------------------------------------

def draw_title(painter: QPainter, target: QRectF, title: Title,
               alpha: float = 1.0, t: float | None = None) -> None:
    """Dibuja el título, con su animación de entrada y de salida.

    La animación se calcula en el modelo (`model/animation.py`) y aquí solo
    se pinta: así el efecto se puede probar sin abrir una ventana, y el
    preview y la exportación aplican exactamente el mismo movimiento.
    """
    if not title.text.strip() or alpha <= 0:
        return

    estado = anim_state(title, t) if t is not None else AnimState()
    if estado.opacity <= 0 or estado.chars <= 0:
        return

    painter.save()
    painter.setOpacity(max(0.0, min(1.0, alpha * estado.opacity)))
    try:
        _draw_title_body(painter, target, title, estado)
    finally:
        painter.restore()


def _draw_title_body(painter: QPainter, target: QRectF, title: Title,
                     estado: AnimState) -> None:

    font = QFont(title.font) if title.font else QFont()
    font.setPixelSize(max(8, int(target.height() * title.size * estado.scale)))
    font.setBold(title.bold)
    font.setItalic(title.italic)

    metrics = QFontMetricsF(font)
    texto = visible_text(title.text, estado.chars)
    lines = texto.splitlines() or [""]
    line_height = metrics.height()
    block_height = line_height * len(lines)

    # El ancho se mide sobre el texto COMPLETO, no sobre el que ya se
    # escribió: si se midiera sobre el visible, un texto centrado se iría
    # acomodando letra por letra y se vería como un temblor.
    completo = title.text.splitlines() or [""]
    widest = max(metrics.horizontalAdvance(line) for line in completo)

    anchor_x = target.left() + target.width() * (title.x + estado.dx)
    anchor_y = target.top() + target.height() * (title.y + estado.dy)
    left = anchor_x - widest * ALIGN_OFFSET.get(title.align, 0.5)
    block = QRectF(left, anchor_y - block_height / 2, widest, block_height)

    if title.background:
        pad = line_height * 0.22
        painter.setPen(Qt.NoPen)
        painter.setBrush(CAPTION_BOX)
        painter.drawRoundedRect(block.adjusted(-pad, -pad / 2, pad, pad / 2), 4, 4)

    if title.shadow:
        _draw_shadow(painter, block, lines, font, metrics, title)

    painter.setFont(font)
    _draw_lines(painter, block, lines, font, metrics, title,
                QColor(title.color), QColor(title.outline_color))


def _draw_lines(painter: QPainter, block: QRectF, lines: list[str], font: QFont,
                metrics: QFontMetricsF, title: Title,
                relleno: QColor, contorno: QColor) -> None:
    line_height = metrics.height()
    for index, line in enumerate(lines):
        row = QRectF(block.left(), block.top() + index * line_height,
                     block.width(), line_height)
        _draw_line(painter, row, line, font, metrics, title, relleno, contorno)


def _draw_shadow(painter: QPainter, block: QRectF, lines: list[str], font: QFont,
                 metrics: QFontMetricsF, title: Title) -> None:
    """La sombra es el mismo texto, del color de la sombra, desplazado.

    Con desenfoque se pinta en una imagen aparte y se suaviza con el mismo
    truco de las máscaras —encoger y volver a estirar—; sin él se pinta
    directo, que es gratis.
    """
    px = font.pixelSize()
    distancia = title.shadow_distance * px
    color = QColor(title.shadow_color)

    painter.save()
    painter.setOpacity(painter.opacity() * max(0.0, min(1.0, title.shadow_opacity)))
    radio = max(0.0, title.shadow_blur) * px
    if radio < 1.0:
        painter.translate(distancia, distancia)
        painter.setFont(font)
        _draw_lines(painter, block, lines, font, metrics, title, color, color)
        painter.restore()
        return

    margen = int(radio * 2 + px * title.outline_width * 2) + 2
    imagen = QImage(int(block.width()) + margen * 2, int(block.height()) + margen * 2,
                    QImage.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.transparent)
    interno = QPainter(imagen)
    interno.setRenderHint(QPainter.Antialiasing)
    interno.setRenderHint(QPainter.TextAntialiasing)
    interno.translate(margen - block.left(), margen - block.top())
    interno.setFont(font)
    _draw_lines(interno, block, lines, font, metrics, title, color, color)
    interno.end()

    imagen = _soften(imagen, radio)
    painter.drawImage(QPointF(block.left() - margen + distancia,
                              block.top() - margen + distancia), imagen)
    painter.restore()


def _draw_line(painter: QPainter, row: QRectF, line: str, font: QFont,
               metrics: QFontMetricsF, title: Title,
               relleno: QColor | None = None, contorno: QColor | None = None) -> None:
    """El contorno se traza sobre el contorno real de la letra.

    Repetir el texto desplazado en ocho direcciones deja bordes sucios en
    las diagonales; trazar el path queda parejo en todas.
    """
    x = row.left() + (row.width() - metrics.horizontalAdvance(line)) * \
        ALIGN_OFFSET.get(title.align, 0.5)
    baseline = row.top() + metrics.ascent()

    if title.outline and title.outline_width > 0:
        path = QPainterPath()
        path.addText(QPointF(x, baseline), font, line)
        width = max(1.0, font.pixelSize() * title.outline_width)
        painter.setPen(QPen(contorno if contorno is not None else OUTLINE,
                            width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    painter.setPen(relleno if relleno is not None else QColor(title.color))
    painter.drawText(QPointF(x, baseline), line)


# --- el cuadro completo ---------------------------------------------------

def compose(width: int, height: int, layers: list,
            overlays: list[tuple[ImageOverlay, QImage]],
            titles: list[Title], t: float | None = None) -> QImage:
    """Dibuja el cuadro completo sobre un lienzo nuevo del tamaño pedido.

    Con `t`, cada elemento aplica su propio fundido y su animación.
    """
    canvas = QImage(width, height, QImage.Format_RGB888)
    canvas.fill(Qt.black)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    target = QRectF(0, 0, width, height)

    draw_layers(painter, target, layers)

    for overlay, image in overlays:
        draw_overlay(painter, target, overlay, image,
                     overlay.fade_at(t) if t is not None else 1.0, t)
    for title in titles:
        draw_title(painter, target, title,
                   title.fade_at(t) if t is not None else 1.0, t)
    painter.end()

    return canvas
