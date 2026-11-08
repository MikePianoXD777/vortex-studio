"""La ventana de Vortex Photo (el modo Fotos de Vortex Studio).

Canva por fuera, Photoshop por dentro: barra de íconos a la izquierda con sus
paneles, barra contextual sobre el lienzo, y a la derecha «Editar foto», que
solo aparece cuando se pide. Todo el trabajo real vive en `PhotoSession`; esta
clase solo arma los trozos y los conecta.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.photo import io as photo_io
from vortex_studio.photo import templates
from vortex_studio.photo.document import KIND_ADJUST, KIND_IMAGE, KIND_SHAPE, KIND_TEXT
from vortex_studio.ui import theme
from vortex_studio.ui.photo.canvas import CanvasView
from vortex_studio.ui.photo.context_bar import ContextBar
from vortex_studio.ui.photo.controls import MORADO, IconBtn
from vortex_studio.ui.photo.dialogs import (
    BatchDialog,
    ExportPopup,
    NewDesignDialog,
    ResizeDialog,
    _Worker,
)
from vortex_studio.ui.photo.edit_panel import EditPanel
from vortex_studio.ui.photo.icons import draw_icon
from vortex_studio.ui.photo.layers_panel import LayersPanel
from vortex_studio.ui.photo.panels import (
    DesignPanel,
    DrawPanel,
    ElementsPanel,
    TextPanel,
    UploadPanel,
)
from vortex_studio.ui.photo.session import PhotoSession

SIDEBAR = (("diseno", "Diseño"), ("subir", "Subir"), ("texto", "Texto"),
           ("elementos", "Elementos"), ("dibujar", "Dibujar"), ("capas", "Capas"))
SAVE_FILTER = "Diseño de Vortex Photo (*.vphoto)"
OPEN_ALL = f"Diseños e imágenes (*.vphoto *.png *.jpg *.jpeg *.webp *.bmp *.gif);;{photo_io.OPEN_FILTER};;{SAVE_FILTER}"
EXT = {"PNG": ".png", "JPG": ".jpg", "WEBP": ".webp"}


class SideButton(QToolButton):
    """Ícono con su nombre debajo, como la barra de Canva."""

    def __init__(self, icon: str, text: str) -> None:
        super().__init__()
        self.icon_name = icon
        self._text = text
        self.setCheckable(True)
        self.setFixedSize(68, 62)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 3, -4, -3)
        if self.isChecked() or self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.PILDORA if self.isChecked() else theme.PILDORA_HOVER))
            p.drawRoundedRect(r, 10, 10)
        color = QColor(theme.TEXTO if self.isChecked() or self._hover else theme.TENUE)
        draw_icon(p, self.icon_name, QRectF(r.center().x() - 11, r.top() + 8, 22, 22), color)
        f = p.font()
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(color)
        p.drawText(QRectF(r.left(), r.top() + 33, r.width(), 18), Qt.AlignCenter, self._text)
        p.end()


class PhotoWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(theme.WINDOW_STYLE)
        self.resize(1440, 860)
        self.setMinimumSize(980, 600)
        self.setAcceptDrops(False)
        self.session = PhotoSession()
        s = self.session
        self._export_worker: _Worker | None = None
        self._edit_open = False
        self.last_export: str | None = None

        # --- piezas ---
        self.canvas = CanvasView(s)
        self.context = ContextBar(s)
        self.layers_panel = LayersPanel(s)
        self.design_panel = DesignPanel(s)
        self.upload_panel = UploadPanel(s)
        self.text_panel = TextPanel(s)
        self.elements_panel = ElementsPanel(s)
        self.draw_panel = DrawPanel(s)
        self.edit_panel = EditPanel(s)
        self.export_popup = ExportPopup(s, self)

        self.panels = {"diseno": self.design_panel, "subir": self.upload_panel, "texto": self.text_panel,
                       "elementos": self.elements_panel, "dibujar": self.draw_panel,
                       "capas": self.layers_panel}
        self.left_stack = QStackedWidget()
        for p in self.panels.values():
            self.left_stack.addWidget(p)
        self.left_frame = QFrame()
        self.left_frame.setObjectName("panelizq")
        self.left_frame.setFixedWidth(292)
        self.left_frame.setStyleSheet(
            f"#panelizq {{ background:{theme.TARJETA}; border-right:1px solid {theme.BORDE}; }}")
        lf = QVBoxLayout(self.left_frame)
        lf.setContentsMargins(0, 0, 0, 0)
        lf.addWidget(self.left_stack)

        self.right_frame = QFrame()
        self.right_frame.setObjectName("panelder")
        self.right_frame.setFixedWidth(318)
        self.right_frame.setStyleSheet(
            f"#panelder {{ background:{theme.TARJETA}; border-left:1px solid {theme.BORDE}; }}")
        rf = QVBoxLayout(self.right_frame)
        rf.setContentsMargins(0, 0, 0, 0)
        rf.addWidget(self.edit_panel)
        self.right_frame.hide()

        self.sidebar = QFrame()
        self.sidebar.setObjectName("barraizq")
        self.sidebar.setFixedWidth(76)
        self.sidebar.setStyleSheet(
            f"#barraizq {{ background:{theme.FONDO}; border-right:1px solid {theme.BORDE}; }}")
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(4, 8, 4, 8)
        sl.setSpacing(4)
        self.side_buttons: dict[str, SideButton] = {}
        for clave, texto in SIDEBAR:
            b = SideButton(clave, texto)
            b.clicked.connect(lambda _=False, k=clave: self.toggle_panel(k))
            sl.addWidget(b, 0, Qt.AlignHCenter)
            self.side_buttons[clave] = b
        sl.addStretch(1)

        centro = QWidget()
        cl = QVBoxLayout(centro)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.context)
        cl.addWidget(self.canvas, 1)
        cl.addWidget(self._build_bottom())

        cuerpo = QWidget()
        bl = QHBoxLayout(cuerpo)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self.sidebar)
        bl.addWidget(self.left_frame)
        bl.addWidget(centro, 1)
        bl.addWidget(self.right_frame)

        raiz = QWidget()
        rl = QVBoxLayout(raiz)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_top())
        rl.addWidget(cuerpo, 1)
        self.setCentralWidget(raiz)

        self._build_actions()
        self._connect()
        self.show_panel("subir")
        self._refresh_all()

    # --- armado ---------------------------------------------------------------------

    def _build_top(self) -> QWidget:
        top = QFrame()
        top.setObjectName("barra")
        top.setFixedHeight(54)
        top.setStyleSheet(f"#barra {{ background:{theme.FONDO}; border-bottom:1px solid {theme.BORDE}; }}")
        lay = QHBoxLayout(top)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)
        marca = QLabel("Vortex Photo")
        marca.setStyleSheet(f"color:{theme.TEXTO}; font-size:14px; font-weight:700; padding-right:8px;")
        lay.addWidget(marca)
        self.btn_file = IconBtn("archivo", "Archivo", 34, text="Archivo")
        self.file_menu = QMenu(self)
        self.btn_file.setMenu(self.file_menu)
        self.btn_file.setPopupMode(QToolButton.InstantPopup)
        lay.addWidget(self.btn_file)
        self.name_edit = QLineEdit()
        self.name_edit.setFixedWidth(230)
        self.name_edit.setFixedHeight(34)
        self.name_edit.setPlaceholderText("Nombre del diseño")
        self.name_edit.editingFinished.connect(self._name_done)
        lay.addWidget(self.name_edit)
        self.btn_undo = IconBtn("deshacer", "Deshacer (Ctrl+Z)", 34)
        self.btn_redo = IconBtn("rehacer", "Rehacer (Ctrl+Shift+Z)", 34)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        lay.addWidget(self.btn_undo)
        lay.addWidget(self.btn_redo)
        self.btn_resize = IconBtn("reglas", "Cambiar el tamaño del diseño", 34, text="Cambiar tamaño")
        self.btn_resize.clicked.connect(self.show_resize)
        lay.addWidget(self.btn_resize)
        lay.addStretch(1)
        self.btn_compare = IconBtn("ojo", "Mantén pulsado para ver el original  (\\)", 34)
        self.btn_compare.pressed.connect(lambda: self.canvas.set_show_original(True))
        self.btn_compare.released.connect(lambda: self.canvas.set_show_original(False))
        lay.addWidget(self.btn_compare)
        self.btn_export = QPushButton("Exportar")
        self.btn_export.setObjectName("primario")
        self.btn_export.setFixedHeight(34)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.show_export)
        lay.addWidget(self.btn_export)
        return top

    def _build_bottom(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("pie")
        bar.setFixedHeight(34)
        bar.setStyleSheet(f"#pie {{ background:{theme.FONDO}; border-top:1px solid {theme.BORDE}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(4)
        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{theme.MUY_TENUE}; font-size:11px;")
        lay.addWidget(self.status, 1)
        self.btn_zoom_out = IconBtn("menos", "Alejar (Ctrl+−)", 26)
        self.zoom_label = QPushButton("50 %")
        self.zoom_label.setFlat(True)
        self.zoom_label.setFixedWidth(58)
        self.zoom_label.setToolTip("Zoom actual. Clic para ajustar a la ventana (Ctrl+0)")
        self.zoom_label.setStyleSheet(f"border:none; background:transparent; color:{theme.TENUE};")
        self.btn_zoom_in = IconBtn("mas", "Acercar (Ctrl++)", 26)
        self.btn_fit = IconBtn("ajustar", "Ajustar a la ventana (Ctrl+0)", 26)
        self.btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        self.btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        self.btn_fit.clicked.connect(self.canvas.fit)
        self.zoom_label.clicked.connect(self.canvas.fit)
        for w in (self.btn_zoom_out, self.zoom_label, self.btn_zoom_in, self.btn_fit):
            lay.addWidget(w)
        return bar

    def _action(self, name: str, text: str, keys, fn, context=Qt.WindowShortcut) -> QAction:
        a = QAction(text, self)
        seqs = [keys] if isinstance(keys, (str, QKeySequence)) else list(keys)
        a.setShortcuts([QKeySequence(k) for k in seqs] if seqs else [])
        a.setShortcutContext(context)
        a.triggered.connect(lambda _=False: fn())
        self.addAction(a)
        self.actions_by_name[name] = a
        return a

    def _build_actions(self) -> None:
        self.actions_by_name: dict[str, QAction] = {}
        A = self._action
        s = self.session
        A("undo", "Deshacer", ["Ctrl+Z"], self.undo)
        A("redo", "Rehacer", ["Ctrl+Shift+Z", "Ctrl+Y"], self.redo)
        A("copy", "Copiar", ["Ctrl+C"], s.copy_selected)
        A("cut", "Cortar", ["Ctrl+X"], s.cut_selected)
        A("paste", "Pegar", ["Ctrl+V"], self.paste)
        A("duplicate", "Duplicar", ["Ctrl+D"], s.duplicate_selected)
        A("delete", "Eliminar", ["Delete"], s.delete_selected)
        A("select_all", "Seleccionar todo", ["Ctrl+A"], s.select_all)
        A("save", "Guardar", ["Ctrl+S"], self.save)
        A("save_as", "Guardar como…", ["Ctrl+Shift+S"], self.save_as)
        A("export", "Exportar…", ["Ctrl+E"], self.show_export)
        A("new", "Nuevo diseño…", ["Ctrl+N"], self.show_new)
        A("open", "Abrir…", ["Ctrl+O"], self.open_dialog)
        A("fit", "Ajustar a la ventana", ["Ctrl+0"], self.canvas.fit)
        A("zoom100", "Zoom 100 %", ["Ctrl+1"], self.canvas.zoom_100)
        A("zoom_in", "Acercar", ["Ctrl++", "Ctrl+="], self.canvas.zoom_in)
        A("zoom_out", "Alejar", ["Ctrl+-"], self.canvas.zoom_out)
        A("tool_move", "Mover", ["V"], lambda: s.set_tool("move"))
        A("tool_brush", "Pincel", ["B"], lambda: self._tool_key("brush"))
        A("tool_erase", "Borrador", ["E"], lambda: self._tool_key("erase"))
        A("text", "Texto", ["T"], self.add_text_and_edit)
        A("crop", "Recortar", ["C"], self.start_crop)
        A("escape", "Salir del modo", ["Esc"], self.escape)

        fm = self.file_menu
        self.new_size_menu = fm.addMenu("Nuevo diseño")
        self.new_size_actions = []
        for g, nombre, w, h in templates.SIZES:
            a = self.new_size_menu.addAction(f"{nombre}  ({w} × {h})")
            a.triggered.connect(lambda _=False, a_=w, b_=h: self.new_design(a_, b_))
            self.new_size_actions.append(a)
        self.new_size_menu.addSeparator()
        self.new_size_menu.addAction("Tamaño personalizado…").triggered.connect(self.show_new)
        fm.addAction(self.actions_by_name["open"])
        fm.addSeparator()
        fm.addAction(self.actions_by_name["save"])
        fm.addAction(self.actions_by_name["save_as"])
        fm.addAction(self.actions_by_name["export"])
        fm.addSeparator()
        fm.addAction("Editar en lote…").triggered.connect(self.show_batch)

    def _connect(self) -> None:
        s, c, ctx = self.session, self.canvas, self.context
        s.committed.connect(lambda _l: self._refresh_all())
        s.selection_changed.connect(self._selection_changed)
        s.document_replaced.connect(self._refresh_all)
        s.message.connect(self.say)
        c.zoom_changed.connect(lambda z: self.zoom_label.setText(f"{round(z * 100)} %"))
        c.files_dropped.connect(self.add_files)
        c.image_dropped.connect(self._image_dropped)
        c.crop_changed.connect(ctx.set_crop_mode)
        c.crop_changed.connect(lambda on: self.right_frame.setVisible(False if on else self._edit_open))
        ctx.crop_requested.connect(self.start_crop)
        ctx.crop_apply.connect(c.apply_crop)
        ctx.crop_cancel.connect(c.cancel_crop)
        ctx.crop_ratio.connect(c.set_crop_ratio)
        ctx.crop_straighten.connect(c.set_straighten)
        ctx.open_edit_photo.connect(lambda: self.open_edit("filtros" if (s.single() and s.single().kind == KIND_IMAGE) else "ajustes"))
        ctx.open_effects.connect(lambda: self.open_edit("efectos"))
        self.edit_panel.closed.connect(self.close_edit)
        self.design_panel.custom_size_requested.connect(self.show_resize)
        self.upload_panel.pick_requested.connect(self.pick_images)
        self.export_popup.requested.connect(self._export_flow)
        s.tool_changed.connect(lambda t: self._tool_sidebar(t))

    # --- paneles ----------------------------------------------------------------------

    def show_panel(self, clave: str) -> None:
        self.left_stack.setCurrentWidget(self.panels[clave])
        self.left_frame.show()
        for k, b in self.side_buttons.items():
            b.setChecked(k == clave)

    def toggle_panel(self, clave: str) -> None:
        if self.left_frame.isVisible() and self.left_stack.currentWidget() is self.panels[clave]:
            self.left_frame.hide()
            self.side_buttons[clave].setChecked(False)
        else:
            self.show_panel(clave)

    def _tool_sidebar(self, tool: str) -> None:
        if tool in ("brush", "erase"):
            self.show_panel("dibujar")

    def open_edit(self, tab: str = "filtros") -> None:
        c = self.session.single()
        if c is None:
            return
        self._edit_open = True
        self.edit_panel.refresh()
        self.edit_panel.show_tab(tab if tab != "filtros" or c.kind == KIND_IMAGE else "ajustes")
        if c.kind in (KIND_TEXT, KIND_SHAPE):
            self.edit_panel.show_tab("efectos")
        self.right_frame.setVisible(not self.canvas.in_crop())

    def close_edit(self) -> None:
        self._edit_open = False
        self.right_frame.hide()

    def _selection_changed(self) -> None:
        c = self.session.single()
        if self._edit_open and c is None:
            self.close_edit()
        elif self._edit_open:
            self.edit_panel.refresh()
        self._refresh_all()

    # --- estado --------------------------------------------------------------------------

    def _refresh_all(self) -> None:
        s = self.session
        h = s.history
        self.btn_undo.setEnabled(h.can_undo)
        self.btn_redo.setEnabled(h.can_redo)
        self.btn_undo.setToolTip(f"Deshacer: {h.undo_label}  (Ctrl+Z)" if h.can_undo else "Deshacer (Ctrl+Z)")
        self.btn_redo.setToolTip(f"Rehacer: {h.redo_label}  (Ctrl+Shift+Z)" if h.can_redo else "Rehacer")
        if not self.name_edit.hasFocus():
            self.name_edit.setText(s.doc.name)
        self.setWindowTitle(f"{'*' if s.dirty else ''}{s.doc.name} — Vortex Photo")
        n = len(s.doc.layers)
        self.say(f"{s.doc.width} × {s.doc.height} px   ·   {n} capa{'s' if n != 1 else ''}", keep=True)

    def say(self, text: str, keep: bool = False) -> None:
        self.status.setText(text)
        if not keep:
            QTimer.singleShot(4000, self._refresh_status)

    def _refresh_status(self) -> None:
        s = self.session
        n = len(s.doc.layers)
        self.status.setText(f"{s.doc.width} × {s.doc.height} px   ·   {n} capa{'s' if n != 1 else ''}")

    def _name_done(self) -> None:
        self.session.rename(self.name_edit.text())

    # --- acciones de edición ----------------------------------------------------------------

    def undo(self) -> None:
        self.canvas.end_text_edit()
        if self.canvas.in_crop():
            self.canvas.cancel_crop()
        self.session.undo()

    def redo(self) -> None:
        self.canvas.end_text_edit()
        self.session.redo()

    def paste(self) -> None:
        if not self.session.paste():
            self.say("No hay nada que pegar")

    def _tool_key(self, tool: str) -> None:
        if self.canvas.is_editing():
            return
        self.session.set_tool(tool)

    def add_text_and_edit(self) -> None:
        if self.canvas.is_editing():
            return
        capa = self.session.add_text(2)
        self.canvas.flush()
        self.canvas.begin_text_edit(capa.id)

    def start_crop(self) -> None:
        if not self.canvas.begin_crop():
            self.say("Selecciona una foto para recortarla")

    def escape(self) -> None:
        c, s = self.canvas, self.session
        if c.in_crop():
            c.cancel_crop()
        elif c.is_editing():
            c.end_text_edit()
        elif s.tool != "move":
            s.set_tool("move")
        elif self._edit_open:
            self.close_edit()
        else:
            s.clear_selection()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Backslash and not e.isAutoRepeat():
            self.canvas.set_show_original(True)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if e.key() == Qt.Key_Backslash and not e.isAutoRepeat():
            self.canvas.set_show_original(False)
            return
        super().keyReleaseEvent(e)

    # --- archivos ------------------------------------------------------------------------------

    def confirm_discard(self) -> bool:
        self.canvas.end_text_edit()
        if not self.session.dirty:
            return True
        r = QMessageBox.question(
            self, "Hay cambios sin guardar", "¿Guardar el diseño antes de continuar?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save()
        return True

    def new_design(self, width: int, height: int, name: str = "Diseño sin título") -> bool:
        if not self.confirm_discard():
            return False
        self.session.new_document(width, height, name)
        return True

    def show_new(self) -> None:
        dlg = NewDesignDialog(self)
        if dlg.exec() == NewDesignDialog.Accepted:
            w, h, name = dlg.values()
            self.new_design(w, h, name)

    def open_file(self, path: str | Path) -> bool:
        if not self.confirm_discard():
            return False
        return self.session.open_path(path)

    def open_dialog(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir", "", OPEN_ALL)
        if ruta:
            self.open_file(ruta)

    def pick_images(self) -> None:
        rutas, _ = QFileDialog.getOpenFileNames(self, "Subir imágenes", "", photo_io.OPEN_FILTER)
        if rutas:
            self.add_files(rutas)

    def add_files(self, paths: list[str], x: float | None = None, y: float | None = None) -> None:
        paths = [str(p) for p in paths]
        vphoto = [p for p in paths if p.lower().endswith(".vphoto")]
        if vphoto:
            self.open_file(vphoto[0])
            return
        for i, p in enumerate(paths):
            at = (x + 24 * i, y + 24 * i) if x is not None and y is not None else None
            self.session.add_image(p, at=at)

    def _image_dropped(self, image, x: float, y: float) -> None:
        from vortex_studio.photo.render import from_qimage
        self.session.add_image(from_qimage(image), at=(x, y))

    def save(self) -> bool:
        self.canvas.end_text_edit()
        if self.session.path is None:
            return self.save_as()
        return self.session.save()

    def save_as(self, path: str | Path | None = None) -> bool:
        self.canvas.end_text_edit()
        if path is None:
            nombre = f"{self.session.doc.name}.vphoto"
            ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", nombre, SAVE_FILTER)
            if not ruta:
                return False
            path = ruta
        ok = self.session.save(path)
        if ok:
            self.say(f"Guardado: {Path(path).name}")
        return ok

    def show_batch(self) -> None:
        dlg = BatchDialog(self.session, self)
        dlg.btn_add.clicked.connect(lambda: dlg.add_paths(
            QFileDialog.getOpenFileNames(dlg, "Fotos", "", photo_io.OPEN_FILTER)[0]))
        dlg.btn_dir.clicked.connect(lambda: dlg.set_out_dir(
            QFileDialog.getExistingDirectory(dlg, "Carpeta de salida")))
        dlg.exec()

    def show_resize(self) -> None:
        d = self.session.doc
        dlg = ResizeDialog(d.width, d.height, self)
        if dlg.exec() == ResizeDialog.Accepted:
            w, h, adapt = dlg.values()
            self.session.resize_document(w, h, adapt)

    # --- exportar -------------------------------------------------------------------------------

    def show_export(self) -> None:
        self.canvas.end_text_edit()
        self.export_popup.show_at(self.btn_export)

    def _export_flow(self, opts: dict) -> None:
        fmt = opts["fmt"]
        base = f"{self.session.doc.name}{EXT[fmt]}"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar", base,
                                              f"{fmt} (*{EXT[fmt]})")
        if ruta:
            self.export_with(ruta, **opts)

    def export_with(self, path: str | Path, fmt: str = "PNG", quality: int = 92, scale: float = 1.0,
                    transparent: bool = False) -> _Worker | None:
        """Exporta en un hilo: la ventana no se congela con un diseño grande."""
        if self._export_worker is not None:
            self.say("Ya se está exportando otro archivo")
            return None
        path = Path(path)
        if path.suffix.lower() not in (EXT[fmt], ".jpeg" if fmt == "JPG" else EXT[fmt]):
            path = path.with_suffix(EXT[fmt])
        doc = self.session.doc.copy()
        if transparent and fmt != "JPG":
            doc.background = None
        store = self.session.store

        def tarea(_avance):
            photo_io.export(doc, store, path, fmt, quality, scale)

        w = _Worker(tarea, self)
        w.done.connect(lambda err, p=path: self._export_done(err, p))
        self._export_worker = w
        self.say(f"Exportando {path.name}…", keep=True)
        w.start()
        return w

    def _export_done(self, error, path: Path) -> None:
        w, self._export_worker = self._export_worker, None
        if error is None:
            self.last_export = str(path)
            self.say(f"Exportado: {path.name}")
        else:
            self.say(f"No se pudo exportar: {error}")
        if w is not None:
            w.deleteLater()

    def exporting(self) -> bool:
        return self._export_worker is not None

    def showEvent(self, e) -> None:
        super().showEvent(e)
        QTimer.singleShot(0, self.canvas.setFocus)

    # --- cierre ---------------------------------------------------------------------------------

    def closeEvent(self, e) -> None:
        if self._export_worker is not None:
            self._export_worker.wait(15000)
        if not self.confirm_discard():
            e.ignore()
            return
        self.canvas._timer.stop()
        e.accept()
