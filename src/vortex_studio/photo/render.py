"""El compositor: convierte un `Document` en píxeles.

Cómo se mantiene rápido:
- **Caché por capa.** Lo caro de una capa (remuestrear su imagen, ajustes,
  filtro, máscara, texto, forma) se guarda con una llave que es la firma de la
  capa **sin su posición, giro, opacidad ni modo de fusión**: arrastrar,
  girar o cambiar la opacidad de una capa no recalcula nada, solo la vuelve a
  colocar. Cambiar un ajuste solo recalcula esa capa. La caché es LRU y está
  limitada en bytes.
- **Escala primero.** La imagen de origen se reduce al tamaño con que se verá
  *antes* de ajustarla, así una foto de 24 MP ajustada a escala de vista previa
  trabaja con ~1 MP.
- **Solo lo que se ve.** Cada capa se coloca en el rectángulo del lienzo que
  toca; lo que queda fuera no se procesa.
"""

from __future__ import annotations

import json
import math
from collections import OrderedDict
from collections.abc import Collection

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter

from ._util import from_qimage, parse_color, resize_gray, resize_rgba, to_qimage
from .adjust import apply_adjustments
from .assets import AssetStore
from .blend import composite
from .document import (KIND_ADJUST, KIND_IMAGE, KIND_SHAPE, KIND_TEXT, Document, Effects,
                       Layer, layer_to_dict)
from .effects import apply_effects
from .filters import apply_filter
from .shapes import render_shape
from .text import render_text

__all__ = ["Renderer", "to_qimage", "from_qimage"]

_MAX_CACHE = 512 * 1024 * 1024


def _nbytes(v) -> int:
    if isinstance(v, np.ndarray):
        return v.nbytes
    if isinstance(v, tuple):
        return sum(_nbytes(x) for x in v)
    return 0


class Renderer:
    def __init__(self, store: AssetStore, max_cache_bytes: int = _MAX_CACHE) -> None:
        self.store = store
        self.max_cache_bytes = int(max_cache_bytes)
        self._cache: OrderedDict = OrderedDict()      # llave → (id de capa, valor, bytes)
        self._bytes = 0
        # Contadores para las pruebas y para medir: cuántas veces se rehizo
        # el contenido de una capa y cuántas se sirvió de la caché.
        self.builds = 0
        self.hits = 0

    # --- caché ----------------------------------------------------------------

    def cache_bytes(self) -> int:
        return self._bytes

    def invalidate(self, layer_id: str | None = None) -> None:
        if layer_id is None:
            self._cache.clear()
            self._bytes = 0
            return
        for k in [k for k, (lid, _, _) in self._cache.items() if lid == layer_id]:
            self._bytes -= self._cache.pop(k)[2]

    def _get(self, key):
        item = self._cache.get(key)
        if item is None:
            return None
        self._cache.move_to_end(key)
        return item

    def _put(self, key, layer_id: str, valor) -> None:
        n = _nbytes(valor)
        if key in self._cache:
            self._bytes -= self._cache.pop(key)[2]
        if n > self.max_cache_bytes:               # no cabe ni solo: no se guarda
            return
        self._cache[key] = (layer_id, valor, n)
        self._bytes += n
        while self._bytes > self.max_cache_bytes and len(self._cache) > 1:
            _, (_, _, nn) = self._cache.popitem(last=False)
            self._bytes -= nn

    # --- contenido de una capa --------------------------------------------------

    @staticmethod
    def _content_sig(layer: Layer) -> str:
        """Firma de lo que cambia los píxeles de la capa. Sin posición, giro,
        opacidad, modo, nombre, visibilidad ni efectos."""
        d = layer_to_dict(layer)
        for k in ("id", "name", "visible", "locked", "opacity", "blend", "effects"):
            d.pop(k, None)
        for k in ("cx", "cy", "rotation"):
            d["transform"].pop(k, None)
        return json.dumps(d, sort_keys=True, default=str)

    @staticmethod
    def _box(layer: Layer, scale: float) -> tuple[int, int]:
        return (max(1, int(round(layer.transform.width * scale))),
                max(1, int(round(layer.transform.height * scale))))

    def _source(self, layer: Layer, tw: int, th: int):
        """La imagen de la capa recortada y remuestreada a la caja."""
        crop = layer.crop
        key = ("src", layer.asset, tuple(crop) if crop else None, tw, th)
        item = self._get(key)
        if item is not None:
            return item[1]
        try:
            src = self.store.get(layer.asset)
        except KeyError:
            return None
        if src.ndim != 3 or src.shape[2] != 4:
            return None
        H, W = src.shape[:2]
        if crop:
            x0 = int(min(max(math.floor(crop[0]), 0), W - 1))
            y0 = int(min(max(math.floor(crop[1]), 0), H - 1))
            x1 = int(min(max(math.ceil(crop[0] + crop[2]), x0 + 1), W))
            y1 = int(min(max(math.ceil(crop[1] + crop[3]), y0 + 1), H))
            src = src[y0:y1, x0:x1]
        out = resize_rgba(src, tw, th)
        self._put(key, layer.id, out)
        return out

    def _content(self, layer: Layer, scale: float, original: bool):
        """Contenido de la capa en su caja sin girar (ya con ajustes, filtro,
        máscara y volteo), o None si no hay nada que dibujar."""
        key = ("content", self._content_sig(layer), round(scale, 6), original)
        item = self._get(key)
        if item is not None:
            self.hits += 1
            return item[1]
        self.builds += 1
        tw, th = self._box(layer, scale)
        px = None
        if layer.kind == KIND_IMAGE:
            px = self._source(layer, tw, th)
            if px is None:
                return None
            if not original:
                px = apply_filter(px, layer.filter, scale)
                px = apply_adjustments(px, layer.adjustments, scale)
        elif layer.kind == KIND_TEXT:
            px = render_text(layer, scale)
        elif layer.kind == KIND_SHAPE:
            px = render_shape(layer, scale)
        elif layer.kind == KIND_ADJUST:
            px = np.full((th, tw, 4), 255, np.uint8)       # cobertura de la capa de ajuste
        else:
            return None
        if layer.mask:
            try:
                m = self.store.get(layer.mask)
            except KeyError:
                m = None
            if m is not None:
                if m.ndim == 3:
                    m = m[..., 0]
                m = resize_gray(m, px.shape[1], px.shape[0])
                px = px.copy() if not px.flags.writeable else px
                a = (px[..., 3].astype(np.uint16) * m + 127) // 255
                px = np.concatenate([px[..., :3], a.astype(np.uint8)[..., None]], axis=2)
        if layer.transform.flip_h:
            px = px[:, ::-1]
        if layer.transform.flip_v:
            px = px[::-1]
        px = np.ascontiguousarray(px)
        px.setflags(write=False)
        self._put(key, layer.id, px)
        return px

    @staticmethod
    def _effects_for_box(layer: Layer) -> Effects:
        """La sombra se mide en el lienzo, pero se calcula en la caja de la
        capa, que puede estar girada: se contra-gira el desplazamiento para que
        al girar la capa la sombra siga cayendo hacia el mismo lado."""
        e = layer.effects
        rot = layer.transform.rotation % 360.0
        if not e.shadow.enabled or abs(rot) < 1e-9:
            return e
        a = math.radians(-rot)
        dx, dy = e.shadow.dx, e.shadow.dy
        from dataclasses import replace
        sombra = replace(e.shadow, dx=dx * math.cos(a) - dy * math.sin(a),
                         dy=dx * math.sin(a) + dy * math.cos(a))
        return Effects(sombra, e.outline, e.glow)

    def _with_effects(self, layer: Layer, content: np.ndarray, scale: float, original: bool):
        efectos = self._effects_for_box(layer)
        if efectos.is_off() or layer.kind == KIND_ADJUST:
            return content, 0, 0
        key = ("fx", self._content_sig(layer), round(scale, 6), original,
               json.dumps(layer_to_dict(layer)["effects"], sort_keys=True),
               round(layer.transform.rotation % 360.0, 4) if efectos.shadow.enabled else 0)
        item = self._get(key)
        if item is not None:
            return item[1]
        res = apply_effects(content, efectos, scale)
        self._put(key, layer.id, res)
        return res

    # --- colocación -----------------------------------------------------------------

    @staticmethod
    def _place(img: np.ndarray, ox: int, oy: int, layer: Layer, scale: float,
               W: int, H: int):
        """Coloca la imagen (con margen de efectos ox, oy) según la
        transformación de la capa. Devuelve (x, y, región RGBA) en el lienzo."""
        t = layer.transform
        bw_px, bh_px = max(1, int(round(t.width * scale))), max(1, int(round(t.height * scale)))
        cx, cy = t.cx * scale, t.cy * scale
        rot = t.rotation % 360.0
        if min(rot, 360.0 - rot) < 1e-6:
            x = int(round(cx - bw_px / 2.0)) - ox
            y = int(round(cy - bh_px / 2.0)) - oy
            return x, y, img
        # Giro: Qt con filtrado bilineal y antialias, solo en el rectángulo que cae en el lienzo.
        bw_real, bh_real = t.width * scale, t.height * scale
        sx, sy = bw_real / bw_px, bh_real / bh_px
        ih, iw = img.shape[:2]
        izq, arr = -bw_real / 2 - ox * sx, -bh_real / 2 - oy * sy
        der, aba = izq + iw * sx, arr + ih * sy
        a = math.radians(rot)
        ca, sa = math.cos(a), math.sin(a)
        xs = [cx + px * ca - py * sa for px in (izq, der) for py in (arr, aba)]
        ys = [cy + px * sa + py * ca for px in (izq, der) for py in (arr, aba)]
        x0, x1 = max(0, int(math.floor(min(xs)))), min(W, int(math.ceil(max(xs))))
        y0, y1 = max(0, int(math.floor(min(ys)))), min(H, int(math.ceil(max(ys))))
        if x1 <= x0 or y1 <= y0:
            return None
        origen = to_qimage(img).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        destino = QImage(x1 - x0, y1 - y0, QImage.Format.Format_ARGB32_Premultiplied)
        destino.fill(0)
        p = QPainter(destino)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(cx - x0, cy - y0)
        p.rotate(rot)
        p.scale(sx, sy)
        p.drawImage(QPointF(-bw_px / 2.0 - ox, -bh_px / 2.0 - oy), origen)
        p.end()
        return x0, y0, from_qimage(destino)

    def _placed(self, layer: Layer, img, ox, oy, scale, W, H, original):
        """`_place` con caché para las capas giradas (remuestrear con Qt es lo
        más caro de volver a dibujar si solo se movió otra capa)."""
        t = layer.transform
        rot = t.rotation % 360.0
        if min(rot, 360.0 - rot) < 1e-6:
            return self._place(img, ox, oy, layer, scale, W, H)
        key = ("place", self._content_sig(layer), round(scale, 6), original,
               json.dumps(layer_to_dict(layer)["effects"], sort_keys=True),
               round(t.cx, 4), round(t.cy, 4), round(rot, 4), W, H)
        item = self._get(key)
        if item is not None:
            return item[1] or None
        res = self._place(img, ox, oy, layer, scale, W, H)
        self._put(key, layer.id, (res[0], res[1], res[2]) if res else ())
        return res

    # --- API pública -----------------------------------------------------------------

    @staticmethod
    def canvas_size(doc: Document, scale: float) -> tuple[int, int]:
        return (max(1, int(round(doc.height * scale))), max(1, int(round(doc.width * scale))))

    def render(self, doc: Document, scale: float = 1.0, *, hide: Collection[str] = (),
               original: bool = False) -> np.ndarray:
        scale = max(float(scale), 1e-4)
        H, W = self.canvas_size(doc, scale)
        canvas = np.zeros((H, W, 4), np.uint8)
        if doc.background:
            r, g, b, a = parse_color(doc.background, (255, 255, 255, 255))
            canvas[...] = (r, g, b, a)
        ocultas = set(hide)
        for layer in doc.layers:
            if (not layer.visible or layer.id in ocultas or layer.opacity <= 0.0
                    or layer.transform.width <= 0 or layer.transform.height <= 0):
                continue
            if layer.kind == KIND_ADJUST:
                if not original:
                    self._apply_adjust_layer(canvas, layer, scale)
                continue
            content = self._content(layer, scale, original)
            if content is None:
                continue
            img, ox, oy = self._with_effects(layer, content, scale, original)
            colocada = self._placed(layer, img, ox, oy, scale, W, H, original)
            if colocada is None:
                continue
            x, y, reg = colocada
            composite(canvas, reg, layer.blend, min(1.0, layer.opacity), x, y)
        return canvas

    def _apply_adjust_layer(self, canvas: np.ndarray, layer: Layer, scale: float) -> None:
        """Una capa de ajuste corrige lo que hay debajo, solo donde su caja (y
        su máscara) lo permiten, con su opacidad."""
        H, W = canvas.shape[:2]
        content = self._content(layer, scale, False)
        if content is None:
            return
        colocada = self._place(content, 0, 0, layer, scale, W, H)
        if colocada is None:
            return
        x, y, cob = colocada
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + cob.shape[1]), min(H, y + cob.shape[0])
        if x1 <= x0 or y1 <= y0:
            return
        cob = cob[y0 - y:y1 - y, x0 - x:x1 - x, 3]
        if cob.max() == 0:
            return
        base = canvas[y0:y1, x0:x1]
        corr = apply_filter(base, layer.filter, scale)
        corr = apply_adjustments(corr, layer.adjustments, scale)
        if corr is base:
            return
        k = min(1.0, layer.opacity)
        if k >= 1.0 and cob.min() == 255:
            base[..., :3] = corr[..., :3]
            return
        a = (cob.astype(np.float32) * np.float32(k / 255.0))[..., None]
        b = base[..., :3].astype(np.float32)
        base[..., :3] = np.clip(b + (corr[..., :3].astype(np.float32) - b) * a + 0.5, 0, 255).astype(np.uint8)

    def render_layer(self, doc: Document, layer: Layer, scale: float = 1.0) -> np.ndarray:
        """La capa sola, con sus ajustes, filtro y máscara, en su caja sin
        girar (ancho·escala × alto·escala). Los efectos (que agrandan la
        imagen) están en `render_layer_fx`."""
        c = self._content(layer, max(float(scale), 1e-4), False)
        if c is None:
            w, h = self._box(layer, scale)
            return np.zeros((h, w, 4), np.uint8)
        return c

    def render_layer_fx(self, doc: Document, layer: Layer, scale: float = 1.0):
        """Como `render_layer` pero con sombra, contorno y brillo: devuelve
        (imagen con margen, margen izquierdo, margen superior)."""
        scale = max(float(scale), 1e-4)
        c = self.render_layer(doc, layer, scale)
        return self._with_effects(layer, c, scale, False)

    def thumbnail(self, doc: Document, max_side: int) -> np.ndarray:
        lado = max(doc.width, doc.height, 1)
        return self.render(doc, max(1, int(max_side)) / lado)
