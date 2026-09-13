"""Genera el ícono de Vortex Studio en todos los tamaños que piden los sistemas.

El ícono es el logo de la barra superior del diseño de la beta —un cuadro
blanco redondeado— sobre una loseta casi negra, con un play recortado para
que en el menú de aplicaciones se lea como editor de video.

Se dibuja con QPainter y se guarda en `src/vortex_studio/assets/`:

- `vortex-studio.svg`, el mismo dibujo en vectores;
- `vortex-studio-<tamaño>.png` para Linux (el menú de aplicaciones);
- `vortex-studio.ico` para Windows, con varios tamaños adentro.

Uso: `python empaquetado/iconos.py`. Los archivos generados se guardan en el
repo; esto solo hace falta si cambia el dibujo.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "src" / "vortex_studio" / "assets"

TAMANOS_PNG = (16, 24, 32, 48, 64, 128, 256, 512)
TAMANOS_ICO = (16, 24, 32, 48, 64, 128, 256)

FONDO = "#0b0b0c"
BORDE = "#2e2e33"
BLANCO = "#ffffff"

# Geometría en una rejilla de 512.
LOSETA = (16, 16, 480, 480, 112)
CUADRO = (136, 136, 240, 240, 56)
PLAY = ((218, 196), (318, 256), (218, 316))

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect x="{LOSETA[0]}" y="{LOSETA[1]}" width="{LOSETA[2]}" height="{LOSETA[3]}" rx="{LOSETA[4]}"
        fill="{FONDO}" stroke="{BORDE}" stroke-width="8"/>
  <rect x="{CUADRO[0]}" y="{CUADRO[1]}" width="{CUADRO[2]}" height="{CUADRO[3]}" rx="{CUADRO[4]}"
        fill="{BLANCO}"/>
  <polygon points="{' '.join(f'{x},{y}' for x, y in PLAY)}" fill="{FONDO}"
           stroke="{FONDO}" stroke-width="14" stroke-linejoin="round"/>
</svg>
"""


def dibujar(lado: int):
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

    imagen = QImage(lado, lado, QImage.Format_ARGB32)
    imagen.fill(Qt.transparent)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(lado / 512, lado / 512)

    x, y, w, h, r = LOSETA
    p.setPen(QPen(QColor(BORDE), 8))
    p.setBrush(QColor(FONDO))
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)

    x, y, w, h, r = CUADRO
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(BLANCO))
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)

    lapiz = QPen(QColor(FONDO), 14)
    lapiz.setJoinStyle(Qt.RoundJoin)
    p.setPen(lapiz)
    p.setBrush(QColor(FONDO))
    p.drawPolygon(QPolygonF([QPointF(px, py) for px, py in PLAY]))
    p.end()
    return imagen


def png_bytes(imagen) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    datos = QByteArray()
    buffer = QBuffer(datos)
    buffer.open(QIODevice.WriteOnly)
    imagen.save(buffer, "PNG")
    buffer.close()
    return bytes(datos)


def ico(imagenes: dict[int, bytes]) -> bytes:
    """Un .ico con entradas PNG adentro, que Windows acepta desde Vista.

    Se arma a mano porque el escritor de ICO de Qt guarda un solo tamaño, y
    Windows necesita varios para verse nítido en la barra y en el escritorio.
    """
    cabecera = struct.pack("<HHH", 0, 1, len(imagenes))
    directorio = b""
    cuerpo = b""
    desplazamiento = 6 + 16 * len(imagenes)
    for lado, datos in sorted(imagenes.items()):
        medida = 0 if lado >= 256 else lado      # 0 quiere decir 256
        directorio += struct.pack("<BBBBHHII", medida, medida, 0, 0, 1, 32,
                                  len(datos), desplazamiento + len(cuerpo))
        cuerpo += datos
    return cabecera + directorio + cuerpo


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "vortex-studio.svg").write_text(SVG, encoding="utf-8")
    pngs = {}
    for lado in TAMANOS_PNG:
        datos = png_bytes(dibujar(lado))
        pngs[lado] = datos
        (DESTINO / f"vortex-studio-{lado}.png").write_bytes(datos)
    (DESTINO / "vortex-studio.ico").write_bytes(ico({t: pngs[t] for t in TAMANOS_ICO}))
    print(f"Íconos en {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
