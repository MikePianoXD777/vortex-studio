"""Capturas fuera de pantalla a 1280×720 y 1920×1080: que la ventana se pinte entera y sin amontonarse."""

import pytest
from PySide6.QtWidgets import QApplication

from ayudas import foto_de_prueba


@pytest.mark.parametrize("ancho,alto", [(1280, 720), (1920, 1080)])
def test_la_ventana_se_pinta_a_cada_tamano(foto, s, lienzo, qapp, tmp_path, ancho, alto):
    foto.resize(ancho, alto)
    qapp.processEvents()
    s.add_image(foto_de_prueba(900, 700))
    s.add_text(0)
    lienzo.fit()
    lienzo.flush()
    foto.open_edit("filtros")
    for _ in range(30):
        qapp.processEvents()
    lienzo.flush()
    img = foto.grab()
    assert (img.width(), img.height()) == (ancho, alto)
    assert img.save(str(tmp_path / f"foto-{ancho}.png"))
    # El lienzo conserva un espacio útil aun con los dos paneles abiertos.
    assert lienzo.width() >= 480
    assert lienzo.canvas_rect().width() > 200
    # Nada sale del ancho de la ventana.
    assert foto.right_frame.geometry().right() <= foto.width()
    # El panel derecho no necesita desplazarse de lado.
    assert foto.edit_panel.findChild(type(foto.edit_panel.stack)) is not None


def test_cada_panel_izquierdo_cabe_en_su_ancho(foto, qapp):
    for clave in foto.panels:
        foto.show_panel(clave)
        qapp.processEvents()
        p = foto.panels[clave]
        assert p.sizeHint().width() <= foto.left_frame.width() + 20, clave
