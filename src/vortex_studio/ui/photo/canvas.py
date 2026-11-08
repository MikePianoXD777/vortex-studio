"""El lienzo de Vortex Photo: dibujo, selección, mover/escalar/girar, guías, zoom.

El render lo hace el motor (`Renderer.render`) a la escala de la vista, con un
temporizador de un solo disparo que junta los cambios: si llegan veinte
`touch()` mientras se arrastra, se dibuja una vez. Mientras algo se arrastra
se usa una escala más chica («borrador») y al soltar, la buena.

Todo lo que se dibuja encima (caja de selección, asas, guías, recorte, cursor
del pincel) lo pinta este widget con `QPainter`; no pasa por el motor.
"""

from __future__ import annotations

import copy
import math
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget

from vortex_studio.photo.document import KIND_ADJUST, KIND_IMAGE, KIND_TEXT, Layer
from vortex_studio.photo.render import to_qimage
from vortex_studio.ui import theme
from vortex_studio.ui.photo import crop as cropmod
from vortex_studio.ui.photo import geometry as geo
from vortex_studio.ui.photo.controls import MORADO, ROSA
from vortex_studio.ui.photo.session import IMAGE_SUFFIXES, PhotoSession

MIN_ZOOM, MAX_ZOOM = 0.01, 32.0
FONDO = "#1b1b1f"
HANDLE_PX = 10          # lado de un asa en pantalla
HANDLE_HIT = 9          # radio de acierto
ROTATE_OFFSET_PX = 28   # el asa de giro, sobre el borde de arriba
DRAG_START_PX = 3
SNAP_PX = 6
MAX_RENDER_PIXELS = 6_000_000
MAX_DRAFT_PIXELS = 1_500_000
BRUSH_TOOLS = ("brush", "erase", "mask_paint", "mask_erase", "clone")


def _hex_alpha(color: str, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(alpha)
    return c


class CanvasView(QWidget):
    files_dropped = Signal(list, float, float)      # rutas, x y y en el lienzo
    image_dropped = Signal(object, float, float)    # una QImage soltada
    zoom_changed = Signal(float)
    crop_changed = Signal(bool)                     # entró o salió del modo recortar
    editing_changed = Signal(bool)                  # empezó o terminó de editar texto

    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        self.zoom = 0.5
        self.origin = QPointF(0, 0)
        self._fit = True
        self._frame: QImage | None = None
        self.show_original = False
        self.render_count = 0
        self.last_render_scale = 1.0
        self._draft = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(8)
        self._timer.timeout.connect(self._render)

        self._drag: dict | None = None
        self._guides: list = []
        self._hud = ""
        self._space = False
        self._hover_id: str | None = None
        self._cursor_px: QPointF | None = None
        self._stroke: list[tuple[float, float]] = []
        self._marquee: tuple[float, float, float, float] | None = None
        self._edit: dict | None = None
        self._crop: dict | None = None
        self._checker = self._make_checker()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.setMinimumSize(200, 200)

        session.live.connect(self._on_live)
        session.committed.connect(self._on_committed)
        session.selection_changed.connect(self._on_selection)
        session.document_replaced.connect(self._on_replaced)
        session.tool_changed.connect(self._on_tool)

    # --- coordenadas ------------------------------------------------------

    def to_screen(self, x: float, y: float) -> QPointF:
        return QPointF(self.origin.x() + x * self.zoom, self.origin.y() + y * self.zoom)

    def to_canvas(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self.origin.x()) / self.zoom, (sy - self.origin.y()) / self.zoom

    def canvas_rect(self) -> QRectF:
        d = self.s.doc
        return QRectF(self.origin.x(), self.origin.y(), d.width * self.zoom, d.height * self.zoom)

    # --- zoom y desplazamiento ---------------------------------------------

    def set_zoom(self, z: float, anchor: QPointF | None = None, fit: bool = False) -> None:
        z = min(max(z, MIN_ZOOM), MAX_ZOOM)
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        cx, cy = self.to_canvas(anchor.x(), anchor.y())
        self.zoom = z
        self.origin = QPointF(anchor.x() - cx * z, anchor.y() - cy * z)
        self._fit = fit
        self._clamp_origin()
        self.zoom_changed.emit(self.zoom)
        self.request_render(draft=True)
        self._settle()

    def fit(self, margin: int = 40) -> None:
        d = self.s.doc
        w, h = max(1, self.width() - 2 * margin), max(1, self.height() - 2 * margin)
        z = min(w / d.width, h / d.height)
        z = min(max(z, MIN_ZOOM), MAX_ZOOM)
        self.zoom = z
        self.origin = QPointF((self.width() - d.width * z) / 2, (self.height() - d.height * z) / 2)
        self._fit = True
        self.zoom_changed.emit(self.zoom)
        self.request_render()
        self.update()

    def zoom_100(self) -> None:
        self.set_zoom(1.0)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.25)

    def _clamp_origin(self) -> None:
        """Que siempre quede un pedazo del lienzo a la vista: no se pierde."""
        d = self.s.doc
        keep = 80
        x = min(max(self.origin.x(), keep - d.width * self.zoom), self.width() - keep)
        y = min(max(self.origin.y(), keep - d.height * self.zoom), self.height() - keep)
        self.origin = QPointF(x, y)

    def pan_by(self, dx: float, dy: float) -> None:
        self.origin = QPointF(self.origin.x() + dx, self.origin.y() + dy)
        self._fit = False
        self._clamp_origin()
        self.update()

    def resizeEvent(self, e) -> None:
        if self._fit:
            self.fit()
        else:
            self._clamp_origin()
        super().resizeEvent(e)

    # --- render -----------------------------------------------------------

    def request_render(self, draft: bool = False) -> None:
        self._draft = self._draft or draft
        if not self._timer.isActive():
            self._timer.start()

    def _settle(self) -> None:
        """Pide el render a escala buena en cuanto se suelte lo que se arrastra."""
        QTimer.singleShot(120, self._final_render)

    def _final_render(self) -> None:
        if self._drag is None:
            self._draft = False
            self.request_render()

    def flush(self) -> None:
        """Dibuja ya lo pendiente (para las pruebas y para capturas)."""
        if self._timer.isActive():
            self._timer.stop()
            self._render()
        elif self._frame is None:
            self._render()

    def render_scale(self, draft: bool) -> float:
        d = self.s.doc
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        limite = MAX_DRAFT_PIXELS if draft else MAX_RENDER_PIXELS
        s = min(self.zoom * dpr, math.sqrt(limite / (d.width * d.height)))
        if draft:
            s *= 0.75
        return max(s, 1.0 / max(d.width, d.height))

    def _hidden(self) -> set[str]:
        hide = set()
        if self._edit:
            hide.add(self._edit["id"])
        if self._crop:
            hide.add(self._crop["id"])
        return hide

    def _render(self) -> None:
        draft = self._draft
        self._draft = False
        scale = self.render_scale(draft)
        try:
            px = self.s.renderer.render(self.s.doc, scale, hide=self._hidden(),
                                        original=self.show_original)
            self._frame = to_qimage(px)
        except Exception as error:      # un fallo del motor no debe tumbar la ventana
            self.s.message.emit(f"No se pudo dibujar: {error}")
            return
        self.last_render_scale = scale
        self.render_count += 1
        self.update()

    def _on_live(self) -> None:
        self.request_render(draft=self._drag is not None)
        self._sync_editor()
        self.update()

    def _on_committed(self, label: str) -> None:
        self.request_render()
        if self._edit and self.s.doc.layer(self._edit["id"]) is None:
            self._drop_editor()
        if self._crop and self.s.doc.layer(self._crop["id"]) is None:
            self._drop_crop()
        self.update()

    def _on_selection(self) -> None:
        if self._crop and self.s.selection != [self._crop["id"]]:
            self.cancel_crop()
        self.update()

    def _on_replaced(self) -> None:
        self._drop_editor()
        self._drop_crop()
        self._frame = None
        self.fit()
        self.request_render()

    def _on_tool(self, tool: str) -> None:
        self._stroke = []
        self._update_cursor()
        self.update()

    def set_show_original(self, on: bool) -> None:
        if on != self.show_original:
            self.show_original = on
            self.request_render()

    # --- dibujo -----------------------------------------------------------

    @staticmethod
    def _make_checker() -> QPixmap:
        pm = QPixmap(16, 16)
        pm.fill(QColor("#cfcfd4"))
        p = QPainter(pm)
        p.fillRect(0, 0, 8, 8, QColor("#ffffff"))
        p.fillRect(8, 8, 8, 8, QColor("#ffffff"))
        p.end()
        return pm

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(FONDO))
        cr = self.canvas_rect()
        for i, a in ((6, 0.05), (4, 0.07), (2, 0.1)):
            p.fillRect(cr.adjusted(-i, -i + 3, i, i + 3), QColor(0, 0, 0, int(255 * a)))
        if self.s.doc.background is None:
            p.drawTiledPixmap(cr.toAlignedRect(), self._checker)
        if self._frame is not None:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(cr, self._frame)
        p.setRenderHint(QPainter.Antialiasing)
        if self._crop:
            self._paint_crop(p)
        else:
            self._paint_selection(p)
            self._paint_guides(p)
            self._paint_marquee(p)
            self._paint_stroke(p)
        self._paint_hud(p)
        p.end()

    def _poly(self, t) -> QPolygonF:
        return QPolygonF([self.to_screen(*c) for c in geo.corners(t)])

    def _paint_selection(self, p: QPainter) -> None:
        sel = self.s.selected()
        if self._hover_id and self._hover_id not in self.s.selection and not self._drag:
            h = self.s.doc.layer(self._hover_id)
            if h is not None:
                p.setPen(QPen(_hex_alpha(MORADO, 0.7), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawPolygon(self._poly(h.transform))
        if not sel or self._edit:
            return
        bloqueado = any(c.locked for c in sel)
        for c in sel:
            pen = QPen(QColor("#9a9aa2") if c.locked else QColor(MORADO), 1.5)
            if len(sel) > 1 and not c.locked:
                pen = QPen(_hex_alpha(MORADO, 0.85), 1.0)
            if c.locked:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(self._poly(c.transform))
        box = geo.selection_box([c.transform for c in sel])
        if bloqueado or self._tools_hide_handles():
            return
        if len(sel) > 1:
            p.setPen(QPen(QColor(MORADO), 1.5))
            p.drawPolygon(self._poly(box))
        for name, (x, y) in self.handle_points(sel, box).items():
            pt = self.to_screen(x, y)
            edge = name in ("n", "s", "e", "w")
            w, h = (HANDLE_PX + (4 if edge and name in ("n", "s") else 0),
                    HANDLE_PX + (4 if edge and name in ("e", "w") else 0))
            if edge:
                w, h = (14, 8) if name in ("n", "s") else (8, 14)
            p.setPen(QPen(QColor(MORADO), 1.5))
            p.setBrush(QColor("#ffffff"))
            r = QRectF(pt.x() - w / 2, pt.y() - h / 2, w, h)
            p.drawRoundedRect(r, 4, 4) if edge else p.drawEllipse(QRectF(pt.x() - 5.5, pt.y() - 5.5, 11, 11))
        rx, ry = geo.rotate_handle_point(box, ROTATE_OFFSET_PX / self.zoom)
        pt = self.to_screen(rx, ry)
        p.setPen(QPen(QColor(MORADO), 1.5))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(pt, 9, 9)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(MORADO), 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(pt.x() - 4, pt.y() - 4, 8, 8), 40 * 16, 270 * 16)

    def _tools_hide_handles(self) -> bool:
        return self.s.tool != "move" or self._drag is not None and self._drag["kind"] == "marquee"

    def handle_points(self, sel: list[Layer], box=None) -> dict[str, tuple[float, float]]:
        """Dónde están las asas de la selección, en coordenadas del lienzo."""
        box = box or geo.selection_box([c.transform for c in sel])
        pts = geo.handle_points(box)
        if len(sel) == 1 and sel[0].kind == KIND_TEXT:
            pts = {k: v for k, v in pts.items() if k in ("nw", "ne", "se", "sw", "e", "w")}
        if len(sel) == 1 and sel[0].kind == KIND_ADJUST:
            return {}
        return pts

    def _paint_guides(self, p: QPainter) -> None:
        for eje, pos, a, b, tipo in self._guides:
            p.setPen(QPen(QColor(ROSA if tipo == "lienzo" else MORADO), 1.2))
            if eje == "v":
                p.drawLine(self.to_screen(pos, a), self.to_screen(pos, b))
            else:
                p.drawLine(self.to_screen(a, pos), self.to_screen(b, pos))

    def _paint_marquee(self, p: QPainter) -> None:
        if self._marquee:
            x0, y0, x1, y1 = self._marquee
            r = QRectF(self.to_screen(x0, y0), self.to_screen(x1, y1)).normalized()
            p.setPen(QPen(QColor(MORADO), 1))
            p.setBrush(_hex_alpha(MORADO, 0.12))
            p.drawRect(r)

    def _paint_stroke(self, p: QPainter) -> None:
        tool = self.s.tool
        if tool in BRUSH_TOOLS and self._cursor_px is not None and self._drag is None:
            self._paint_brush_cursor(p, self._cursor_px)
        if self._stroke and tool in BRUSH_TOOLS:
            br = self.s.brush
            if tool == "brush":
                col = _hex_alpha(br.color, br.opacity)
            elif tool == "erase":
                col = QColor(255, 255, 255, 110)
            elif tool == "mask_paint":
                col = QColor(80, 220, 120, 120)
            elif tool == "mask_erase":
                col = QColor(255, 80, 80, 120)
            else:
                col = QColor(255, 255, 255, 90)
            pen = QPen(col, max(1.0, br.size * self.zoom), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            pts = [self.to_screen(x, y) for x, y in self._stroke]
            if len(pts) == 1:
                p.drawPoint(pts[0])
            else:
                p.drawPolyline(pts)
            self._paint_brush_cursor(p, self.to_screen(*self._stroke[-1]))

    def _paint_brush_cursor(self, p: QPainter, pt: QPointF) -> None:
        r = max(1.5, self.s.brush.size * self.zoom / 2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 170), 2.5))
        p.drawEllipse(pt, r, r)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.2))
        p.drawEllipse(pt, r, r)
        if self.s.tool == "clone" and self.s.clone_source is not None:
            sx, sy = self.s.clone_source
            capa = self.s.single()
            if capa is not None:
                p.drawLine(pt + QPointF(-4, 0), pt + QPointF(4, 0))

    def _paint_hud(self, p: QPainter) -> None:
        if not self._hud:
            return
        f = QFont()
        f.setPixelSize(12)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(self._hud) + 18
        sel = self.s.selected()
        box = geo.selection_box([c.transform for c in sel]) if sel else None
        if box is None:
            return
        pt = self.to_screen(box.cx, box.cy + box.height / 2 + 30 / self.zoom)
        r = QRectF(pt.x() - w / 2, pt.y(), w, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(MORADO))
        p.drawRoundedRect(r, 11, 11)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignCenter, self._hud)

    # --- eventos de ratón ---------------------------------------------------

    def _pos(self, e) -> tuple[float, float]:
        pt = e.position()
        return self.to_canvas(pt.x(), pt.y())

    def hit_layer(self, x: float, y: float) -> Layer | None:
        pad = 4.0 / self.zoom
        hide = self._hidden()
        for c in reversed(self.s.doc.layers):
            if not c.visible or c.kind == KIND_ADJUST or c.id in hide:
                continue
            if geo.contains(c.transform, x, y, pad):
                return c
        return None

    def hit_handle(self, sx: float, sy: float) -> str | None:
        """El asa de la selección bajo el puntero ('rotate', 'nw'…), o None."""
        sel = self.s.selected()
        if not sel or any(c.locked for c in sel) or self.s.tool != "move" or self._edit:
            return None
        box = geo.selection_box([c.transform for c in sel])
        rx, ry = geo.rotate_handle_point(box, ROTATE_OFFSET_PX / self.zoom)
        rp = self.to_screen(rx, ry)
        if math.hypot(rp.x() - sx, rp.y() - sy) <= HANDLE_HIT + 2:
            return "rotate"
        best, best_d = None, HANDLE_HIT
        for name, (x, y) in self.handle_points(sel, box).items():
            pt = self.to_screen(x, y)
            d = math.hypot(pt.x() - sx, pt.y() - sy)
            if d <= best_d:
                best, best_d = name, d
        return best

    def mousePressEvent(self, e) -> None:
        self.setFocus()
        sx, sy = e.position().x(), e.position().y()
        x, y = self._pos(e)
        if self._edit:
            self.end_text_edit()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._space):
            self._drag = {"kind": "pan", "last": QPointF(sx, sy)}
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return
        if self._crop:
            self._crop_press(x, y)
            return
        tool = self.s.tool
        if tool in BRUSH_TOOLS or tool == "wand":
            self._tool_press(e, x, y)
            return
        mods = e.modifiers()
        h = self.hit_handle(sx, sy)
        sel = self.s.selected()
        if h == "rotate":
            self._begin_rotate(x, y)
            return
        if h:
            self._begin_resize(h)
            return
        capa = self.hit_layer(x, y)
        if capa is not None:
            if mods & Qt.ShiftModifier:
                self.s.toggle_selection(capa.id)
                return
            if capa.id not in self.s.selection:
                self.s.select([capa.id])
            self._begin_move(x, y, sx, sy)
            return
        if not (mods & Qt.ShiftModifier):
            self.s.clear_selection()
        self._drag = {"kind": "marquee", "x0": x, "y0": y, "base": list(self.s.selection),
                      "shift": bool(mods & Qt.ShiftModifier)}
        self._marquee = (x, y, x, y)

    def _begin_move(self, x, y, sx, sy) -> None:
        sel = self.s.selected()
        movibles = [c for c in sel if not c.locked]
        if not movibles:
            self._drag = None
            return
        ids = {c.id for c in movibles}
        otros = [geo.bbox([c.transform]) for c in self.s.doc.layers
                 if c.id not in ids and c.visible and c.kind != KIND_ADJUST]
        self._drag = {
            "kind": "move", "x0": x, "y0": y, "sx": sx, "sy": sy, "moved": False,
            "orig": {c.id: (c.transform.cx, c.transform.cy) for c in movibles},
            "box": geo.bbox([c.transform for c in movibles]), "others": otros,
        }

    def _begin_resize(self, handle: str) -> None:
        sel = self.s.selected()
        box = geo.selection_box([c.transform for c in sel])
        self._drag = {
            "kind": "resize", "handle": handle, "box": box, "moved": False,
            "orig": [(c, replace(c.transform), c.font_size, c.letter_spacing) for c in sel],
            "group": len(sel) > 1,
        }
        # Como en Canva: en una foto, las asas de los lados recortan en vez de deformar.
        if (len(sel) == 1 and sel[0].kind == KIND_IMAGE and sel[0].asset
                and handle not in geo.CORNERS and self.s.store.has(sel[0].asset)):
            c = sel[0]
            copia = copy.copy(c)
            copia.transform = replace(c.transform)
            self._drag["crop"] = {
                "math": cropmod.CropMath(copia, self.s.store.size(c.asset)),
                "crop0": c.crop, "t0": replace(c.transform),
            }

    def _begin_rotate(self, x, y) -> None:
        sel = self.s.selected()
        box = geo.selection_box([c.transform for c in sel])
        self._drag = {
            "kind": "rotate", "box": box, "moved": False,
            "a0": geo.angle_to(box.cx, box.cy, x, y),
            "orig": [(c, replace(c.transform)) for c in sel],
        }

    def _tool_press(self, e, x, y) -> None:
        tool = self.s.tool
        if tool == "wand":
            self.s.wand_click(x, y)
            return
        if tool == "clone" and (e.modifiers() & Qt.AltModifier):
            capa = self.s.single()
            if capa is not None and capa.kind == KIND_IMAGE and capa.asset:
                self.s.clone_source = self.s.pixel_point(capa, x, y)
                self.s.message.emit("Origen elegido: ahora pinta sobre la zona a tapar")
            return
        if tool == "clone" and self.s.clone_source is None:
            self.s.message.emit("Alt + clic para elegir de dónde copiar")
            return
        self._stroke = [(x, y)]
        self._drag = {"kind": "stroke"}
        self.update()

    def mouseMoveEvent(self, e) -> None:
        sx, sy = e.position().x(), e.position().y()
        x, y = self._pos(e)
        self._cursor_px = QPointF(sx, sy)
        d = self._drag
        if d is None:
            old = self._hover_id
            capa = self.hit_layer(x, y) if not self._crop else None
            self._hover_id = capa.id if capa else None
            self._update_cursor(sx, sy)
            if self.s.tool in BRUSH_TOOLS or old != self._hover_id:
                self.update()
            return
        kind = d["kind"]
        if kind == "pan":
            last = d["last"]
            self.pan_by(sx - last.x(), sy - last.y())
            d["last"] = QPointF(sx, sy)
        elif kind == "move":
            self._do_move(e, x, y, sx, sy)
        elif kind == "resize":
            self._do_resize(e, x, y)
        elif kind == "rotate":
            self._do_rotate(e, x, y)
        elif kind == "marquee":
            self._do_marquee(x, y)
        elif kind == "stroke":
            if geo and math.isfinite(x) and math.isfinite(y):
                self._stroke.append((x, y))
            self.update()
        elif kind == "crop":
            self._crop_drag(x, y)

    def _do_move(self, e, x, y, sx, sy) -> None:
        d = self._drag
        if not d["moved"] and math.hypot(sx - d["sx"], sy - d["sy"]) < DRAG_START_PX:
            return
        d["moved"] = True
        dx, dy = x - d["x0"], y - d["y0"]
        if e.modifiers() & Qt.ShiftModifier:        # solo en horizontal o en vertical
            if abs(dx) >= abs(dy):
                dy = 0.0
            else:
                dx = 0.0
        self._guides = []
        if not (e.modifiers() & Qt.ControlModifier):
            x0, y0, x1, y1 = d["box"]
            doc = self.s.doc
            ax, ay, guias = geo.compute_snap((x0 + dx, y0 + dy, x1 + dx, y1 + dy), d["others"],
                                             doc.width, doc.height, SNAP_PX / self.zoom)
            dx, dy = dx + ax, dy + ay
            self._guides = guias
        for c in self.s.selected():
            if c.id in d["orig"]:
                ox, oy = d["orig"][c.id]
                c.transform.cx, c.transform.cy = ox + dx, oy + dy
        self.s.touch()

    def _do_resize(self, e, x, y) -> None:
        d = self._drag
        d["moved"] = True
        handle, box = d["handle"], d["box"]
        shift = bool(e.modifiers() & Qt.ShiftModifier)
        esquina = handle in geo.CORNERS
        if d["group"]:
            nb = geo.resize_transform(box, handle, x, y, proportional=esquina and not shift)
            sx, sy = nb.width / box.width, nb.height / box.height
            for c, t0, fs0, ls0 in d["orig"]:
                if c.locked:
                    continue
                c.transform = replace(t0, cx=nb.cx + (t0.cx - box.cx) * sx,
                                      cy=nb.cy + (t0.cy - box.cy) * sy,
                                      width=t0.width * sx, height=t0.height * sy)
                if c.kind == KIND_TEXT:
                    k = math.sqrt(sx * sy)
                    c.font_size, c.letter_spacing = fs0 * k, ls0 * k
                    self.s.fit_text(c)
            self._hud = f"{round(nb.width)} × {round(nb.height)}"
        else:
            c, t0, fs0, ls0 = d["orig"][0]
            cr = d.get("crop")
            if cr is not None and not shift:
                m = cr["math"]
                lx, ly = geo.to_local(cr["t0"], x, y)
                rect = cropmod.drag_handle(m.current_rect(), handle, lx, ly, m.full_rect(), None)
                c.crop, nt = m.result(rect)
                c.transform = replace(nt, rotation=t0.rotation)
                self.s.renderer.invalidate(c.id)
                self._hud = f"{round(c.transform.width)} × {round(c.transform.height)}"
                self.s.touch()
                return
            if cr is not None:                        # con Mayúsculas el lado sí deforma
                c.crop = cr["crop0"]
                cr["estirado"] = True
            if c.kind == KIND_TEXT:
                prop = esquina
            elif c.kind == KIND_IMAGE:
                prop = esquina and not shift
            else:
                prop = esquina and shift
            nt = geo.resize_transform(t0, handle, x, y, proportional=prop)
            if c.kind == KIND_TEXT:
                if esquina:
                    k = nt.width / t0.width
                    c.font_size, c.letter_spacing = fs0 * k, ls0 * k
                else:
                    nt = replace(nt, height=t0.height)
            c.transform = nt
            if c.kind == KIND_TEXT:
                self.s.fit_text(c)
            self._hud = f"{round(c.transform.width)} × {round(c.transform.height)}"
        self.s.touch()

    def _do_rotate(self, e, x, y) -> None:
        d = self._drag
        d["moved"] = True
        box = d["box"]
        delta = geo.angle_to(box.cx, box.cy, x, y) - d["a0"]
        snap = bool(e.modifiers() & Qt.ShiftModifier)
        if len(d["orig"]) == 1:
            c, t0 = d["orig"][0]
            ang = t0.rotation + delta
            if snap:
                ang = geo.snap_angle(ang)
            c.transform = replace(t0, rotation=geo.normalize_angle(ang))
            self._hud = f"{round(c.transform.rotation)}°"
        else:
            if snap:
                delta = geo.snap_angle(delta)
            for c, t0 in d["orig"]:
                nx, ny = geo.rotate_point(t0.cx, t0.cy, box.cx, box.cy, delta)
                c.transform = replace(t0, cx=nx, cy=ny,
                                      rotation=geo.normalize_angle(t0.rotation + delta))
            self._hud = f"{round(geo.normalize_angle(delta))}°"
        self.s.touch()

    def _do_marquee(self, x, y) -> None:
        d = self._drag
        self._marquee = (d["x0"], d["y0"], x, y)
        x0, x1 = sorted((d["x0"], x))
        y0, y1 = sorted((d["y0"], y))
        dentro = []
        for c in self.s.doc.layers:
            if not c.visible or c.kind == KIND_ADJUST:
                continue
            bx0, by0, bx1, by1 = geo.bbox([c.transform])
            if bx0 <= x1 and bx1 >= x0 and by0 <= y1 and by1 >= y0:
                dentro.append(c.id)
        base = d["base"] if d["shift"] else []
        self.s.select(base + [i for i in dentro if i not in base])
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        d = self._drag
        self._drag = None
        if d is None:
            return
        kind = d["kind"]
        self._guides = []
        self._hud = ""
        self._marquee = None
        if kind == "pan":
            self._update_cursor()
            return
        if kind == "move" and d["moved"]:
            self.s.commit("Mover")
        elif kind == "resize" and d["moved"]:
            cr = d.get("crop")
            if cr is not None and not cr.get("estirado"):
                capa = self.s.doc.layer(d["orig"][0][0].id)
                if capa is not None:
                    self.s.remap_mask(capa, cr["crop0"])
                    self.s.renderer.invalidate(capa.id)
                self.s.commit("Recortar")
            else:
                self.s.commit("Cambiar tamaño")
        elif kind == "rotate" and d["moved"]:
            self.s.commit("Girar")
        elif kind == "stroke":
            self._finish_stroke()
        elif kind == "crop":
            self._crop["drag"] = None
        self._settle()
        self.update()

    def _finish_stroke(self) -> None:
        pts, self._stroke = self._stroke, []
        tool = self.s.tool
        if tool == "brush":
            self.s.paint_stroke(pts)
        elif tool == "erase":
            self.s.paint_stroke(pts, erase=True)
        elif tool == "mask_paint":
            self.s.mask_stroke(pts, erase=False)
        elif tool == "mask_erase":
            self.s.mask_stroke(pts, erase=True)
        elif tool == "clone":
            self.s.clone_stroke(pts)

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._crop or self.s.tool != "move":
            return
        x, y = self._pos(e)
        capa = self.hit_layer(x, y)
        if capa is None:
            return
        if capa.id not in self.s.selection:
            self.s.select([capa.id])
        if capa.kind == KIND_TEXT:
            self.begin_text_edit(capa.id)
        elif capa.kind == KIND_IMAGE:
            self.begin_crop(capa.id)

    def leaveEvent(self, e) -> None:
        self._cursor_px = None
        self._hover_id = None
        self.update()
        super().leaveEvent(e)

    def wheelEvent(self, e) -> None:
        delta = e.angleDelta()
        if e.modifiers() & Qt.ControlModifier:
            f = 1.0015 ** delta.y()
            self.set_zoom(self.zoom * f, e.position())
            e.accept()
            return
        dx, dy = delta.x() / 2.0, delta.y() / 2.0
        if e.modifiers() & Qt.ShiftModifier and dx == 0:
            dx, dy = dy, 0.0
        self.pan_by(dx, dy)
        e.accept()

    # --- cursor -----------------------------------------------------------

    def _update_cursor(self, sx: float | None = None, sy: float | None = None) -> None:
        if self._space:
            self.setCursor(Qt.OpenHandCursor)
            return
        if self._crop:
            self.setCursor(Qt.ArrowCursor)
            return
        tool = self.s.tool
        if tool in BRUSH_TOOLS:
            self.setCursor(Qt.BlankCursor)
            return
        if tool == "wand":
            self.setCursor(Qt.CrossCursor)
            return
        if sx is None and self._cursor_px is not None:
            sx, sy = self._cursor_px.x(), self._cursor_px.y()
        if sx is None:
            self.setCursor(Qt.ArrowCursor)
            return
        h = self.hit_handle(sx, sy)
        if h == "rotate":
            self.setCursor(Qt.CrossCursor)
        elif h:
            sel = self.s.selected()
            box = geo.selection_box([c.transform for c in sel])
            hx, hy = geo.HANDLES[h]
            vx, vy = geo.rot(hx, hy, box.rotation)
            ang = (math.degrees(math.atan2(vy, vx)) + 360) % 180
            if ang < 22.5 or ang >= 157.5:
                self.setCursor(Qt.SizeHorCursor)
            elif ang < 67.5:
                self.setCursor(Qt.SizeFDiagCursor)
            elif ang < 112.5:
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.SizeBDiagCursor)
        elif self._hover_id:
            capa = self.s.doc.layer(self._hover_id)
            self.setCursor(Qt.ArrowCursor if capa is not None and capa.locked else Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # --- teclado ----------------------------------------------------------

    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        if k == Qt.Key_Space and not e.isAutoRepeat():
            self._space = True
            self._update_cursor()
            return
        if self._crop:
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.apply_crop()
            elif k == Qt.Key_Escape:
                self.cancel_crop()
            return
        if k == Qt.Key_Escape:
            if self._edit:
                self.end_text_edit()
            elif self.s.tool != "move":
                self.s.set_tool("move")
            else:
                self.s.clear_selection()
            return
        paso = 10 if e.modifiers() & Qt.ShiftModifier else 1
        flechas = {Qt.Key_Left: (-paso, 0), Qt.Key_Right: (paso, 0),
                   Qt.Key_Up: (0, -paso), Qt.Key_Down: (0, paso)}
        if k in flechas and self.s.selection and self.s.tool == "move":
            self.s.move_selected(*flechas[k])
            return
        if k in (Qt.Key_Delete, Qt.Key_Backspace) and not self._edit:
            self.s.delete_selected()
            return
        e.ignore()

    def keyReleaseEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = False
            self._update_cursor()
            return
        e.ignore()

    def focusOutEvent(self, e) -> None:
        self._space = False
        super().focusOutEvent(e)

    # --- arrastrar y soltar --------------------------------------------------

    def dragEnterEvent(self, e) -> None:
        m = e.mimeData()
        if m.hasUrls() and any(self._accepts(u.toLocalFile()) for u in m.urls()) or m.hasImage():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        e.acceptProposedAction()

    @staticmethod
    def _accepts(ruta: str) -> bool:
        if not ruta:
            return False
        suf = Path(ruta).suffix.lower()
        return suf in IMAGE_SUFFIXES or suf == ".vphoto"

    def dropEvent(self, e) -> None:
        x, y = self.to_canvas(e.position().x(), e.position().y())
        m = e.mimeData()
        rutas = [u.toLocalFile() for u in m.urls() if self._accepts(u.toLocalFile())] if m.hasUrls() else []
        if rutas:
            self.files_dropped.emit(rutas, x, y)
            e.acceptProposedAction()
        elif m.hasImage():
            img = m.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.image_dropped.emit(img, x, y)
                e.acceptProposedAction()

    # --- menú contextual ----------------------------------------------------

    def contextMenuEvent(self, e) -> None:
        x, y = self.to_canvas(e.pos().x(), e.pos().y())
        capa = self.hit_layer(x, y)
        if capa is not None and capa.id not in self.s.selection:
            self.s.select([capa.id])
        self.build_context_menu().exec(e.globalPos())

    def build_context_menu(self) -> QMenu:
        s = self.s
        m = QMenu(self)
        hay = bool(s.selection)
        acc = {}
        for clave, texto, fn in (
            ("copiar", "Copiar", s.copy_selected), ("cortar", "Cortar", s.cut_selected),
            ("pegar", "Pegar", s.paste), ("duplicar", "Duplicar", s.duplicate_selected),
            (None, None, None),
            ("frente", "Traer al frente", lambda: s.reorder("frente")),
            ("fondo", "Enviar al fondo", lambda: s.reorder("fondo")),
            (None, None, None),
            ("bloquear", "Bloquear / desbloquear", s.lock_selected),
            ("borrar", "Eliminar", s.delete_selected),
        ):
            if clave is None:
                m.addSeparator()
                continue
            a = m.addAction(texto)
            a.triggered.connect(lambda _=False, f=fn: f())
            a.setEnabled(hay or clave == "pegar")
            acc[clave] = a
        m._acciones = acc
        return m

    # --- texto en el lugar ------------------------------------------------

    def begin_text_edit(self, layer_id: str, select_all: bool = True) -> bool:
        capa = self.s.doc.layer(layer_id)
        if capa is None or capa.kind != KIND_TEXT or capa.locked:
            return False
        if self._crop:
            return False
        if self._edit:
            self.end_text_edit()
        ed = QPlainTextEdit(self)
        ed.setFrameShape(QPlainTextEdit.NoFrame)
        ed.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed.document().setDocumentMargin(0)
        ed.setPlainText(capa.text)
        ed.installEventFilter(self)
        ed.textChanged.connect(self._editor_changed)
        self._edit = {"id": layer_id, "editor": ed, "start": capa.text}
        self._sync_editor()
        ed.show()
        ed.setFocus()
        if select_all:
            ed.selectAll()
        self.request_render()
        self.editing_changed.emit(True)
        return True

    def is_editing(self) -> bool:
        return self._edit is not None

    def editor(self) -> QPlainTextEdit | None:
        return self._edit["editor"] if self._edit else None

    def _sync_editor(self) -> None:
        """Pone el editor con la letra, el color y el sitio de la capa."""
        if not self._edit:
            return
        capa = self.s.doc.layer(self._edit["id"])
        ed = self._edit["editor"]
        if capa is None:
            return
        t = capa.transform
        f = QFont(capa.font_family)
        f.setPixelSize(max(1, round(capa.font_size * self.zoom)))
        f.setBold(capa.bold)
        f.setItalic(capa.italic)
        f.setUnderline(capa.underline)
        f.setLetterSpacing(QFont.AbsoluteSpacing, capa.letter_spacing * self.zoom)
        f.setCapitalization(QFont.AllUppercase if capa.uppercase else QFont.MixedCase)
        ed.setFont(f)
        ed.setStyleSheet(f"QPlainTextEdit {{ background: transparent; color: {capa.color}; "
                         f"border: none; selection-background-color: {MORADO}; }}")
        opt = ed.document().defaultTextOption()
        opt.setAlignment({"left": Qt.AlignLeft, "center": Qt.AlignHCenter,
                          "right": Qt.AlignRight}.get(capa.align, Qt.AlignHCenter))
        ed.document().setDefaultTextOption(opt)
        tl = self.to_screen(t.cx - t.width / 2, t.cy - t.height / 2)
        ed.setGeometry(round(tl.x()), round(tl.y()), max(20, round(t.width * self.zoom)) + 2,
                       max(20, round(t.height * self.zoom)) + 2)

    def _editor_changed(self) -> None:
        if not self._edit:
            return
        capa = self.s.doc.layer(self._edit["id"])
        if capa is None:
            return
        capa.text = self._edit["editor"].toPlainText()
        self.s.fit_text(capa)
        self.s.touch()

    def end_text_edit(self, commit: bool = True) -> None:
        if not self._edit:
            return
        info, self._edit = self._edit, None
        capa = self.s.doc.layer(info["id"])
        ed = info["editor"]
        ed.removeEventFilter(self)
        ed.hide()
        ed.deleteLater()
        self.editing_changed.emit(False)
        if capa is not None:
            if not commit:
                capa.text = info["start"]
                self.s.fit_text(capa)
                self.s.touch()
            elif not capa.text.strip():
                self.s.selection = [capa.id]
                capa.locked = False
                self.s.delete_selected()
            elif capa.text != info["start"]:
                self.s.commit("Editar texto")
            else:
                self.request_render()
        self.request_render()
        self.update()

    def _drop_editor(self) -> None:
        if self._edit:
            ed = self._edit["editor"]
            self._edit = None
            ed.removeEventFilter(self)
            ed.hide()
            ed.deleteLater()
            self.editing_changed.emit(False)

    def eventFilter(self, obj, ev) -> bool:
        if self._edit and obj is self._edit["editor"]:
            if ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
                self.end_text_edit()
                return True
            if ev.type() == QEvent.FocusOut:
                QTimer.singleShot(0, self._focus_lost)
        return super().eventFilter(obj, ev)

    def _focus_lost(self) -> None:
        if self._edit and not self._edit["editor"].hasFocus():
            self.end_text_edit()

    # --- recortar ---------------------------------------------------------

    def can_crop(self) -> bool:
        capa = self.s.single()
        return capa is not None and capa.kind == KIND_IMAGE and not capa.locked and bool(capa.asset)

    def begin_crop(self, layer_id: str | None = None) -> bool:
        if self._edit:
            self.end_text_edit()
        capa = self.s.doc.layer(layer_id) if layer_id else self.s.single()
        if capa is None or capa.kind != KIND_IMAGE or capa.locked or not capa.asset:
            return False
        if not self.s.store.has(capa.asset):
            return False
        if self._crop:
            self.cancel_crop()
        w, h = self.s.store.size(capa.asset)
        math_ = cropmod.CropMath(capa, (w, h))
        self.s.select([capa.id])
        px = self.s.store.get(capa.asset)
        self._crop = {"id": capa.id, "math": math_, "rect": math_.current_rect(),
                      "ratio": None, "rot0": capa.transform.rotation, "image": to_qimage(px),
                      "drag": None, "straighten": 0.0}
        self.s.set_tool("move")
        self.crop_changed.emit(True)
        self.request_render()
        self.update()
        return True

    def in_crop(self) -> bool:
        return self._crop is not None

    def crop_rect(self):
        return self._crop["rect"] if self._crop else None

    def set_crop_ratio(self, ratio: float | None) -> None:
        c = self._crop
        if not c:
            return
        c["ratio"] = ratio
        if ratio:
            c["rect"] = cropmod.clamp_rect(cropmod.fit_ratio(c["rect"], ratio), c["math"].full_rect())
        self.update()

    def set_straighten(self, degrees: float) -> None:
        c = self._crop
        if not c:
            return
        capa = self.s.doc.layer(c["id"])
        if capa is None:
            return
        c["straighten"] = degrees
        capa.transform.rotation = geo.normalize_angle(c["rot0"] + degrees)
        self.update()

    def apply_crop(self) -> bool:
        c = self._crop
        if not c:
            return False
        capa = self.s.doc.layer(c["id"])
        self._crop = None
        self.crop_changed.emit(False)
        if capa is None:
            self.update()
            return False
        crop, t = c["math"].result(c["rect"])
        w, h = c["math"].iw, c["math"].ih
        if abs(crop[0]) < 0.5 and abs(crop[1]) < 0.5 and abs(crop[2] - w) < 1 and abs(crop[3] - h) < 1:
            crop = None
        # El giro (enderezar) ya está puesto en la capa; la caja nueva conserva ese valor.
        t = replace(t, rotation=capa.transform.rotation)
        cambio = (crop != capa.crop or abs(t.width - capa.transform.width) > 0.01
                  or abs(t.height - capa.transform.height) > 0.01
                  or abs(t.cx - capa.transform.cx) > 0.01 or abs(t.cy - capa.transform.cy) > 0.01
                  or abs(c["straighten"]) > 1e-6)
        crop0 = capa.crop
        capa.crop = crop
        capa.transform = t
        self.s.remap_mask(capa, crop0)
        self.s.renderer.invalidate(capa.id)
        if cambio:
            self.s.commit("Recortar")
        else:
            self.request_render()
        self.update()
        return cambio

    def cancel_crop(self) -> None:
        c = self._crop
        if not c:
            return
        capa = self.s.doc.layer(c["id"])
        if capa is not None:
            capa.transform.rotation = c["rot0"]
        self._crop = None
        self.crop_changed.emit(False)
        self.request_render()
        self.update()

    def _drop_crop(self) -> None:
        if self._crop:
            self._crop = None
            self.crop_changed.emit(False)

    def _crop_handles_local(self):
        x0, y0, x1, y1 = self._crop["rect"]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        return {"nw": (x0, y0), "n": (mx, y0), "ne": (x1, y0), "e": (x1, my),
                "se": (x1, y1), "s": (mx, y1), "sw": (x0, y1), "w": (x0, my)}

    def _crop_local(self, x, y):
        capa = self.s.doc.layer(self._crop["id"])
        return geo.to_local(capa.transform, x, y)

    def _crop_press(self, x, y) -> None:
        c = self._crop
        capa = self.s.doc.layer(c["id"])
        if capa is None:
            return
        lx, ly = self._crop_local(x, y)
        r = HANDLE_HIT * 1.3 / self.zoom
        for name, (hx, hy) in self._crop_handles_local().items():
            if math.hypot(hx - lx, hy - ly) <= r:
                c["drag"] = ("handle", name)
                self._drag = {"kind": "crop"}
                return
        x0, y0, x1, y1 = c["rect"]
        if x0 <= lx <= x1 and y0 <= ly <= y1:
            c["drag"] = ("move", lx, ly, c["rect"])
            self._drag = {"kind": "crop"}

    def _crop_drag(self, x, y) -> None:
        c = self._crop
        if not c or not c["drag"]:
            return
        lx, ly = self._crop_local(x, y)
        bounds = c["math"].full_rect()
        if c["drag"][0] == "handle":
            c["rect"] = cropmod.drag_handle(c["rect"], c["drag"][1], lx, ly, bounds, c["ratio"])
        else:
            _, px0, py0, r0 = c["drag"]
            dx, dy = lx - px0, ly - py0
            c["rect"] = cropmod.clamp_rect((r0[0] + dx, r0[1] + dy, r0[2] + dx, r0[3] + dy), bounds)
        self.update()

    def _paint_crop(self, p: QPainter) -> None:
        c = self._crop
        capa = self.s.doc.layer(c["id"])
        if capa is None:
            return
        m = c["math"]
        t = capa.transform
        p.save()
        o = self.to_screen(t.cx, t.cy)
        p.translate(o)
        p.rotate(t.rotation)
        p.scale(self.zoom, self.zoom)
        fx0, fy0, fx1, fy1 = m.full_rect()
        p.save()
        p.translate((fx0 + fx1) / 2, (fy0 + fy1) / 2)
        p.scale(m.sx, m.sy)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(-(fx1 - fx0) / 2, -(fy1 - fy0) / 2, fx1 - fx0, fy1 - fy0), c["image"])
        p.restore()
        x0, y0, x1, y1 = c["rect"]
        # Todo lo que queda fuera del recorte se atenúa: la foto completa y lo demás del lienzo.
        sombra = QPainterPath()
        gran = 20000.0
        sombra.addRect(QRectF(-gran, -gran, 2 * gran, 2 * gran))
        hueco = QPainterPath()
        hueco.addRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        p.fillPath(sombra.subtracted(hueco), QColor(0, 0, 0, 150))
        px = 1.0 / self.zoom
        p.setPen(QPen(QColor("#ffffff"), 1.5 * px))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1 * px))
        for i in (1, 2):
            p.drawLine(QPointF(x0 + (x1 - x0) * i / 3, y0), QPointF(x0 + (x1 - x0) * i / 3, y1))
            p.drawLine(QPointF(x0, y0 + (y1 - y0) * i / 3), QPointF(x1, y0 + (y1 - y0) * i / 3))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        for name, (hx, hy) in self._crop_handles_local().items():
            if name in ("nw", "ne", "se", "sw"):
                p.drawRoundedRect(QRectF(hx - 6 * px, hy - 6 * px, 12 * px, 12 * px), 3 * px, 3 * px)
            elif name in ("n", "s"):
                p.drawRoundedRect(QRectF(hx - 10 * px, hy - 3 * px, 20 * px, 6 * px), 3 * px, 3 * px)
            else:
                p.drawRoundedRect(QRectF(hx - 3 * px, hy - 10 * px, 6 * px, 20 * px), 3 * px, 3 * px)
        p.restore()
