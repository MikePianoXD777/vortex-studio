"""Atajos de teclado y sincronía de los paneles."""

from vortex_studio.ui.timeline import TOOL_RAZOR


def test_los_atajos_de_una_tecla_estan_marcados(ventana):
    nombres = {a.text().replace("&", "") for a in ventana._plain_actions}
    assert any("Reproducir" in n for n in nombres)
    assert any("Navaja" in n for n in nombres)
    assert "Eliminar" in nombres
    # Los que llevan Ctrl no deben estar: no estorban al escribir.
    assert not any("Deshacer" in n for n in nombres)
    assert not any("Importar" in n for n in nombres)


def test_se_apagan_al_escribir(ventana):
    """Si no, teclear un subtítulo activa la navaja y borra el clip."""
    assert all(a.isEnabled() for a in ventana._plain_actions)

    ventana._focus_changed(None, ventana.text_panel._text)
    assert not any(a.isEnabled() for a in ventana._plain_actions)

    ventana._focus_changed(ventana.text_panel._text, ventana.timeline)
    assert all(a.isEnabled() for a in ventana._plain_actions)


def test_el_campo_numerico_tambien_los_apaga(ventana):
    ventana._focus_changed(None, ventana.text_panel._duration)
    assert not any(a.isEnabled() for a in ventana._plain_actions)


def test_los_paneles_siguen_al_playhead(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.add_title()

    ventana._seek(5.5)          # más allá del texto
    assert ventana.text_panel._title is None

    ventana._seek(1.5)
    assert ventana.text_panel._title is not None


def test_el_panel_de_color_apunta_al_clip_de_abajo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    assert ventana.color_panel._adjust is ventana.sequence.top_clip_at(2.0).color


def test_los_deslizadores_escriben_en_el_modelo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    clip = ventana.sequence.top_clip_at(2.0)

    ventana.color_panel._brightness._slider.setValue(40)
    assert clip.color.brightness == 40

    ventana.color_panel._reset()
    assert clip.color.is_neutral


def test_teclear_no_llena_el_historial(ventana, media):
    """Ctrl+Z debe deshacer 'escribir el subtítulo', no la última letra."""
    ventana._place_video(media["mudo"])
    ventana.add_title()
    antes = ventana.history._index

    for texto in ("u", "un", "uno"):
        ventana.text_panel._text.setPlainText(texto)
    assert ventana.history._index == antes, "creó una entrada por letra"

    ventana._flush()
    assert ventana.history._index == antes + 1
    assert ventana.history.undo_label == "Editar texto"


def test_deshacer_no_deja_paneles_con_objetos_muertos(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    ventana.undo()

    vivos = [c for t in ventana.sequence.text_tracks() for c in t.clips]
    assert ventana.text_panel._title is None or ventana.text_panel._title in vivos
    assert ventana.timeline.selected is None


def test_la_barra_de_estado_dice_lo_importante(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._update_status()
    mensaje = ventana.statusBar().currentMessage()

    assert "320×180" in mensaje
    assert "30 fps" in mensaje
    assert "elemento" in mensaje

    ventana.set_tool(TOOL_RAZOR)
    assert "Navaja" in ventana.statusBar().currentMessage()


def test_las_marcas_salen_en_la_barra(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.mark_in()
    ventana._seek(3.0)
    ventana.mark_out()

    assert "Marcas" in ventana.statusBar().currentMessage()
    assert ventana._range() == (1.0, 3.0)
