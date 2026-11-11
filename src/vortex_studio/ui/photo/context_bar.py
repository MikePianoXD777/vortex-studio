"""La barra de arriba del lienzo: cambia según lo que está seleccionado."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.photo.document import KIND_ADJUST, KIND_IMAGE, KIND_SHAPE, KIND_TEXT
from vortex_studio.ui import theme
from vortex_studio.ui.photo import crop as cropmod
from vortex_studio.ui.photo.controls import (
    BAR_SPIN_STYLE,
    ColorButton,
    IconBtn,
    PSlider,
    Segmented,
    separator,
)
from vortex_studio.ui.photo.session import PhotoSession

ALIGN_CYCLE = ("left", "center", "right")
ALIGN_ICON = {"left": "izquierda", "center": "centro", "right": "derecha"}


class SliderPopup(QFrame):
    """Un deslizador que sale bajo un botón (para «Transparencia», «Espaciado»…)."""

    def __init__(self, sliders: list[PSlider], parent=None) -> None:
        super().__init__(parent, Qt.Popup)
        self.setObjectName("sp")
        self.setStyleSheet(f"#sp {{ background:{theme.CAMPO}; border:1px solid {theme.BORDE_FUERTE}; "
                           "border-radius:10px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        for s in sliders:
            lay.addWidget(s)
        self.setMinimumWidth(280)


class PopupButton(IconBtn):
    """Botón que abre un `SliderPopup` con los deslizadores que se le den."""

    def __init__(self, icon: str, tip: str, sliders: list[PSlider], text: str = "") -> None:
        super().__init__(icon, tip, 32, text=text)
        self.sliders = sliders
        # Una sola, hija del botón, desde el principio. Antes cada clic armaba otra (las viejas
        # quedaban vivas) y hasta el primer clic los deslizadores no tenían padre: eran
        # ventanas sueltas cuyas conexiones mantenían viva la ventana de Fotos ya cerrada.
        self.popup = SliderPopup(self.sliders, self)
        self.clicked.connect(self.open_popup)

    def open_popup(self) -> None:
        self.popup.adjustSize()
        self.popup.move(self.mapToGlobal(QPoint(0, self.height() + 4)))
        self.popup.show()


class ContextBar(QWidget):
    open_edit_photo = Signal()
    open_effects = Signal()
    crop_requested = Signal()
    crop_apply = Signal()
    crop_cancel = Signal()
    crop_ratio = Signal(object)
    crop_straighten = Signal(float)

    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        self._syncing = False
        self._crop_mode = False
        self.setFixedHeight(48)
        self.setStyleSheet(f"ContextBar {{ background:{theme.TARJETA}; border-bottom:1px solid {theme.BORDE}; }}")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.pages = QStackedWidget()
        self.p_none = self._page_none()
        self.p_text = self._page_text()
        self.p_image = self._page_image()
        self.p_shape = self._page_shape()
        self.p_multi = self._page_multi()
        self.p_adjust = self._page_adjust()
        self.p_crop = self._page_crop()
        for p in (self.p_none, self.p_text, self.p_image, self.p_shape, self.p_multi,
                  self.p_adjust, self.p_crop):
            self.pages.addWidget(p)

        # Lo de siempre, a la derecha: posición, duplicar, bloquear, borrar.
        self.btn_position = IconBtn("posicion", "Posición", 34, text="Posición")
        self.position_menu = self._build_position_menu()
        self.btn_position.setMenu(self.position_menu)
        self.btn_position.setPopupMode(QToolButton.InstantPopup)
        self.btn_dup = IconBtn("duplicar", "Duplicar (Ctrl+D)", 34)
        self.btn_lock = IconBtn("candado", "Bloquear", 34, checkable=True)
        self.btn_del = IconBtn("basura", "Eliminar (Supr)", 34)
        self.btn_dup.clicked.connect(self.s.duplicate_selected)
        self.btn_lock.clicked.connect(lambda: self.s.lock_selected())
        self.btn_del.clicked.connect(self.s.delete_selected)
        self.always = QWidget()
        al = QHBoxLayout(self.always)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(2)
        for w in (separator(), self.btn_position, self.btn_dup, self.btn_lock, self.btn_del):
            al.addWidget(w)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)
        lay.addWidget(self.pages, 1)
        lay.addWidget(self.always)

        session.selection_changed.connect(self.refresh)
        session.committed.connect(lambda _l: self.refresh())
        session.document_replaced.connect(self.refresh)
        self.refresh()

    # --- construcción de cada página ----------------------------------------------

    @staticmethod
    def _row(*widgets) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        for x in widgets:
            if x is None:
                lay.addStretch(1)
            else:
                lay.addWidget(x)
        lay.addStretch(1)
        return w

    @staticmethod
    def _hint(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{theme.MUY_TENUE}; font-size:12px;")
        return lab

    def _page_none(self) -> QWidget:
        self.lbl_none = self._hint("Haz clic en un elemento para editarlo, o agrega algo desde la barra de la izquierda.")
        return self._row(self.lbl_none)

    def _page_text(self) -> QWidget:
        self.font_box = QFontComboBox()
        self.font_box.setFixedWidth(170)
        self.font_box.setFixedHeight(32)
        self.font_box.currentFontChanged.connect(self._font_changed)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(4, 999)
        self.size_spin.setKeyboardTracking(False)
        self.size_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.size_spin.setStyleSheet(BAR_SPIN_STYLE)
        self.size_spin.setAlignment(Qt.AlignCenter)
        self.size_spin.setFixedSize(62, 32)
        self.size_spin.valueChanged.connect(self._size_changed)
        self.text_color = ColorButton("#ffffff", "Color del texto")
        self.text_color.changed.connect(lambda c: self._text_edit("Color del texto", color=c or "#000000"))
        self.btn_bold = IconBtn("B", "Negrita", 32, checkable=True, letter={"bold": True})
        self.btn_italic = IconBtn("I", "Cursiva", 32, checkable=True, letter={"italic": True})
        self.btn_underline = IconBtn("U", "Subrayado", 32, checkable=True, letter={"underline": True})
        self.btn_upper = IconBtn("Aa", "Mayúsculas", 32, checkable=True)
        self.btn_bold.clicked.connect(lambda on: self._text_edit("Negrita", bold=on))
        self.btn_italic.clicked.connect(lambda on: self._text_edit("Cursiva", italic=on))
        self.btn_underline.clicked.connect(lambda on: self._text_edit("Subrayado", underline=on))
        self.btn_upper.clicked.connect(lambda on: self._text_edit("Mayúsculas", uppercase=on))
        self.btn_align = IconBtn("centro", "Alineación", 32)
        self.btn_align.clicked.connect(self._cycle_align)
        self.sp_letter = PSlider("Letras", -20, 100, 0, suffix=" px")
        self.sp_line = PSlider("Líneas", 0.8, 2.5, 1.2, div=100)
        for sl, attr, label in ((self.sp_letter, "letter_spacing", "Espaciado de letras"),
                                (self.sp_line, "line_height", "Espaciado de líneas")):
            sl.live.connect(lambda v, a=attr: self._text_live(a, v))
            sl.committed.connect(lambda v, lb=label: self._commit_text(lb))
        self.btn_spacing = PopupButton("controles", "Espaciado", [self.sp_letter, self.sp_line], "Espaciado")
        self.btn_text_fx = IconBtn("sombra", "Efectos", 32, text="Efectos")
        self.btn_text_fx.clicked.connect(self.open_effects)
        return self._row(self.font_box, self.size_spin, self.text_color, separator(), self.btn_bold,
                         self.btn_italic, self.btn_underline, self.btn_upper, self.btn_align,
                         self.btn_spacing, self.btn_text_fx)

    def _page_image(self) -> QWidget:
        self.btn_edit_photo = IconBtn("sparkle", "Editar foto", 34, text="Editar foto")
        self.btn_edit_photo.clicked.connect(self.open_edit_photo)
        self.btn_crop = IconBtn("recortar", "Recortar (C)", 34, text="Recortar")
        self.btn_crop.clicked.connect(self.crop_requested)
        self.flip_menu = QMenu(self)
        self.act_flip_h = self.flip_menu.addAction("Voltear horizontalmente")
        self.act_flip_v = self.flip_menu.addAction("Voltear verticalmente")
        self.act_flip_h.triggered.connect(lambda: self.s.flip_selected(True))
        self.act_flip_v.triggered.connect(lambda: self.s.flip_selected(False))
        self.btn_flip = IconBtn("voltear", "Voltear", 34, text="Voltear")
        self.btn_flip.setMenu(self.flip_menu)
        self.btn_flip.setPopupMode(QToolButton.InstantPopup)
        self.img_opacity = PSlider("Transparencia", 0, 100, 100, suffix="%")
        self.img_opacity.live.connect(self._opacity_live)
        self.img_opacity.committed.connect(lambda v: self.s.selected() and self.s.commit("Transparencia"))
        self.btn_img_opacity = PopupButton("fusion", "Transparencia", [self.img_opacity], "Transparencia")
        return self._row(self.btn_edit_photo, self.btn_crop, self.btn_flip, self.btn_img_opacity)

    def _page_shape(self) -> QWidget:
        self.fill_color = ColorButton("#7c5cff", "Relleno", allow_none=True)
        self.stroke_color = ColorButton(None, "Borde", allow_none=True)
        self.fill_color.changed.connect(lambda c: self._shape_edit("Color de relleno", fill=c))
        self.stroke_color.changed.connect(self._stroke_changed)
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(0, 200)
        self.stroke_spin.setSuffix(" px")
        self.stroke_spin.setKeyboardTracking(False)
        self.stroke_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.stroke_spin.setStyleSheet(BAR_SPIN_STYLE)
        self.stroke_spin.setAlignment(Qt.AlignCenter)
        self.stroke_spin.setFixedSize(76, 32)
        self.stroke_spin.setToolTip("Grosor del borde")
        self.stroke_spin.valueChanged.connect(lambda v: self._shape_edit("Grosor del borde", stroke_width=float(v)))
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, 2000)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setKeyboardTracking(False)
        self.radius_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.radius_spin.setStyleSheet(BAR_SPIN_STYLE)
        self.radius_spin.setAlignment(Qt.AlignCenter)
        self.radius_spin.setFixedSize(76, 32)
        self.radius_spin.setToolTip("Esquinas redondeadas")
        self.radius_spin.valueChanged.connect(lambda v: self._shape_edit("Esquinas", corner_radius=float(v)))
        self.lbl_radius = self._hint("Esquinas")
        self.shape_opacity = PSlider("Transparencia", 0, 100, 100, suffix="%")
        self.shape_opacity.live.connect(self._opacity_live)
        self.shape_opacity.committed.connect(lambda v: self.s.selected() and self.s.commit("Transparencia"))
        self.btn_shape_opacity = PopupButton("fusion", "Transparencia", [self.shape_opacity], "Transparencia")
        self.btn_shape_fx = IconBtn("sombra", "Efectos", 32, text="Efectos")
        self.btn_shape_fx.clicked.connect(self.open_effects)
        return self._row(self._hint("Relleno"), self.fill_color, self._hint("Borde"), self.stroke_color,
                         self.stroke_spin, self.lbl_radius, self.radius_spin, self.btn_shape_opacity,
                         self.btn_shape_fx)

    def _page_multi(self) -> QWidget:
        self.lbl_multi = self._hint("")
        return self._row(self.lbl_multi)

    def _page_adjust(self) -> QWidget:
        self.btn_edit_adjust = IconBtn("sparkle", "Editar ajustes", 34, text="Editar ajustes")
        self.btn_edit_adjust.clicked.connect(self.open_edit_photo)
        return self._row(self._hint("Capa de ajuste: corrige todo lo que tiene debajo."), self.btn_edit_adjust)

    def _page_crop(self) -> QWidget:
        self.ratio_seg = Segmented([(k, k) for k in cropmod.RATIOS], "Libre")
        self.ratio_seg.changed.connect(lambda k: self.crop_ratio.emit(cropmod.RATIOS[k]))
        self.straighten = PSlider("Enderezar", -45, 45, 0, suffix="°")
        self.straighten.setFixedWidth(280)
        self.straighten.live.connect(self.crop_straighten)
        self.btn_crop_cancel = QPushButton("Cancelar")
        self.btn_crop_cancel.clicked.connect(self.crop_cancel)
        self.btn_crop_ok = QPushButton("Listo")
        self.btn_crop_ok.setObjectName("primario")
        self.btn_crop_ok.clicked.connect(self.crop_apply)
        return self._row(self._hint("Recortar"), self.ratio_seg, self.straighten, None,
                         self.btn_crop_cancel, self.btn_crop_ok)

    def _build_position_menu(self) -> QMenu:
        m = QMenu(self)
        self.pos_actions = {}
        for clave, texto in (("adelante", "Traer adelante"), ("atras", "Enviar atrás"),
                             ("frente", "Traer al frente"), ("fondo", "Enviar al fondo")):
            a = m.addAction(texto)
            a.triggered.connect(lambda _=False, c=clave: self.s.reorder(c))
            self.pos_actions[clave] = a
        m.addSeparator()
        for clave, texto in (("izquierda", "Alinear a la izquierda"), ("centro", "Centrar horizontalmente"),
                             ("derecha", "Alinear a la derecha"), ("arriba", "Alinear arriba"),
                             ("medio", "Centrar verticalmente"), ("abajo", "Alinear abajo")):
            a = m.addAction(texto)
            a.triggered.connect(lambda _=False, c=clave: self.s.align(c))
            self.pos_actions[clave] = a
        return m

    # --- reflejar la selección ------------------------------------------------------

    def set_crop_mode(self, on: bool) -> None:
        self._crop_mode = on
        if on:
            self.pages.setCurrentWidget(self.p_crop)
            self.always.setEnabled(False)
            self.ratio_seg.set_value("Libre")
            self.straighten.set_value(0)
        else:
            self.always.setEnabled(True)
            self.refresh()

    def refresh(self) -> None:
        if self._crop_mode:
            return
        sel = self.s.selected()
        self._syncing = True
        try:
            self.btn_lock.setChecked(bool(sel) and all(c.locked for c in sel))
            self.btn_lock.icon_name = "candado" if self.btn_lock.isChecked() else "candado_abierto"
            for w in (self.btn_dup, self.btn_lock, self.btn_del, self.btn_position):
                w.setEnabled(bool(sel))
            if not sel:
                self.pages.setCurrentWidget(self.p_none)
            elif len(sel) > 1:
                self.lbl_multi.setText(f"{len(sel)} elementos seleccionados")
                self.pages.setCurrentWidget(self.p_multi)
            else:
                c = sel[0]
                if c.kind == KIND_TEXT:
                    self._fill_text(c)
                    self.pages.setCurrentWidget(self.p_text)
                elif c.kind == KIND_IMAGE:
                    self.img_opacity.set_value(round(c.opacity * 100))
                    self.pages.setCurrentWidget(self.p_image)
                elif c.kind == KIND_SHAPE:
                    self._fill_shape(c)
                    self.pages.setCurrentWidget(self.p_shape)
                else:
                    self.pages.setCurrentWidget(self.p_adjust)
            self.btn_lock.update()
        finally:
            self._syncing = False

    def _fill_text(self, c) -> None:
        f = QFont(c.font_family)
        self.font_box.setCurrentFont(f)
        self.size_spin.setValue(round(c.font_size))
        self.text_color.set_color(c.color)
        self.btn_bold.setChecked(c.bold)
        self.btn_italic.setChecked(c.italic)
        self.btn_underline.setChecked(c.underline)
        self.btn_upper.setChecked(c.uppercase)
        self.btn_align.set_icon(ALIGN_ICON.get(c.align, "centro"))
        self.sp_letter.set_value(c.letter_spacing)
        self.sp_line.set_value(c.line_height)

    def _fill_shape(self, c) -> None:
        self.fill_color.set_color(c.fill)
        self.stroke_color.set_color(c.stroke)
        self.stroke_spin.setValue(round(c.stroke_width))
        self.radius_spin.setValue(round(c.corner_radius))
        rect = c.shape == "rect"
        self.radius_spin.setVisible(rect)
        self.lbl_radius.setVisible(rect)
        self.shape_opacity.set_value(round(c.opacity * 100))

    # --- acciones --------------------------------------------------------------------

    def _text_edit(self, label: str, **attrs) -> None:
        if self._syncing:
            return

        def aplicar(c):
            if c.kind == KIND_TEXT and not c.locked:
                for k, v in attrs.items():
                    setattr(c, k, v)
        self.s.edit(label, aplicar)

    def _font_changed(self, f: QFont) -> None:
        self._text_edit("Fuente", font_family=f.family())

    def _size_changed(self, v: int) -> None:
        self._text_edit("Tamaño de letra", font_size=float(v))

    def _cycle_align(self) -> None:
        sel = self.s.single()
        if sel is None or sel.kind != KIND_TEXT:
            return
        nuevo = ALIGN_CYCLE[(ALIGN_CYCLE.index(sel.align) + 1) % 3] if sel.align in ALIGN_CYCLE else "left"
        self._text_edit("Alineación", align=nuevo)

    def _text_live(self, attr: str, v: float) -> None:
        if self._syncing:
            return
        for c in self.s.selected():
            if c.kind == KIND_TEXT and not c.locked:
                setattr(c, attr, v)
                self.s.fit_text(c)
        self.s.touch()

    def _commit_text(self, label: str) -> None:
        if not self._syncing and self.s.selected():
            self.s.commit(label)

    def _shape_edit(self, label: str, **attrs) -> None:
        if self._syncing:
            return

        def aplicar(c):
            if c.kind == KIND_SHAPE and not c.locked:
                for k, v in attrs.items():
                    setattr(c, k, v)
        self.s.edit(label, aplicar)

    def _stroke_changed(self, color) -> None:
        extra = {}
        sel = self.s.single()
        if color and sel is not None and sel.stroke_width <= 0:
            extra["stroke_width"] = 4.0
        self._shape_edit("Color del borde", stroke=color, **extra)

    def _opacity_live(self, v: float) -> None:
        if self._syncing:
            return
        for c in self.s.selected():
            c.opacity = v / 100.0
        self.s.touch()
