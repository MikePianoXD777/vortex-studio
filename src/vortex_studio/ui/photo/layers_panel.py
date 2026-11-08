"""Panel de capas: lista con miniatura, ojo, candado, arrastrar para reordenar."""

from __future__ import annotations

import json

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.photo.document import (
    BLENDS,
    KIND_ADJUST,
    KIND_IMAGE,
    KIND_SHAPE,
    KIND_TEXT,
    layer_to_dict,
)
from vortex_studio.photo.render import to_qimage
from vortex_studio.ui import theme
from vortex_studio.ui.photo.controls import IconBtn, PSlider, heading, muted
from vortex_studio.ui.photo.icons import draw_icon
from vortex_studio.ui.photo.session import PhotoSession

ROW_H = 54
THUMB = 40
KIND_NAMES = {KIND_IMAGE: "Imagen", KIND_TEXT: "Texto", KIND_SHAPE: "Forma", KIND_ADJUST: "Ajuste"}


def eye_rect(r: QRect) -> QRect:
    return QRect(r.right() - 34, r.center().y() - 11, 22, 22)


def lock_rect(r: QRect) -> QRect:
    return QRect(r.right() - 62, r.center().y() - 11, 22, 22)


class _Delegate(QStyledItemDelegate):
    def __init__(self, panel: "LayersPanel") -> None:
        super().__init__(panel)
        self.panel = panel

    def sizeHint(self, option, index) -> QSize:
        return QSize(100, ROW_H)

    def paint(self, p: QPainter, option, index) -> None:
        layer = self.panel.layer_at_row(index.row())
        if layer is None:
            return
        r = option.rect.adjusted(2, 2, -2, -2)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if index.data(Qt.UserRole + 1):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.PILDORA))
            p.drawRoundedRect(r, 8, 8)
        th = QRect(r.left() + 6, r.center().y() - THUMB // 2, THUMB, THUMB)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2b2b30"))
        p.drawRoundedRect(th, 6, 6)
        pm = self.panel.thumb(layer)
        if pm is not None:
            p.drawPixmap(th.center().x() - pm.width() // 2, th.center().y() - pm.height() // 2, pm)
        elif layer.kind == KIND_ADJUST:
            draw_icon(p, "controles", QRectF(th.adjusted(8, 8, -8, -8)), QColor(theme.TENUE))
        dim = not layer.visible
        p.setPen(QColor(theme.APAGADO if dim else theme.TEXTO))
        f = p.font()
        f.setPixelSize(13)
        p.setFont(f)
        nombre = layer.text.strip().split("\n")[0] if layer.kind == KIND_TEXT and layer.text else layer.name
        texto = p.fontMetrics().elidedText(nombre or KIND_NAMES.get(layer.kind, "Capa"),
                                           Qt.ElideRight, r.width() - THUMB - 14 - 70)
        p.drawText(QRect(th.right() + 10, r.top() + 8, r.width() - THUMB - 84, 18),
                   Qt.AlignVCenter | Qt.AlignLeft, texto)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(theme.MUY_TENUE))
        sub = KIND_NAMES.get(layer.kind, "Capa")
        if layer.opacity < 0.999:
            sub += f" · {round(layer.opacity * 100)}%"
        if layer.blend != "Normal":
            sub += f" · {layer.blend}"
        p.drawText(QRect(th.right() + 10, r.top() + 27, r.width() - THUMB - 84, 16),
                   Qt.AlignVCenter | Qt.AlignLeft, sub)
        draw_icon(p, "ojo" if layer.visible else "ojo_cerrado", QRectF(eye_rect(r)).adjusted(3, 3, -3, -3),
                  QColor(theme.TEXTO if layer.visible else theme.APAGADO))
        draw_icon(p, "candado" if layer.locked else "candado_abierto",
                  QRectF(lock_rect(r)).adjusted(3, 3, -3, -3),
                  QColor(theme.TEXTO if layer.locked else theme.APAGADO))
        p.restore()


class LayerList(QListWidget):
    drop_requested = Signal(int, int, bool)     # fila origen, fila destino, después

    def __init__(self, panel: "LayersPanel") -> None:
        super().__init__()
        self.panel = panel
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(_Delegate(panel))
        self.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; outline: none; padding: 0; }}"
            "QListWidget::item { border: none; background: transparent; }")
        self.setSpacing(0)

    def mousePressEvent(self, e) -> None:
        item = self.itemAt(e.position().toPoint())
        if item is not None and e.button() == Qt.LeftButton:
            r = self.visualItemRect(item).adjusted(2, 2, -2, -2)
            layer = self.panel.layer_at_row(self.row(item))
            if layer is not None:
                pt = e.position().toPoint()
                if eye_rect(r).contains(pt):
                    self.panel.s.set_visible(layer.id, not layer.visible)
                    return
                if lock_rect(r).contains(pt):
                    self.panel.s.set_locked(layer.id, not layer.locked)
                    return
        super().mousePressEvent(e)

    def dropEvent(self, e) -> None:
        # No dejamos que Qt mueva la fila: eso desincroniza la lista del diseño.
        # Se calcula a dónde iba y se le pide a la sesión; ella repinta todo.
        src = self.currentRow()
        item = self.itemAt(e.position().toPoint())
        if src < 0:
            e.ignore()
            return
        if item is None:
            dst, after = self.count() - 1, True
        else:
            dst = self.row(item)
            rect = self.visualItemRect(item)
            after = e.position().y() > rect.center().y()
        e.setDropAction(Qt.IgnoreAction)
        e.accept()
        self.drop_requested.emit(src, dst, after)


class LayersPanel(QWidget):
    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        self._thumbs: dict[str, QPixmap] = {}
        self._rows: list[str] = []
        self._syncing = False

        self.list = LayerList(self)
        self.list.itemSelectionChanged.connect(self._selection_from_list)
        self.list.drop_requested.connect(self.move_row)

        self.opacity = PSlider("Transparencia", 0, 100, 100, suffix="%")
        self.opacity.live.connect(self._opacity_live)
        self.opacity.committed.connect(self._opacity_commit)
        self.blend = QComboBox()
        self.blend.addItems(BLENDS)
        self.blend.activated.connect(self._blend_changed)

        fila = QHBoxLayout()
        fila.setSpacing(2)
        self.btn_dup = IconBtn("duplicar", "Duplicar capa", 30)
        self.btn_del = IconBtn("basura", "Eliminar capa", 30)
        self.btn_dup.clicked.connect(self.s.duplicate_selected)
        self.btn_del.clicked.connect(self.s.delete_selected)
        fila.addStretch(1)
        fila.addWidget(self.btn_dup)
        fila.addWidget(self.btn_del)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(heading("Capas"))
        lay.addWidget(muted("Arrastra para reordenar. Arriba = al frente."))
        lay.addWidget(self.list, 1)
        lay.addWidget(self.opacity)
        lay.addWidget(self.blend)
        lay.addLayout(fila)

        session.committed.connect(lambda _l: self.refresh())
        session.selection_changed.connect(self._sync_selection)
        session.document_replaced.connect(self.refresh)
        self.refresh()

    # --- filas ↔ capas ------------------------------------------------------

    def layer_at_row(self, row: int):
        if 0 <= row < len(self._rows):
            return self.s.doc.layer(self._rows[row])
        return None

    def row_of(self, layer_id: str) -> int:
        return self._rows.index(layer_id) if layer_id in self._rows else -1

    def refresh(self) -> None:
        self._syncing = True
        try:
            capas = list(reversed(self.s.doc.layers))
            self._rows = [c.id for c in capas]
            self.list.clear()
            for c in capas:
                it = QListWidgetItem()
                it.setSizeHint(QSize(100, ROW_H))
                self.list.addItem(it)
            self._mark_selected()
        finally:
            self._syncing = False
        self._sync_controls()
        self.list.viewport().update()

    def _mark_selected(self) -> None:
        ids = set(self.s.selection)
        for r, lid in enumerate(self._rows):
            it = self.list.item(r)
            sel = lid in ids
            it.setSelected(sel)
            it.setData(Qt.UserRole + 1, sel)

    def _sync_selection(self) -> None:
        self._syncing = True
        try:
            self._mark_selected()
        finally:
            self._syncing = False
        self._sync_controls()
        self.list.viewport().update()

    def _selection_from_list(self) -> None:
        if self._syncing:
            return
        ids = [self._rows[self.list.row(i)] for i in self.list.selectedItems()
               if 0 <= self.list.row(i) < len(self._rows)]
        self._syncing = True
        try:
            for r in range(self.list.count()):
                self.list.item(r).setData(Qt.UserRole + 1, self.list.item(r).isSelected())
            self.s.select(ids)
        finally:
            self._syncing = False
        self._sync_controls()

    def move_row(self, src: int, dst: int, after: bool = False) -> bool:
        """Lleva la fila `src` junto a la fila `dst` (la lista va con el frente arriba)."""
        if not (0 <= src < len(self._rows)) or not (0 <= dst < len(self._rows)):
            return False
        if src == dst:
            return False
        lid = self._rows[src]
        i = self.s.doc.index(lid)
        # En la lista, «después» = más abajo = menor índice en doc.layers.
        lista = [c.id for c in self.s.doc.layers if c.id != lid]
        base = lista.index(self._rows[dst])
        pos = base if after else base + 1
        return self.s.move_layer_to(lid, pos) if pos != i else False

    # --- controles de abajo ----------------------------------------------------

    def _sync_controls(self) -> None:
        sel = self.s.selected()
        self.opacity.setEnabled(bool(sel))
        self.blend.setEnabled(bool(sel))
        if sel:
            self.opacity.set_value(round(sel[0].opacity * 100))
            self.blend.setCurrentText(sel[0].blend)

    def _opacity_live(self, v: float) -> None:
        for c in self.s.selected():
            c.opacity = v / 100.0
        self.s.touch()

    def _opacity_commit(self, v: float) -> None:
        if self.s.selected():
            self.s.commit("Transparencia")

    def _blend_changed(self, _i: int) -> None:
        modo = self.blend.currentText()
        self.s.edit("Modo de fusión", lambda c: setattr(c, "blend", modo))

    # --- miniaturas ---------------------------------------------------------------

    def thumb(self, layer) -> QPixmap | None:
        if layer.kind == KIND_ADJUST:
            return None
        d = layer_to_dict(layer)
        for k in ("cx", "cy", "rotation"):
            d["transform"].pop(k, None)
        d.pop("id", None)
        d.pop("name", None)
        key = json.dumps(d, sort_keys=True, default=str)
        pm = self._thumbs.get(key)
        if pm is not None:
            return pm
        try:
            t = layer.transform
            scale = (THUMB - 2) / max(t.width, t.height, 1.0)
            px = self.s.renderer.render_layer(self.s.doc, layer, scale)
            pm = QPixmap.fromImage(to_qimage(px))
        except Exception:
            return None
        if len(self._thumbs) > 300:
            self._thumbs.clear()
        self._thumbs[key] = pm
        return pm
