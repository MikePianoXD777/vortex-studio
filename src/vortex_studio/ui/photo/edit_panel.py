"""El panel derecho «Editar foto»: filtros, ajustes y efectos; lo avanzado, detrás de «Más opciones»."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.photo import adjust as photo_adjust
from vortex_studio.photo.document import (
    BLENDS,
    HSL_BANDS,
    KIND_ADJUST,
    KIND_IMAGE,
    KIND_SHAPE,
    KIND_TEXT,
    Adjustments,
    Filter,
    Layer,
)
from vortex_studio.photo.filters import FILTERS, apply_filter
from vortex_studio.photo.render import from_qimage, to_qimage
from vortex_studio.ui import theme
from vortex_studio.ui.photo.controls import (
    MORADO,
    ColorButton,
    IconBtn,
    PSlider,
    Segmented,
    heading,
    muted,
)
from vortex_studio.ui.photo.session import PhotoSession
from vortex_studio.ui.widgets import Collapsible

THUMB_SIDE = 72          # lado de la miniatura de cada filtro
BAND_NAMES = {"red": "Rojos", "orange": "Naranjas", "yellow": "Amarillos", "green": "Verdes",
              "aqua": "Aguas", "blue": "Azules", "purple": "Morados", "magenta": "Magentas"}
BAND_COLORS = {"red": "#ff4d4d", "orange": "#ff9a3c", "yellow": "#ffd93c", "green": "#4cd964",
               "aqua": "#3cd9d0", "blue": "#4d8bff", "purple": "#9b6bff", "magenta": "#ff5cc8"}

# (campo, etiqueta, mínimo, máximo, factor): el deslizador muestra `campo / factor`.
GROUPS = [
    ("Luz", [("exposure", "Exposición", -3, 3, 100), ("contrast", "Contraste", -100, 100, 1),
             ("highlights", "Luces", -100, 100, 1), ("shadows", "Sombras", -100, 100, 1),
             ("whites", "Blancos", -100, 100, 1), ("blacks", "Negros", -100, 100, 1)]),
    ("Color", [("temperature", "Temperatura", -100, 100, 1), ("tint", "Matiz", -100, 100, 1),
               ("vibrance", "Intensidad", -100, 100, 1), ("saturation", "Saturación", -100, 100, 1)]),
    ("Detalle", [("clarity", "Claridad", -100, 100, 1), ("sharpen", "Nitidez", 0, 100, 1),
                 ("blur", "Desenfoque", 0, 100, 1)]),
    ("Efectos", [("vignette", "Viñeta", 0, 100, 1), ("grain", "Grano", 0, 100, 1)]),
]


class CurveEditor(QWidget):
    """La curva maestra: arrastrar puntos; clic en vacío agrega; doble clic quita."""

    live = Signal(list)
    committed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.points: list[tuple[float, float]] = []
        self._drag: int | None = None
        self.setFixedHeight(190)
        self.setMouseTracking(True)

    def set_points(self, pts) -> None:
        self.points = [tuple(p) for p in pts]
        self.update()

    def _full(self) -> list[tuple[float, float]]:
        return sorted(self.points) if self.points else [(0.0, 0.0), (1.0, 1.0)]

    def _rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(8, 8, -8, -8)

    def _to_pt(self, x: float, y: float) -> QPointF:
        r = self._rect()
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _from_pt(self, pt: QPointF) -> tuple[float, float]:
        r = self._rect()
        return (min(max((pt.x() - r.left()) / r.width(), 0.0), 1.0),
                min(max((r.bottom() - pt.y()) / r.height(), 0.0), 1.0))

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.CAMPO))
        p.drawRoundedRect(self.rect(), 8, 8)
        p.setPen(QPen(QColor(theme.BORDE_FUERTE), 1))
        for i in range(1, 4):
            p.drawLine(QPointF(r.left() + r.width() * i / 4, r.top()), QPointF(r.left() + r.width() * i / 4, r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + r.height() * i / 4), QPointF(r.right(), r.top() + r.height() * i / 4))
        pts = self._full()
        path = QPainterPath(self._to_pt(*pts[0]))
        for q in pts[1:]:
            path.lineTo(self._to_pt(*q))
        p.setPen(QPen(QColor(theme.TEXTO), 1.8))
        p.drawPath(path)
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor(MORADO), 1.5))
        for q in self.points:
            p.drawEllipse(self._to_pt(*q), 5, 5)
        p.end()

    def _hit(self, pt: QPointF) -> int | None:
        for i, q in enumerate(self.points):
            c = self._to_pt(*q)
            if (c.x() - pt.x()) ** 2 + (c.y() - pt.y()) ** 2 <= 100:
                return i
        return None

    def mousePressEvent(self, e) -> None:
        pt = e.position()
        i = self._hit(pt)
        if i is None:
            if not self.points:
                self.points = [(0.0, 0.0), (1.0, 1.0)]
            self.points.append(self._from_pt(pt))
            self.points.sort()
            i = self._hit(pt)
        self._drag = i
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is None:
            return
        x, y = self._from_pt(e.position())
        lo = self.points[self._drag - 1][0] + 0.01 if self._drag > 0 else 0.0
        hi = self.points[self._drag + 1][0] - 0.01 if self._drag < len(self.points) - 1 else 1.0
        self.points[self._drag] = (min(max(x, lo), hi), y)
        self.update()
        self.live.emit(self.value())

    def mouseReleaseEvent(self, e) -> None:
        if self._drag is not None:
            self._drag = None
            self.committed.emit(self.value())

    def mouseDoubleClickEvent(self, e) -> None:
        i = self._hit(e.position())
        if i is not None and 0 < i < len(self.points) - 1:
            del self.points[i]
            self.update()
            self.committed.emit(self.value())

    def value(self) -> list[tuple[float, float]]:
        pts = sorted(self.points)
        if len(pts) <= 2 and all(abs(x - y) < 1e-6 for x, y in pts):
            return []
        return pts


def _hsep() -> QLabel:
    lab = QLabel()
    lab.setFixedHeight(8)
    return lab


class EditPanel(QWidget):
    closed = Signal()

    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        self._syncing = False
        self._thumb_key: tuple | None = None
        self._thumb_queue: list[str] = []
        self._thumb_images: dict[str, QPixmap] = {}
        self._base_thumb: QImage | None = None
        self.filter_buttons: dict[str, QToolButton] = {}
        self.sliders: dict[str, PSlider] = {}
        self.group_boxes: dict[str, Collapsible] = {}
        self._pump = QTimer(self)
        self._pump.setInterval(0)
        self._pump.setSingleShot(True)
        self._pump.timeout.connect(self._pump_thumb)

        self.title = heading("Editar foto")
        cerrar = IconBtn("cerrar", "Cerrar", 28)
        cerrar.clicked.connect(self.closed)
        cab = QHBoxLayout()
        cab.addWidget(self.title, 1)
        cab.addWidget(cerrar)

        # Pestañas como píldoras.
        self.tabs = Segmented([("filtros", "Filtros"), ("ajustes", "Ajustes"), ("efectos", "Efectos")],
                              "filtros")
        self.tabs.changed.connect(self._tab_changed)
        self.stack = QStackedWidget()
        self.page_filters = self._build_filters()
        self.page_adjust = self._build_adjust()
        self.page_effects = self._build_effects()
        for p in (self.page_filters, self.page_adjust, self.page_effects):
            self.stack.addWidget(p)

        self.more = Collapsible("Más opciones", *self._build_more())
        self.more_host = QWidget()
        ml = QVBoxLayout(self.more_host)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.more)

        cuerpo = QWidget()
        cl = QVBoxLayout(cuerpo)
        cl.setContentsMargins(0, 10, 4, 14)
        cl.setSpacing(8)
        cl.addWidget(self.stack)
        cl.addWidget(self.more_host)
        cl.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setWidget(cuerpo)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 0)
        lay.setSpacing(8)
        lay.addLayout(cab)
        lay.addWidget(self.tabs)
        lay.addWidget(sa, 1)

        session.selection_changed.connect(self.refresh)
        session.committed.connect(lambda _l: self.refresh())
        session.document_replaced.connect(self.refresh)
        session.tool_changed.connect(self._sync_tools)
        self.refresh()

    # --- construcción -----------------------------------------------------------

    def _build_filters(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        nombres = [("", "Ninguno")] + [(f.id, f.name) for f in FILTERS.values()]
        for i, (fid, nombre) in enumerate(nombres):
            b = QToolButton()
            b.setCheckable(True)
            b.setText(nombre)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(THUMB_SIDE, THUMB_SIDE))
            b.setFixedSize(THUMB_SIDE + 12, THUMB_SIDE + 34)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton {{ background:transparent; border:2px solid transparent; border-radius:10px; "
                f"color:{theme.TENUE}; font-size:11px; padding:2px; }}"
                f"QToolButton:hover {{ color:{theme.TEXTO}; }}"
                f"QToolButton:checked {{ border-color:{MORADO}; color:{theme.TEXTO}; }}")
            b.clicked.connect(lambda _=False, f=fid: self.pick_filter(f))
            self.grid.addWidget(b, i // 3, i % 3)
            self.filter_buttons[fid] = b
        lay.addLayout(self.grid)
        self.intensity = PSlider("Intensidad", 0, 100, 100, suffix="%")
        self.intensity.live.connect(self._intensity_live)
        self.intensity.committed.connect(self._intensity_commit)
        lay.addWidget(self.intensity)
        lay.addStretch(1)
        return w

    def _build_adjust(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.btn_auto = QPushButton("  Mejorar con un clic")
        self.btn_auto.setObjectName("primario")
        self.btn_auto.setIcon(QIcon())
        self.btn_auto.clicked.connect(self.auto_enhance)
        lay.addWidget(self.btn_auto)
        for nombre, campos in GROUPS:
            cuerpo = QWidget()
            cl = QVBoxLayout(cuerpo)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            for campo, etiqueta, lo, hi, factor in campos:
                sl = PSlider(etiqueta, lo, hi, 0, div=1 if factor == 1 else factor)
                sl.live.connect(lambda v, c=campo, f=factor: self._adj_live(c, v * f))
                sl.committed.connect(lambda v, e=etiqueta: self._commit(e))
                self.sliders[campo] = sl
                cl.addWidget(sl)
            reset = QPushButton(f"Restablecer {nombre.lower()}")
            reset.setStyleSheet("padding:4px 8px; font-size:11px;")
            reset.clicked.connect(lambda _=False, n=nombre: self.reset_group(n))
            cl.addWidget(reset)
            box = Collapsible(nombre, cuerpo, abierto=nombre in ("Luz", "Color"))
            self.group_boxes[nombre] = box
            lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _build_effects(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.fx: dict[str, dict] = {}

        def seccion(clave, titulo, color, sliders):
            chk = QCheckBox(titulo)
            chk.toggled.connect(lambda on, k=clave, t=titulo: self._fx_toggle(k, on, t))
            col = ColorButton(color, f"Color de {titulo.lower()}")
            col.changed.connect(lambda c, k=clave, t=titulo: self._fx_attr(k, "color", c or "#000000", t))
            fila = QHBoxLayout()
            fila.addWidget(chk, 1)
            fila.addWidget(col)
            lay.addLayout(fila)
            d = {"check": chk, "color": col, "sliders": {}}
            for attr, etiqueta, lo, hi, escala in sliders:
                sl = PSlider(etiqueta, lo, hi, 0)
                sl.live.connect(lambda v, k=clave, a=attr, e=escala: self._fx_live(k, a, v / e))
                sl.committed.connect(lambda v, t=titulo: self._commit(t))
                lay.addWidget(sl)
                d["sliders"][attr] = (sl, escala)
            self.fx[clave] = d
            lay.addSpacing(8)

        seccion("shadow", "Sombra", "#000000", [("opacity", "Opacidad", 0, 100, 100),
                                               ("blur", "Desenfoque", 0, 80, 1),
                                               ("dx", "Mover →", -80, 80, 1), ("dy", "Mover ↓", -80, 80, 1)])
        seccion("outline", "Contorno", "#ffffff", [("width", "Grosor", 1, 40, 1)])
        seccion("glow", "Brillo", "#ffffff", [("opacity", "Opacidad", 0, 100, 100),
                                             ("radius", "Radio", 1, 80, 1)])
        lay.addStretch(1)
        return w

    def _build_more(self) -> list[QWidget]:
        # Curva
        self.curve = CurveEditor()
        self.curve.live.connect(self._curve_live)
        self.curve.committed.connect(self._curve_commit)
        reset_curve = QPushButton("Restablecer curva")
        reset_curve.clicked.connect(lambda: (self.curve.set_points([]), self._curve_commit([])))
        curva = QWidget()
        cl = QVBoxLayout(curva)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(muted("Clic para agregar un punto; doble clic para quitarlo."))
        cl.addWidget(self.curve)
        cl.addWidget(reset_curve)
        # HSL
        self.band = QComboBox()
        for b in HSL_BANDS:
            self.band.addItem(BAND_NAMES[b], b)
        self.band.currentIndexChanged.connect(lambda _i: self._fill_hsl())
        self.hsl = [PSlider("Tono", -100, 100, 0), PSlider("Saturación", -100, 100, 0),
                    PSlider("Luminosidad", -100, 100, 0)]
        for i, sl in enumerate(self.hsl):
            sl.live.connect(lambda v, k=i: self._hsl_live(k, v))
            sl.committed.connect(lambda v: self._commit("Color por franja"))
        hsl = QWidget()
        hl = QVBoxLayout(hsl)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.band)
        for sl in self.hsl:
            hl.addWidget(sl)
        # Fusión
        self.blend = QComboBox()
        self.blend.addItems(BLENDS)
        self.blend.activated.connect(lambda _i: self.s.edit("Modo de fusión", lambda c: setattr(c, "blend", self.blend.currentText())))
        fus = QWidget()
        fl = QVBoxLayout(fus)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.blend)
        # Máscara
        self.btn_mask_paint = IconBtn("pincel", "Pintar la máscara: revela", 36, checkable=True, text="Pintar")
        self.btn_mask_erase = IconBtn("borrador", "Borrar con la máscara: oculta", 36, checkable=True, text="Borrar")
        self.btn_wand = IconBtn("varita", "Varita mágica", 36, checkable=True, text="Varita")
        self.btn_mask_paint.clicked.connect(lambda: self._tool("mask_paint"))
        self.btn_mask_erase.clicked.connect(lambda: self._tool("mask_erase"))
        self.btn_wand.clicked.connect(lambda: self._tool("wand"))
        self.wand_tol = PSlider("Tolerancia", 0, 100, self.s.wand_tolerance)
        self.wand_tol.live.connect(lambda v: setattr(self.s, "wand_tolerance", float(v)))
        self.wand_mode = Segmented([(False, "Ocultar lo que toca"), (True, "Conservar lo que toca")], False)
        self.wand_mode.changed.connect(lambda k: setattr(self.s, "wand_keep", bool(k)))
        self.wand_contig = QCheckBox("Solo la zona conectada")
        self.wand_contig.setChecked(True)
        self.wand_contig.toggled.connect(lambda on: setattr(self.s, "wand_contiguous", on))
        self.btn_remove_bg = QPushButton("Quitar fondo")
        self.btn_remove_bg.clicked.connect(self.s.remove_background)
        self.btn_clear_mask = QPushButton("Quitar la máscara")
        self.btn_clear_mask.clicked.connect(self.s.clear_mask)
        fila = QHBoxLayout()
        for b in (self.btn_mask_paint, self.btn_mask_erase, self.btn_wand):
            fila.addWidget(b)
        mask = QWidget()
        ml = QVBoxLayout(mask)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addLayout(fila)
        ml.addWidget(self.wand_tol)
        ml.addWidget(self.wand_mode)
        ml.addWidget(self.wand_contig)
        ml.addWidget(self.btn_remove_bg)
        ml.addWidget(self.btn_clear_mask)
        # Tampón y capa de ajuste
        self.btn_clone = IconBtn("tampon", "Tampón de clonar", 36, checkable=True, text="Tampón de clonar")
        self.btn_clone.clicked.connect(lambda: self._tool("clone"))
        self.btn_add_adjust = QPushButton("Agregar capa de ajuste")
        self.btn_add_adjust.clicked.connect(self.s.add_adjustment_layer)
        extra = QWidget()
        el = QVBoxLayout(extra)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(self.btn_clone)
        el.addWidget(muted("Alt + clic para elegir de dónde copiar; luego pinta encima de lo que quieras tapar."))
        el.addWidget(self.btn_add_adjust)

        def sub(t, w):
            return Collapsible(t, w)
        self.sub_curve, self.sub_hsl = sub("Curva", curva), sub("Color por franja", hsl)
        self.sub_blend, self.sub_mask = sub("Modo de fusión", fus), sub("Máscara", mask)
        self.sub_extra = sub("Retoque y capas", extra)
        return [self.sub_curve, self.sub_hsl, self.sub_blend, self.sub_mask, self.sub_extra]

    # --- el objetivo --------------------------------------------------------------

    def target(self) -> Layer | None:
        c = self.s.single()
        return c if c is not None and c.kind in (KIND_IMAGE, KIND_ADJUST) else None

    def fx_target(self) -> Layer | None:
        return self.s.single()

    def refresh(self) -> None:
        c = self.s.single()
        self._syncing = True
        try:
            if c is None:
                return
            es_foto = c.kind in (KIND_IMAGE, KIND_ADJUST)
            self.title.setText("Editar foto" if c.kind == KIND_IMAGE else
                               "Capa de ajuste" if c.kind == KIND_ADJUST else "Efectos")
            self.tabs.buttons["filtros"].setVisible(es_foto)
            self.tabs.buttons["ajustes"].setVisible(es_foto)
            self.tabs.buttons["efectos"].setVisible(c.kind != KIND_ADJUST)
            if not es_foto and self.tabs.value() != "efectos":
                self.tabs.set_value("efectos")
                self.stack.setCurrentWidget(self.page_effects)
            if c.kind == KIND_ADJUST and self.tabs.value() == "efectos":
                self.tabs.set_value("ajustes")
                self.stack.setCurrentWidget(self.page_adjust)
            self.more_host.setVisible(c.kind == KIND_IMAGE or c.kind == KIND_ADJUST)
            self.sub_mask.setVisible(c.kind == KIND_IMAGE)
            self.sub_extra.setVisible(c.kind == KIND_IMAGE)
            self.sub_blend.setVisible(True)
            self.btn_auto.setVisible(c.kind == KIND_IMAGE or c.kind == KIND_ADJUST)
            if es_foto:
                a = c.adjustments
                for campo, sl in self.sliders.items():
                    f = next(f for _n, cs in GROUPS for cc, _e, _l, _h, f in cs if cc == campo)
                    sl.set_value(getattr(a, campo) / f)
                self.curve.set_points(a.curve)
                self._fill_hsl()
                self.blend.setCurrentText(c.blend)
                self._mark_filter(c.filter)
                self._prepare_thumbs(c)
            self._fill_fx(c)
            self._sync_tools(self.s.tool)
        finally:
            self._syncing = False

    def _tab_changed(self, key) -> None:
        self.stack.setCurrentWidget({"filtros": self.page_filters, "ajustes": self.page_adjust,
                                     "efectos": self.page_effects}[key])

    def show_tab(self, key: str) -> None:
        self.tabs.set_value(key)
        self._tab_changed(key)

    def _commit(self, label: str) -> None:
        if not self._syncing and self.s.selection:
            self.s.commit(label)

    # --- filtros ----------------------------------------------------------------------

    def _mark_filter(self, flt: Filter) -> None:
        actual = flt.name if not flt.is_off() else ""
        for fid, b in self.filter_buttons.items():
            b.setChecked(fid == actual)
        self.intensity.set_value(flt.intensity if flt.name else 100)
        self.intensity.setEnabled(bool(flt.name))

    def pick_filter(self, fid: str) -> None:
        c = self.target()
        if c is None or c.locked:
            return
        nombre = FILTERS[fid].name if fid else "ninguno"
        c.filter = Filter(fid, self.intensity.value() if fid and c.filter.name else 100.0) if fid else Filter()
        self._mark_filter(c.filter)
        self.s.commit(f"Filtro {nombre}")

    def _intensity_live(self, v: float) -> None:
        c = self.target()
        if c is not None and not self._syncing and c.filter.name:
            c.filter.intensity = v
            self.s.touch()

    def _intensity_commit(self, v: float) -> None:
        c = self.target()
        if c is not None and not self._syncing and c.filter.name:
            self.s.commit("Intensidad del filtro")

    def _prepare_thumbs(self, c: Layer) -> None:
        """Las miniaturas se hacen una vez por foto (y recorte), una por turno del bucle de eventos."""
        if c.kind != KIND_IMAGE or not c.asset or not self.s.store.has(c.asset):
            return
        key = (c.asset, c.crop)
        if key == self._thumb_key:
            return
        self._thumb_key = key
        self._thumb_images = {}
        px = self.s.store.get(c.asset)
        if c.crop:
            x, y, w, h = (int(round(v)) for v in c.crop)
            px = px[max(0, y): y + max(1, h), max(0, x): x + max(1, w)]
        img = to_qimage(np.ascontiguousarray(px))
        lado = THUMB_SIDE * 2
        self._base_thumb = img.scaled(lado, lado, Qt.KeepAspectRatioByExpanding,
                                      Qt.SmoothTransformation)
        self._thumb_queue = [""] + list(FILTERS)
        for fid, b in self.filter_buttons.items():
            b.setIcon(QIcon())
        self._pump.start()

    def _pump_thumb(self) -> None:
        if not self._thumb_queue or self._base_thumb is None:
            return
        fid = self._thumb_queue.pop(0)
        img = self._base_thumb
        w, h = img.width(), img.height()
        cuadro = img.copy((w - min(w, h)) // 2, (h - min(w, h)) // 2, min(w, h), min(w, h))
        if fid:
            try:
                px = apply_filter(from_qimage(cuadro), Filter(fid, 100.0), 1.0)
                cuadro = to_qimage(px)
            except Exception:
                pass
        pm = QPixmap.fromImage(cuadro.scaled(THUMB_SIDE * 2, THUMB_SIDE * 2, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
        pm.setDevicePixelRatio(2.0)
        self._thumb_images[fid] = pm
        self.filter_buttons[fid].setIcon(QIcon(pm))
        if self._thumb_queue:
            self._pump.start()

    def thumbs_ready(self) -> bool:
        return not self._thumb_queue and bool(self._thumb_images)

    # --- ajustes ------------------------------------------------------------------------

    def _adj_live(self, campo: str, valor: float) -> None:
        c = self.target()
        if c is None or self._syncing or c.locked:
            return
        setattr(c.adjustments, campo, float(valor))
        self.s.renderer.invalidate(c.id)
        self.s.touch()

    def reset_group(self, nombre: str) -> None:
        c = self.target()
        if c is None or c.locked:
            return
        campos = dict(GROUPS)[nombre]
        if all(getattr(c.adjustments, campo) == 0 for campo, *_ in campos):
            return
        for campo, *_ in campos:
            setattr(c.adjustments, campo, 0.0)
        self.s.renderer.invalidate(c.id)
        self.s.commit(f"Restablecer {nombre.lower()}")

    def auto_enhance(self) -> None:
        c = self.target()
        if c is None or c.locked:
            return
        if c.kind == KIND_IMAGE and c.asset and self.s.store.has(c.asset):
            px = self.s.store.get(c.asset)
            if c.crop:
                x, y, w, h = (int(round(v)) for v in c.crop)
                px = px[max(0, y): y + max(1, h), max(0, x): x + max(1, w)]
            paso = max(1, max(px.shape[:2]) // 512)
            adj = photo_adjust.auto_enhance(np.ascontiguousarray(px[::paso, ::paso]))
        else:
            adj = photo_adjust.auto_enhance(np.zeros((8, 8, 4), np.uint8))
        c.adjustments = adj
        self.s.renderer.invalidate(c.id)
        self.s.commit("Mejorar con un clic")

    # --- curva y HSL --------------------------------------------------------------------

    def _curve_live(self, pts: list) -> None:
        c = self.target()
        if c is not None and not self._syncing and not c.locked:
            c.adjustments.curve = [tuple(p) for p in pts]
            self.s.touch()

    def _curve_commit(self, pts: list) -> None:
        c = self.target()
        if c is not None and not self._syncing and not c.locked:
            c.adjustments.curve = [tuple(p) for p in pts]
            self.s.commit("Curva")

    def _band(self) -> str:
        return self.band.currentData() or HSL_BANDS[0]

    def _fill_hsl(self) -> None:
        c = self.target()
        h, s, l = (c.adjustments.hsl.get(self._band(), (0.0, 0.0, 0.0)) if c else (0, 0, 0))
        for sl, v in zip(self.hsl, (h, s, l)):
            sl.set_value(v)

    def _hsl_live(self, idx: int, v: float) -> None:
        c = self.target()
        if c is None or self._syncing or c.locked:
            return
        cur = list(c.adjustments.hsl.get(self._band(), (0.0, 0.0, 0.0)))
        cur[idx] = float(v)
        if any(cur):
            c.adjustments.hsl[self._band()] = tuple(cur)
        else:
            c.adjustments.hsl.pop(self._band(), None)
        self.s.touch()

    # --- efectos -------------------------------------------------------------------------

    def _fill_fx(self, c: Layer) -> None:
        for clave, d in self.fx.items():
            efecto = getattr(c.effects, clave)
            d["check"].setChecked(efecto.enabled)
            d["color"].set_color(efecto.color)
            for attr, (sl, escala) in d["sliders"].items():
                sl.set_value(getattr(efecto, attr) * escala)

    def _fx_toggle(self, clave: str, on: bool, titulo: str) -> None:
        c = self.fx_target()
        if c is None or self._syncing or c.locked:
            return
        getattr(c.effects, clave).enabled = on
        self.s.renderer.invalidate(c.id)
        self.s.commit(titulo if on else f"Quitar {titulo.lower()}")

    def _fx_attr(self, clave: str, attr: str, valor, titulo: str) -> None:
        c = self.fx_target()
        if c is None or self._syncing or c.locked:
            return
        e = getattr(c.effects, clave)
        setattr(e, attr, valor)
        e.enabled = True
        self.s.renderer.invalidate(c.id)
        self.s.commit(titulo)

    def _fx_live(self, clave: str, attr: str, valor: float) -> None:
        c = self.fx_target()
        if c is None or self._syncing or c.locked:
            return
        e = getattr(c.effects, clave)
        setattr(e, attr, float(valor))
        e.enabled = True
        self.s.touch()

    # --- herramientas de la máscara y el tampón ---------------------------------------------

    def _tool(self, tool: str) -> None:
        self.s.set_tool("move" if self.s.tool == tool else tool)
        self._sync_tools(self.s.tool)

    def _sync_tools(self, tool: str) -> None:
        for b, t in ((self.btn_mask_paint, "mask_paint"), (self.btn_mask_erase, "mask_erase"),
                     (self.btn_wand, "wand"), (self.btn_clone, "clone")):
            b.setChecked(tool == t)
