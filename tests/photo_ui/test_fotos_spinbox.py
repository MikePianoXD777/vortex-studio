"""Todos los spinbox de Vortex Photo muestran su valor (bug de Qt 6.12: campo de 1 px)."""

from PySide6.QtWidgets import QAbstractSpinBox


def _revisar(raiz, qapp, minimo=22):
    raiz.show()
    qapp.processEvents()
    spins = raiz.findChildren(QAbstractSpinBox)
    assert spins
    for sp in spins:
        if sp.isHidden() and not sp.parentWidget().isVisibleTo(raiz):
            continue
        assert sp.lineEdit().width() >= minimo, (sp.objectName(), sp.toolTip(), sp.lineEdit().width())


def test_spinbox_de_la_barra_contextual(foto, s, qapp):
    s.add_text(0)
    qapp.processEvents()
    bar = foto.context
    assert bar.size_spin.lineEdit().width() >= 22
    s.add_shape("rect")
    qapp.processEvents()
    assert bar.stroke_spin.lineEdit().width() >= 22
    assert bar.radius_spin.lineEdit().width() >= 22


def test_spinbox_de_toda_la_ventana(foto, s, qapp):
    s.add_text(0)
    foto.open_edit("filtros")
    qapp.processEvents()
    for sp in foto.findChildren(QAbstractSpinBox):
        if sp.isVisible():
            assert sp.lineEdit().width() >= 22, (sp.toolTip(), sp.lineEdit().width())


def test_spinbox_de_los_dialogos(foto, qapp):
    from vortex_studio.ui.photo.dialogs import ResizeDialog

    d = ResizeDialog(1080, 1080)
    _revisar(d, qapp, 40)
    d.close()
