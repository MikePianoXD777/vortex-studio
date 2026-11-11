"""La sesión de Vortex Photo: el diseño abierto y todo lo que se le hace.

Aquí vive la lógica (agregar, mover, ordenar, copiar, deshacer, pintar…) sin
ningún widget, para que el lienzo, los paneles y las pruebas hablen con la
misma pieza. Cada cambio que el usuario ve como «una cosa» termina en
`commit(etiqueta)`, que es lo único que escribe en el historial; mientras algo
se arrastra se llama a `touch()`, que solo avisa que hay que volver a dibujar.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication, QImage

from vortex_studio.photo import io as photo_io
from vortex_studio.photo import paint, templates
from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import (
    KIND_ADJUST,
    KIND_IMAGE,
    KIND_SHAPE,
    KIND_TEXT,
    Document,
    Layer,
    Transform,
    layer_from_dict,
    document_to_dict,
    layer_to_dict,
    new_id,
)
from vortex_studio.photo.history import PhotoHistory
from vortex_studio.photo._util import resize_gray
from vortex_studio.photo.render import Renderer, from_qimage
from vortex_studio.photo.text import text_height
from vortex_studio.ui.photo import aniso
from vortex_studio.ui.photo import crop as cropmod
from vortex_studio.ui.photo import geometry as geo

SHAPE_NAMES = {
    "rect": "Rectángulo", "ellipse": "Círculo", "triangle": "Triángulo", "star": "Estrella",
    "line": "Línea", "arrow": "Flecha", "heart": "Corazón",
}
DRAWING_NAME = "Dibujo"
PASTE_OFFSET = 24
MAX_PAINT_SIDE = 4096          # tope del lado de una capa de dibujo nueva

TOOLS = ("move", "brush", "erase", "mask_paint", "mask_erase", "wand", "clone")


class PhotoSession(QObject):
    live = Signal()                 # algo cambió: hay que volver a dibujar
    committed = Signal(str)         # se cerró un paso del historial
    selection_changed = Signal()
    document_replaced = Signal()    # diseño nuevo o abierto
    tool_changed = Signal(str)
    message = Signal(str)           # aviso breve para la barra de estado

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.brush = paint.Brush(size=40, hardness=0.8, opacity=1.0, color="#7c5cff")
        self.tool = "move"
        self.clipboard: list[dict] = []
        self.clipboard_pixels: dict[str, np.ndarray] = {}     # id viejo → píxeles (sobreviven a otro diseño)
        self._paste_count = 0
        self.uploads: list[tuple[str, np.ndarray, str]] = []     # (nombre, miniatura RGBA, id en el almacén)
        self.wand_tolerance = 32.0
        self.wand_contiguous = True
        self.wand_keep = False          # False = la varita oculta lo que toca
        self.clone_source: tuple[float, float] | None = None
        self._reset(Document())

    # --- estado base ------------------------------------------------------

    def _reset(self, doc: Document, store: AssetStore | None = None) -> None:
        self.store = store or AssetStore()
        # `renderer` lo usa solo el hilo de dibujo del lienzo (con `render_lock`); las
        # miniaturas de las capas usan el suyo, para no esperar a que termine un dibujo.
        self.renderer = Renderer(self.store)
        self.thumb_renderer = Renderer(self.store, max_cache_bytes=64 * 1024 * 1024)
        self.render_lock = threading.RLock()
        self._to_invalidate: set[str] = set()
        self.history = PhotoHistory()
        self.doc = doc
        self.history.reset(doc)
        self._saved = document_to_dict(doc)
        self.selection: list[str] = []
        self.path: Path | None = None
        self.dirty = False
        self.clone_source = None

    def new_document(self, width: int, height: int, name: str = "Diseño sin título",
                     background: str | None = "#ffffff") -> None:
        width = int(min(max(1, width), 16000))
        height = int(min(max(1, height), 16000))
        self._reset(Document(width, height, background, name))
        self.set_tool("move")
        self.document_replaced.emit()
        self.selection_changed.emit()

    def open_path(self, path: str | Path) -> bool:
        """Abre un .vphoto, o una imagen como diseño nuevo del mismo tamaño."""
        path = Path(path)
        try:
            if path.suffix.lower() == ".vphoto":
                doc, store = photo_io.load_document(path)
                self._reset(doc, store)
                self.path = path
            else:
                pixels = photo_io.load_image(path)
                h, w = pixels.shape[:2]
                self._reset(Document(w, h, None, path.stem))
                layer = photo_io.add_image(self.doc, self.store, pixels, fit=False)
                layer.name = path.stem
                self.history.reset(self.doc)
        except Exception as error:
            self.message.emit(f"No se pudo abrir {path.name}: {error}")
            return False
        self.set_tool("move")
        self.document_replaced.emit()
        self.selection_changed.emit()
        return True

    def save(self, path: str | Path | None = None) -> bool:
        destino = Path(path) if path else self.path
        if destino is None:
            return False
        if destino.suffix.lower() != ".vphoto":
            destino = destino.with_suffix(".vphoto")
        try:
            photo_io.save_document(self.doc, self.store, destino)
        except Exception as error:
            self.message.emit(f"No se pudo guardar: {error}")
            return False
        self.path = destino
        self.dirty = False
        self.collect_assets()
        self._saved = document_to_dict(self.doc)
        self.committed.emit("Guardado")
        return True

    # --- selección --------------------------------------------------------

    def layer(self, layer_id: str) -> Layer | None:
        return self.doc.layer(layer_id)

    def selected(self) -> list[Layer]:
        """Las capas seleccionadas, de abajo hacia arriba."""
        ids = set(self.selection)
        return [c for c in self.doc.layers if c.id in ids]

    def single(self) -> Layer | None:
        sel = self.selected()
        return sel[0] if len(sel) == 1 else None

    def select(self, ids, add: bool = False) -> None:
        nuevos = [i for i in ids if self.doc.layer(i) is not None]
        if add:
            nuevos = self.selection + [i for i in nuevos if i not in self.selection]
        if nuevos != self.selection:
            self.selection = nuevos
            self.selection_changed.emit()

    def toggle_selection(self, layer_id: str) -> None:
        if layer_id in self.selection:
            self.select([i for i in self.selection if i != layer_id])
        else:
            self.select([layer_id], add=True)

    def clear_selection(self) -> None:
        self.select([])

    def select_all(self) -> None:
        self.select([c.id for c in self.doc.layers])

    def set_tool(self, tool: str) -> None:
        if tool not in TOOLS:
            tool = "move"
        if tool != self.tool:
            self.tool = tool
            self.tool_changed.emit(tool)

    # --- historial --------------------------------------------------------

    def touch(self) -> None:
        self.live.emit()

    def _keep_assets(self) -> set[str]:
        """Lo que no se puede soltar del almacén: historial, diseño y subidas de la sesión."""
        return (self.history.assets_in_use() | self.doc.assets()
                | {u[2] for u in self.uploads if u[2]})

    def collect_assets(self) -> None:
        """Suelta las imágenes que ya nadie usa (cada trazo agrega una completa)."""
        keep = self._keep_assets()
        if len(self.store) > len(keep):
            self.store.collect(keep)

    def commit(self, label: str) -> None:
        self.history.push(self.doc, label)
        self.dirty = True
        self.collect_assets()
        self.live.emit()
        self.committed.emit(label)

    def undo(self) -> bool:
        return self._restore(self.history.undo(), "Deshacer")

    def redo(self) -> bool:
        return self._restore(self.history.redo(), "Rehacer")

    def _restore(self, doc: Document | None, prefijo: str) -> bool:
        if doc is None:
            return False
        self.doc = doc
        self.selection = [i for i in self.selection if doc.layer(i) is not None]
        # Si se deshace (o rehace) justo hasta lo guardado, ya no hay cambios sin guardar.
        self.dirty = self._saved is None or document_to_dict(doc) != self._saved
        self.live.emit()
        self.committed.emit(prefijo)
        self.selection_changed.emit()
        return True

    # --- editar -----------------------------------------------------------

    def fit_text(self, layer: Layer) -> None:
        """Ajusta el alto de un texto a lo que ocupa, dejando fijo su borde de arriba."""
        if layer.kind != KIND_TEXT:
            return
        t = layer.transform
        nuevo = max(1.0, text_height(layer))
        dx, dy = geo.rot(0, (nuevo - t.height) / 2, t.rotation)
        t.cx += dx
        t.cy += dy
        t.height = nuevo

    def edit(self, label: str, fn: Callable[[Layer], None],
             layers: list[Layer] | None = None, commit: bool = True) -> None:
        """Aplica `fn` a las capas (por omisión las seleccionadas) y cierra un paso."""
        for capa in (self.selected() if layers is None else layers):
            fn(capa)
            self.fit_text(capa)
        if commit:
            self.commit(label)
        else:
            self.touch()

    def add_layer(self, layer: Layer, label: str, select: bool = True) -> Layer:
        self.doc.layers.append(layer)
        if select:
            self.selection = [layer.id]
            self.selection_changed.emit()
        self.commit(label)
        return layer

    def add_image(self, source, at: tuple[float, float] | None = None) -> Layer | None:
        """Agrega una foto (ruta o píxeles) arriba, cabiendo en el lienzo."""
        try:
            capa = photo_io.add_image(self.doc, self.store, source, fit=True)
        except Exception as error:
            self.message.emit(f"No se pudo abrir la imagen: {error}")
            return None
        if at is not None:
            capa.transform.cx, capa.transform.cy = at
        pixels = self.store.get(capa.asset)
        self._remember_upload(capa.name, pixels, capa.asset)
        self.selection = [capa.id]
        self.selection_changed.emit()
        self.commit("Agregar imagen")
        return capa

    def _remember_upload(self, name: str, pixels: np.ndarray, asset: str) -> None:
        h, w = pixels.shape[:2]
        paso = max(1, max(h, w) // 96)
        mini = np.ascontiguousarray(pixels[::paso, ::paso])
        self.uploads = [u for u in self.uploads if u[0] != name]
        self.uploads.insert(0, (name, mini, asset))
        del self.uploads[24:]

    def add_text(self, index: int = 0, at: tuple[float, float] | None = None) -> Layer:
        _, modelo = templates.text_presets()[index]
        k = max(0.25, self.doc.width / 1080)
        capa = modelo.copy()
        capa.font_size = modelo.font_size * k
        capa.transform.width = min(modelo.transform.width * k, self.doc.width * 0.9)
        capa.transform.height = capa.font_size * 1.3
        cx, cy = at if at is not None else (self.doc.width / 2, self.doc.height / 2)
        capa.transform.cx, capa.transform.cy = cx, cy
        self.fit_text(capa)
        return self.add_layer(capa, "Agregar texto")

    def add_shape(self, kind: str, at: tuple[float, float] | None = None) -> Layer:
        lado = 0.3 * min(self.doc.width, self.doc.height)
        cx, cy = at if at is not None else (self.doc.width / 2, self.doc.height / 2)
        capa = Layer(kind=KIND_SHAPE, name=SHAPE_NAMES.get(kind, "Forma"), shape=kind,
                     transform=Transform(cx, cy, lado, lado))
        if kind in ("line", "arrow"):
            capa.transform.width, capa.transform.height = lado * 1.6, max(12.0, lado * 0.08)
            capa.fill, capa.stroke, capa.stroke_width = None, "#7c5cff", max(6.0, lado * 0.04)
        return self.add_layer(capa, "Agregar forma")

    def add_adjustment_layer(self) -> Layer:
        capa = Layer(kind=KIND_ADJUST, name="Capa de ajuste",
                     transform=Transform(self.doc.width / 2, self.doc.height / 2,
                                         self.doc.width, self.doc.height))
        return self.add_layer(capa, "Agregar capa de ajuste")

    def delete_selected(self) -> bool:
        borrar = [c for c in self.selected() if not c.locked]
        if not borrar:
            if self.selection:
                self.message.emit("Está bloqueado: desbloquéalo para borrarlo")
            return False
        ids = {c.id for c in borrar}
        self.doc.layers = [c for c in self.doc.layers if c.id not in ids]
        self.selection = [i for i in self.selection if i not in ids]
        self.selection_changed.emit()
        self.commit("Eliminar")
        return True

    def duplicate_selected(self) -> list[Layer]:
        nuevas = []
        for capa in self.selected():
            copia = capa.copy()
            copia.name = capa.name
            copia.locked = False
            copia.transform.cx += PASTE_OFFSET
            copia.transform.cy += PASTE_OFFSET
            nuevas.append(copia)
        if not nuevas:
            return []
        self.doc.layers.extend(nuevas)
        self.selection = [c.id for c in nuevas]
        self.selection_changed.emit()
        self.commit("Duplicar")
        return nuevas

    def copy_selected(self) -> bool:
        sel = self.selected()
        if not sel:
            return False
        self.clipboard = [layer_to_dict(c) for c in sel]
        self.clipboard_pixels = {}
        for c in sel:
            for aid in (c.asset, c.mask):
                if aid and self.store.has(aid):
                    self.clipboard_pixels[aid] = self.store.get(aid)
        self._paste_count = 0
        try:
            # La marca en el portapapeles real distingue «copié aquí» de
            # «copié una imagen en otro programa» al pegar.
            QGuiApplication.clipboard().setText("vortex-photo:" + new_id())
        except Exception:
            pass
        return True

    def cut_selected(self) -> bool:
        if not self.copy_selected():
            return False
        return self.delete_selected()

    def paste(self) -> bool:
        mime = None
        try:
            mime = QGuiApplication.clipboard().mimeData()
        except Exception:
            pass
        if mime is not None and mime.hasImage():
            imagen = mime.imageData()
            if isinstance(imagen, QImage) and not imagen.isNull():
                return self.add_image(from_qimage(imagen)) is not None
        if mime is not None and mime.hasUrls():
            ok = False
            for url in mime.urls():
                ruta = url.toLocalFile()
                if ruta and Path(ruta).suffix.lower() in IMAGE_SUFFIXES:
                    ok = self.add_image(ruta) is not None or ok
            if ok:
                return True
        if not self.clipboard:
            return False
        self._paste_count += 1
        nuevas = []
        for d in self.clipboard:
            capa = layer_from_dict(d)
            capa.id = new_id()
            capa.locked = False
            for campo in ("asset", "mask"):
                aid = getattr(capa, campo)
                if aid and not self.store.has(aid):
                    px = self.clipboard_pixels.get(aid)
                    # Se vuelve a registrar en el almacén de este diseño (puede ser otro).
                    setattr(capa, campo, self.store.put(px) if px is not None else None)
            capa.transform.cx += PASTE_OFFSET * self._paste_count
            capa.transform.cy += PASTE_OFFSET * self._paste_count
            nuevas.append(capa)
        self.doc.layers.extend(nuevas)
        self.selection = [c.id for c in nuevas]
        self.selection_changed.emit()
        self.commit("Pegar")
        return True

    # --- orden y propiedades de capas ---------------------------------------

    def reorder(self, op: str) -> bool:
        """`op`: adelante, atras, frente o fondo. Mueve toda la selección."""
        ids = {c.id for c in self.selected()}
        if not ids:
            return False
        capas = self.doc.layers
        antes = [c.id for c in capas]
        if op == "frente":
            capas = [c for c in capas if c.id not in ids] + [c for c in capas if c.id in ids]
        elif op == "fondo":
            capas = [c for c in capas if c.id in ids] + [c for c in capas if c.id not in ids]
        elif op == "adelante":
            for i in range(len(capas) - 2, -1, -1):
                if capas[i].id in ids and capas[i + 1].id not in ids:
                    capas[i], capas[i + 1] = capas[i + 1], capas[i]
        elif op == "atras":
            for i in range(1, len(capas)):
                if capas[i].id in ids and capas[i - 1].id not in ids:
                    capas[i], capas[i - 1] = capas[i - 1], capas[i]
        self.doc.layers = capas
        if [c.id for c in capas] == antes:
            return False
        self.commit({"frente": "Traer al frente", "fondo": "Enviar al fondo",
                     "adelante": "Traer adelante", "atras": "Enviar atrás"}[op])
        return True

    def move_layer_to(self, layer_id: str, new_index: int) -> bool:
        """Pone la capa en esa posición de `doc.layers` (0 = fondo)."""
        i = self.doc.index(layer_id)
        if i < 0:
            return False
        new_index = min(max(0, new_index), len(self.doc.layers) - 1)
        if new_index == i:
            return False
        capa = self.doc.layers.pop(i)
        self.doc.layers.insert(new_index, capa)
        self.commit("Reordenar capas")
        return True

    def set_visible(self, layer_id: str, visible: bool) -> None:
        capa = self.doc.layer(layer_id)
        if capa is not None and capa.visible != visible:
            capa.visible = visible
            self.commit("Mostrar capa" if visible else "Ocultar capa")

    def set_locked(self, layer_id: str, locked: bool) -> None:
        capa = self.doc.layer(layer_id)
        if capa is not None and capa.locked != locked:
            capa.locked = locked
            self.commit("Bloquear" if locked else "Desbloquear")

    def lock_selected(self, locked: bool | None = None) -> None:
        sel = self.selected()
        if not sel:
            return
        valor = (not all(c.locked for c in sel)) if locked is None else locked
        for c in sel:
            c.locked = valor
        self.commit("Bloquear" if valor else "Desbloquear")

    def move_selected(self, dx: float, dy: float, label: str = "Mover") -> bool:
        sel = [c for c in self.selected() if not c.locked]
        if not sel:
            return False
        for c in sel:
            c.transform.cx += dx
            c.transform.cy += dy
        self.commit(label)
        return True

    def align(self, where: str) -> bool:
        """Alinea al lienzo (una capa) o al conjunto (varias)."""
        sel = [c for c in self.selected() if not c.locked]
        if not sel:
            return False
        caja = geo.bbox([c.transform for c in sel])
        if len(sel) == 1:
            caja_ref = (0.0, 0.0, float(self.doc.width), float(self.doc.height))
        else:
            caja_ref = caja
        for c in sel:
            x0, y0, x1, y1 = geo.bbox([c.transform])
            if where == "izquierda":
                c.transform.cx += caja_ref[0] - x0
            elif where == "derecha":
                c.transform.cx += caja_ref[2] - x1
            elif where == "centro":
                c.transform.cx += (caja_ref[0] + caja_ref[2]) / 2 - (x0 + x1) / 2
            elif where == "arriba":
                c.transform.cy += caja_ref[1] - y0
            elif where == "abajo":
                c.transform.cy += caja_ref[3] - y1
            elif where == "medio":
                c.transform.cy += (caja_ref[1] + caja_ref[3]) / 2 - (y0 + y1) / 2
        self.commit("Alinear")
        return True

    def flip_selected(self, horizontal: bool) -> None:
        sel = [c for c in self.selected() if not c.locked]
        if not sel:
            return
        for c in sel:
            if horizontal:
                c.transform.flip_h = not c.transform.flip_h
            else:
                c.transform.flip_v = not c.transform.flip_v
        self.commit("Voltear")

    # --- el diseño --------------------------------------------------------

    def rename(self, name: str) -> None:
        name = name.strip() or "Diseño sin título"
        if name != self.doc.name:
            self.doc.name = name
            self.commit("Cambiar nombre")

    def set_background(self, color: str | None) -> None:
        if color != self.doc.background:
            self.doc.background = color
            self.commit("Color de fondo")

    def resize_document(self, width: int, height: int, adapt: bool = True) -> None:
        """Cambia el tamaño. Con `adapt` el contenido se acomoda al nuevo lienzo."""
        width = int(min(max(1, width), 16000))
        height = int(min(max(1, height), 16000))
        old_w, old_h = self.doc.width, self.doc.height
        if (width, height) == (old_w, old_h):
            return
        if adapt:
            sx, sy = width / old_w, height / old_h
            s = min(sx, sy)
            for c in self.doc.layers:
                t = c.transform
                t.cx *= sx
                t.cy *= sy
                if c.kind == KIND_ADJUST:
                    t.width, t.height = width, height
                    continue
                t.width *= s
                t.height *= s
                c.stroke_width *= s
                c.corner_radius *= s
                fx = c.effects
                fx.shadow.blur *= s
                fx.shadow.dx *= s
                fx.shadow.dy *= s
                fx.outline.width *= s
                fx.glow.radius *= s
                if c.kind == KIND_TEXT:
                    c.font_size *= s
                    c.letter_spacing *= s
                    self.fit_text(c)
        self.doc.width, self.doc.height = width, height
        self.commit("Cambiar tamaño")

    # --- exportar -----------------------------------------------------------

    def export(self, path, fmt: str = "PNG", quality: int = 92, scale: float = 1.0,
               transparent: bool = False) -> None:
        doc = self.doc.copy()
        if transparent and fmt.upper() not in ("JPG", "JPEG"):
            doc.background = None
        photo_io.export(doc, self.store, path, fmt, quality, scale)

    # --- pintar -----------------------------------------------------------

    def _has_pixels(self, layer: Layer | None) -> bool:
        """La capa tiene su imagen en el almacén (si no, no se puede pintar sobre ella)."""
        if layer is None or not layer.asset or not self.store.has(layer.asset):
            self.message.emit("A esta capa le falta su imagen")
            return False
        return True

    def pixel_point(self, layer: Layer, x: float, y: float) -> tuple[float, float]:
        """Un punto del lienzo, en píxeles de la imagen original de la capa."""
        w, h = self.store.size(layer.asset)
        cx0, cy0, cw, ch = layer.crop or (0.0, 0.0, float(w), float(h))
        t = layer.transform
        lx, ly = geo.to_local(t, x, y)
        if t.flip_h:
            lx = -lx
        if t.flip_v:
            ly = -ly
        return (cx0 + (lx / max(1e-6, t.width) + 0.5) * cw,
                cy0 + (ly / max(1e-6, t.height) + 0.5) * ch)

    def pixels_per_unit(self, layer: Layer) -> float:
        return self.pixels_per_unit_xy(layer)[0]

    def pixels_per_unit_xy(self, layer: Layer) -> tuple[float, float]:
        """Píxeles de la imagen por unidad del lienzo, en x y en y (difieren si la capa está estirada)."""
        w, h = self.store.size(layer.asset)
        cw = layer.crop[2] if layer.crop else w
        ch = layer.crop[3] if layer.crop else h
        return (cw / max(1e-6, layer.transform.width), ch / max(1e-6, layer.transform.height))

    def paint_target(self, create: bool) -> Layer | None:
        sel = self.single()
        if sel is not None and sel.kind == KIND_IMAGE and not sel.locked and sel.name == DRAWING_NAME:
            return sel
        if not create:
            return None
        k = min(1.0, MAX_PAINT_SIDE / max(self.doc.width, self.doc.height))
        pixels = np.zeros((max(1, round(self.doc.height * k)), max(1, round(self.doc.width * k)), 4),
                          np.uint8)
        capa = Layer(kind=KIND_IMAGE, name=DRAWING_NAME, asset=self.store.put(pixels),
                     transform=Transform(self.doc.width / 2, self.doc.height / 2,
                                         self.doc.width, self.doc.height))
        self.doc.layers.append(capa)
        return capa

    def paint_stroke(self, points: list[tuple[float, float]], erase: bool = False) -> bool:
        """Un trazo de pincel (o de borrador) con puntos en coordenadas del lienzo."""
        if not points:
            return False
        if erase:
            capa = self.single()
            if capa is None or capa.kind != KIND_IMAGE or capa.locked or not capa.asset:
                self.message.emit("Selecciona una foto o un dibujo para borrar")
                return False
            nueva = False
            if not self._has_pixels(capa):
                return False
        else:
            capa = self.paint_target(create=False)
            nueva = capa is None
            if nueva:
                sel = self.single()
                if sel is not None and sel.locked:
                    self.message.emit("La capa está bloqueada")
                    return False
                capa = self.paint_target(create=True)
            elif not self._has_pixels(capa):
                return False
        ax, ay = self.pixels_per_unit_xy(capa)
        pts = []
        for x, y in points:
            u, v = self.pixel_point(capa, x, y)
            pts.append((u, v, 1.0))
        pixels = self.store.get(capa.asset)
        if aniso.es_estirada(ax, ay):
            # Capa estirada: el pincel se calcula redondo en el lienzo, no en la imagen.
            cob = aniso.cobertura(pixels.shape[:2], pts, self.brush.size, self.brush.hardness,
                                  self.brush.opacity, ax, ay)
            nuevo = aniso.pintar(pixels, cob, self.brush.color, erase)
        else:
            brush = paint.Brush(self.brush.size * ax, self.brush.hardness, self.brush.opacity,
                                self.brush.color, "erase" if erase else "paint")
            nuevo = paint.stroke(pixels, pts, brush)
        capa.asset = self.store.put(nuevo)
        self.invalidate(capa.id)
        if nueva:
            self.selection = [capa.id]
            self.selection_changed.emit()
        self.commit("Borrador" if erase else "Pincel")
        return True

    def _crop_pixels(self, layer: Layer) -> np.ndarray:
        px = self.store.get(layer.asset)
        if layer.crop:
            x, y, w, h = (int(round(v)) for v in layer.crop)
            px = px[max(0, y): y + max(1, h), max(0, x): x + max(1, w)]
        return px

    def _mask_of(self, layer: Layer) -> np.ndarray:
        px = self._crop_pixels(layer)
        if layer.mask and self.store.has(layer.mask):
            m = np.array(self.store.get(layer.mask))
            if m.ndim == 3:
                m = m[..., 0]
            m = np.array(m, np.uint8)
            if m.shape != px.shape[:2]:          # quedó de otro recorte: se acomoda al actual
                m = resize_gray(m, px.shape[1], px.shape[0])
            return m
        return np.full(px.shape[:2], 255, np.uint8)

    def invalidate(self, layer_id: str) -> None:
        """Descarta la caché de una capa sin esperar si el hilo de dibujo está ocupado."""
        if self.render_lock.acquire(blocking=False):
            try:
                self.renderer.invalidate(layer_id)
                self.thumb_renderer.invalidate(layer_id)
            finally:
                self.render_lock.release()
        else:
            self._to_invalidate.add(layer_id)       # lo aplica el hilo de dibujo al empezar

    def apply_pending_invalidations(self) -> None:
        """Lo llama el hilo de dibujo, con `render_lock` tomado."""
        pend, self._to_invalidate = self._to_invalidate, set()
        for lid in pend:
            self.renderer.invalidate(lid)

    def remap_mask(self, layer: Layer, old_crop) -> None:
        """Acomoda la máscara de la capa al recorte nuevo (`old_crop`: el de antes, o None)."""
        if not layer.mask or not self.store.has(layer.mask) or not layer.asset:
            return
        w, h = self.store.size(layer.asset)
        full = (0.0, 0.0, float(w), float(h))
        old, new = old_crop or full, layer.crop or full
        if all(abs(a - b) < 1e-6 for a, b in zip(old, new)):
            return
        m = np.array(self.store.get(layer.mask))
        if m.ndim == 3:
            m = m[..., 0]
        layer.mask = self.store.put(cropmod.remap_mask(np.array(m, np.uint8), old, new))

    def _mask_point(self, layer: Layer, x: float, y: float) -> tuple[float, float]:
        u, v = self.pixel_point(layer, x, y)
        cx0, cy0 = (layer.crop[0], layer.crop[1]) if layer.crop else (0.0, 0.0)
        return u - cx0, v - cy0

    def mask_stroke(self, points: list[tuple[float, float]], erase: bool) -> bool:
        """Pinta (revela) o borra (oculta) la máscara de la foto seleccionada."""
        capa = self.single()
        if capa is None or capa.kind != KIND_IMAGE or capa.locked or not capa.asset or not points:
            self.message.emit("Selecciona una foto para pintar su máscara")
            return False
        if not self._has_pixels(capa):
            return False
        ax, ay = self.pixels_per_unit_xy(capa)
        pts = [(*self._mask_point(capa, x, y), 1.0) for x, y in points]
        actual = self._mask_of(capa)
        if aniso.es_estirada(ax, ay):
            cob = aniso.cobertura(actual.shape[:2], pts, self.brush.size, self.brush.hardness,
                                  1.0, ax, ay)
            nueva = aniso.pintar_mascara(actual, cob, erase)
        else:
            brush = paint.Brush(self.brush.size * ax, self.brush.hardness, 1.0, "#ffffff",
                                "erase" if erase else "paint")
            nueva = paint.stroke_mask(actual, pts, brush)
        capa.mask = self.store.put(nueva)
        self.commit("Borrar con la máscara" if erase else "Pintar la máscara")
        return True

    def wand_click(self, x: float, y: float) -> bool:
        capa = self.single()
        if capa is None or capa.kind != KIND_IMAGE or capa.locked or not capa.asset:
            self.message.emit("Selecciona una foto para usar la varita")
            return False
        if not self._has_pixels(capa):
            return False
        u, v = self._mask_point(capa, x, y)
        px = self._crop_pixels(capa)
        h, w = px.shape[:2]
        if not (0 <= u < w and 0 <= v < h):
            return False
        sel = paint.magic_wand(px, int(u), int(v), self.wand_tolerance, self.wand_contiguous)
        actual = self._mask_of(capa)
        if self.wand_keep:
            nueva = np.minimum(actual, sel)
        else:
            nueva = np.where(sel > 127, 0, actual).astype(np.uint8)
        capa.mask = self.store.put(nueva)
        self.commit("Varita mágica")
        return True

    def remove_background(self) -> bool:
        capa = self.single()
        if capa is None or capa.kind != KIND_IMAGE or capa.locked or not capa.asset:
            self.message.emit("Selecciona una foto para quitarle el fondo")
            return False
        if not self._has_pixels(capa):
            return False
        capa.mask = self.store.put(paint.remove_background(self._crop_pixels(capa)))
        self.commit("Quitar fondo")
        return True

    def clear_mask(self) -> bool:
        capa = self.single()
        if capa is None or not capa.mask:
            return False
        capa.mask = None
        self.commit("Quitar máscara")
        return True

    def clone_stroke(self, points: list[tuple[float, float]]) -> bool:
        capa = self.single()
        if capa is None or capa.kind != KIND_IMAGE or capa.locked or not capa.asset or not points:
            return False
        if self.clone_source is None:
            self.message.emit("Alt + clic para elegir de dónde copiar")
            return False
        if not self._has_pixels(capa):
            return False
        k = self.pixels_per_unit(capa)
        pts = [(*self.pixel_point(capa, x, y), 1.0) for x, y in points]
        sx, sy = self.clone_source
        offset = (sx - pts[0][0], sy - pts[0][1])
        brush = paint.Brush(self.brush.size * k, self.brush.hardness, self.brush.opacity)
        capa.asset = self.store.put(paint.clone(self.store.get(capa.asset), pts, brush, offset))
        self.invalidate(capa.id)
        self.commit("Tampón de clonar")
        return True


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def is_finite_point(x: float, y: float) -> bool:
    return math.isfinite(x) and math.isfinite(y)
