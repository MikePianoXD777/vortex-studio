"""El diseño de la beta: barra superior, transporte, herramientas, medios y paneles."""

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest

from vortex_studio.model.project import KEEP_PITCH, MUTE_AUDIO, SHIFT_PITCH
from vortex_studio.ui.timeline import TOOL_RAZOR, TOOL_SELECT, TOOL_SLIP, TimelineWidget
from vortex_studio.ui.transport import SPEEDS, TransportBar
from vortex_studio.ui.widgets import (
    ICONOS,
    DockTitle,
    IconButton,
    SliderRow,
    Switch,
    draw_icon,
    make_icon,
)


def _brillo(imagen, x, y):
    return QColor(imagen.pixel(x, y)).lightness()


# --- barra superior ---------------------------------------------------------

def test_la_barra_de_menus_vive_en_la_barra_de_arriba(ventana):
    assert ventana.menuWidget() is ventana.top_bar
    assert ventana.menuBar() is ventana.top_bar.menu


def test_estan_todos_los_menus(ventana):
    nombres = [a.text().replace("&", "") for a in ventana.menuBar().actions()]
    for menu in ("Archivo", "Editar", "Clip", "Secuencia", "Ver"):
        assert menu in nombres


def test_pedir_la_barra_de_menus_no_tapa_la_de_arriba(ventana):
    ventana.menuBar().addMenu("extra")
    assert ventana.menuWidget() is ventana.top_bar


def test_la_barra_dice_tamano_y_cuadros(ventana):
    seq = ventana.sequence
    texto = ventana.top_bar.info.text()
    assert f"{seq.width}×{seq.height}" in texto and f"{seq.fps:g} fps" in texto


def test_la_barra_dice_el_nombre_del_proyecto(ventana, tmp_path):
    ventana._path = tmp_path / "boda.vortex"
    assert ventana.save()
    assert "boda.vortex" in ventana.top_bar.info.text()


def test_exportar_esta_a_la_vista(ventana):
    boton = ventana.top_bar.export_button
    assert boton.text() == "Exportar" and boton.objectName() == "primario"
    assert boton.isVisibleTo(ventana)


# --- transporte -------------------------------------------------------------

def _boton(barra, icono):
    return next(b for b in barra.findChildren(IconButton) if b.icon_name == icono)


def test_play_cambia_a_pausa(qapp):
    barra = TransportBar()
    barra.set_playing(True)
    assert barra._play.icon_name == "pausa"
    barra.set_playing(False)
    assert barra._play.icon_name == "play"


def test_silenciar_cambia_icono_y_volumen(qapp):
    barra = TransportBar()
    oidos = []
    barra.volume_changed.connect(oidos.append)
    barra._mute.setChecked(True)
    assert barra._mute.icon_name == "silencio"
    assert barra.volume() == 0.0 and oidos[-1] == 0.0
    assert not barra._volume.isEnabled()
    barra._mute.setChecked(False)
    assert barra._mute.icon_name == "volumen" and barra.volume() > 0


def test_los_botones_avisan(qapp):
    barra = TransportBar()
    avisos = []
    barra.go_start.connect(lambda: avisos.append("inicio"))
    barra.go_end.connect(lambda: avisos.append("fin"))
    barra.play_pause.connect(lambda: avisos.append("play"))
    barra.step.connect(avisos.append)
    for icono in ("inicio", "fin", "anterior", "siguiente"):
        _boton(barra, icono).click()
    barra._play.click()
    assert avisos == ["inicio", "fin", -1, 1, "play"]


def test_la_velocidad_avisa_y_se_refleja(qapp):
    barra = TransportBar()
    oidas = []
    barra.speed_changed.connect(oidas.append)
    barra._speed.setCurrentIndex(SPEEDS.index(2.0))
    assert oidas == [2.0]
    barra.set_speed(0.5)
    assert barra._speed.currentData() == 0.5 and oidas == [2.0]


# --- herramientas del timeline ---------------------------------------------

def test_la_pildora_cambia_la_herramienta(ventana):
    ventana.timeline_tools.tool_buttons[TOOL_RAZOR].click()
    assert ventana.timeline.tool == TOOL_RAZOR
    assert ventana._tool_actions[TOOL_RAZOR].isChecked()


def test_el_menu_marca_la_pildora(ventana):
    ventana.set_tool(TOOL_SLIP)
    assert ventana.timeline_tools.tool_buttons[TOOL_SLIP].isChecked()
    ventana.set_tool(TOOL_SELECT)
    assert ventana.timeline_tools.tool_buttons[TOOL_SELECT].isChecked()
    assert not ventana.timeline_tools.tool_buttons[TOOL_SLIP].isChecked()


def test_el_conteo_de_elementos(ventana, media):
    assert ventana.timeline_tools.count.text() == "0 elementos"
    ventana._place_video(media["sonoro"])
    piezas = sum(len(t.clips) for t in ventana.sequence.tracks)
    assert ventana.timeline_tools.count.text() == f"{piezas} elementos"


def test_dividir_corta_en_el_playhead(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    ventana.timeline_tools.split_button.click()
    assert len(ventana.sequence.video_tracks()[-1].clips) == 2


def test_iman_apagado_no_pega(ventana):
    linea = ventana.timeline
    assert linea._snap(0.05) == 0.0
    ventana.timeline_tools.snap_button.setChecked(False)
    assert not linea.snapping
    assert linea._snap(0.05) != 0.0 and linea._snap_at is None
    ventana.timeline_tools.snap_button.setChecked(True)
    assert linea._snap(0.05) == 0.0


def test_enlace_apagado_selecciona_un_lado(ventana, media):
    ventana._place_video(media["sonoro"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    assert len(ventana.timeline.selected_items()) == 2
    ventana.timeline_tools.link_button.setChecked(False)
    assert ventana.timeline.selected_items() == [clip]
    ventana.timeline_tools.link_button.setChecked(True)
    assert len(ventana.timeline.selected_items()) == 2


def test_enlace_apagado_no_marca_el_otro_lado(ventana, media):
    ventana._place_video(media["sonoro"])
    video = ventana.sequence.video_tracks()[-1].clips[0]
    audio = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(video)
    assert ventana.timeline._is_selected(audio) == (False, True)
    ventana.timeline.linked_selection = False
    assert ventana.timeline._is_selected(audio) == (False, False)


# --- regla ------------------------------------------------------------------

@pytest.mark.parametrize("t, paso, texto", [
    (4.0, 2.0, "00:04"),
    (65.0, 5.0, "01:05"),
    (1.5, 0.5, "00:01.5"),
    (3725.0, 60.0, "1:02:05"),
])
def test_etiquetas_de_la_regla(t, paso, texto):
    assert TimelineWidget._ruler_label(t, paso) == texto


# --- interruptores del clip -------------------------------------------------

def _clip_con_audio(ventana, media):
    ventana._place_video(media["sonoro"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    return clip, ventana.clip_panel


def test_mantener_tono_refleja_el_modo(ventana, media):
    clip, panel = _clip_con_audio(ventana, media)
    assert panel._keep_pitch.isChecked() == (clip.audio_mode == KEEP_PITCH)
    assert not panel._mute_audio.isChecked()


def test_apagar_mantener_tono_cambia_el_tono(ventana, media):
    clip, panel = _clip_con_audio(ventana, media)
    panel._keep_pitch.setChecked(True)
    panel._keep_pitch.setChecked(False)
    assert panel._audio_mode.currentText() == SHIFT_PITCH
    assert panel._item.audio_mode == SHIFT_PITCH


def test_silenciar_apaga_mantener_tono(ventana, media):
    clip, panel = _clip_con_audio(ventana, media)
    panel._mute_audio.setChecked(True)
    assert panel._item.audio_mode == MUTE_AUDIO
    assert not panel._keep_pitch.isEnabled()
    panel._mute_audio.setChecked(False)
    assert panel._item.audio_mode == KEEP_PITCH
    assert panel._keep_pitch.isEnabled() and panel._keep_pitch.isChecked()


def test_la_lista_escondida_mueve_los_interruptores(ventana, media):
    clip, panel = _clip_con_audio(ventana, media)
    panel._audio_mode.setCurrentText(MUTE_AUDIO)
    assert panel._mute_audio.isChecked() and not panel._keep_pitch.isChecked()


def test_el_interruptor_cambia_al_clic(qapp):
    interruptor = Switch()
    assert not interruptor.isChecked()
    QTest.mouseClick(interruptor, Qt.LeftButton)
    assert interruptor.isChecked()
    QTest.mouseClick(interruptor, Qt.LeftButton)
    assert not interruptor.isChecked()


# --- números de los deslizadores -------------------------------------------

def test_decimas_se_ven_como_segundos(qapp):
    fila = SliderRow("Entrada", 0, 300, 0, scale=10, decimals=1)
    fila.set_value(12)
    assert fila._spin.text() == "1.2"


def test_velocidad_con_su_signo(qapp):
    fila = SliderRow("Velocidad", 10, 400, 100, scale=100, decimals=2, suffix="×")
    fila.set_value(150)
    assert fila._spin.text() == "1.50×"


def test_escribir_el_numero_real(qapp):
    fila = SliderRow("Entrada", 0, 300, 0, scale=10, decimals=1)
    fila._spin.lineEdit().setText("2.5")
    fila._spin.interpretText()
    assert fila.value() == 25


def test_sin_escala_se_ve_igual_que_antes(qapp):
    fila = SliderRow("Volumen", 0, 400, 100)
    assert fila._spin.text() == "100" and fila.value() == 100


# --- panel de medios --------------------------------------------------------

def test_pestanas_de_medios_filtran(ventana):
    bin_ = ventana.media_bin
    bin_.tab_button(1).click()
    assert bin_.kind.currentText() == "Audio"
    bin_.tab_button(0).click()
    assert bin_.kind.currentText() == "Todo"


def test_la_pestana_texto_cambia_de_pagina(ventana):
    bin_ = ventana.media_bin
    bin_.tab_button(2).click()
    assert bin_.pages.currentIndex() == 1
    bin_.tab_button(0).click()
    assert bin_.pages.currentIndex() == 0


def test_un_filtro_por_codigo_suelta_las_pestanas(ventana):
    bin_ = ventana.media_bin
    bin_.kind.setCurrentText("Video")
    assert not any(bin_.tab_button(i).isChecked() for i in range(3))
    bin_.kind.setCurrentText("Todo")
    assert bin_.tab_button(0).isChecked()


def test_la_tarjeta_importar_avisa_y_no_cuenta(ventana, media):
    bin_ = ventana.media_bin
    ventana.import_to_bin([media["mudo"]])
    assert bin_.list.count() == 1
    pedidos = []
    bin_.import_requested.disconnect()
    bin_.import_requested.connect(lambda: pedidos.append(True))
    QTest.mouseClick(bin_.list.viewport(), Qt.LeftButton, Qt.NoModifier,
                     bin_.list.import_rect().center())
    assert pedidos == [True] and bin_.list.count() == 1


def test_la_tarjeta_importar_va_despues_del_ultimo(ventana, media):
    bin_ = ventana.media_bin
    vacia = bin_.list.import_rect()
    ventana.import_to_bin([media["mudo"]])
    qapp_rect = bin_.list.import_rect()
    assert qapp_rect != vacia
    primero = bin_.list.visualItemRect(bin_.list.item(0))
    assert not primero.intersects(qapp_rect)


def test_las_tarjetas_llevan_duracion(ventana, media):
    from vortex_studio.ui.media_bin import DURATION_ROLE
    ventana.import_to_bin([media["mudo"]])
    assert ventana.media_bin.list.item(0).data(DURATION_ROLE) > 0


def test_tarjeta_de_texto_agrega_un_texto(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.media_bin.text_cards["Centro"].click()
    titulo = ventana.sequence.text_tracks()[0].clips[0]
    assert titulo.y == pytest.approx(0.5)


def test_tarjeta_de_subtitulos_avisa(ventana):
    pedidos = []
    ventana.media_bin.subtitles_requested.disconnect()
    ventana.media_bin.subtitles_requested.connect(lambda: pedidos.append(True))
    ventana.media_bin.text_cards["subtitulos"].click()
    assert pedidos == [True]


# --- monitor ----------------------------------------------------------------

def test_el_cuadro_tiene_esquinas_redondeadas(ventana, media):
    ventana._place_video(media["gris"])
    ventana._settle_preview()
    imagen = ventana.preview.grab().toImage()
    caja = ventana.preview._fit(ventana.preview._aspect)
    esquina = (int(caja.left()) + 1, int(caja.top()) + 1)
    centro = (int(caja.center().x()), int(caja.center().y()))
    assert _brillo(imagen, *centro) > 100
    assert _brillo(imagen, *esquina) < 30


def test_el_monitor_vacio_usa_el_color_de_la_tarjeta(ventana):
    from vortex_studio.ui import theme
    imagen = ventana.preview.grab().toImage()
    assert QColor(imagen.pixel(3, 3)).name() == theme.TARJETA


# --- paneles despegables ----------------------------------------------------

def test_los_paneles_llevan_su_barra_propia(ventana):
    for dock in (ventana.panel, ventana.media_bin, ventana.scopes, ventana.keyframe_editor):
        assert isinstance(dock.titleBarWidget(), DockTitle)


def test_despegar_y_volver(ventana):
    barra = ventana.media_bin.titleBarWidget()
    barra.float_button.click()
    assert ventana.media_bin.isFloating()
    barra.float_button.click()
    assert not ventana.media_bin.isFloating()


def test_cerrar_solo_donde_se_puede(ventana):
    assert ventana.media_bin.titleBarWidget().close_button.isVisibleTo(ventana.media_bin)
    assert not ventana.panel.titleBarWidget().close_button.isVisibleTo(ventana.panel)


def test_los_paneles_que_no_estan_en_el_diseno_dicen_su_nombre(ventana):
    assert ventana.keyframe_editor.titleBarWidget()._title.text() == "KEYFRAMES"
    assert ventana.panel.titleBarWidget()._title.text() == ""


# --- íconos -----------------------------------------------------------------

@pytest.mark.parametrize("nombre", ICONOS)
def test_cada_icono_pinta_algo(qapp, nombre):
    imagen = QImage(32, 32, QImage.Format_ARGB32)
    imagen.fill(Qt.transparent)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.Antialiasing)
    draw_icon(p, nombre, QRectF(0, 0, 32, 32), QColor("#ffffff"))
    p.end()
    pintados = sum(1 for x in range(32) for y in range(32) if QColor(imagen.pixel(x, y)).alpha())
    assert pintados > 10


def test_make_icon_no_sale_vacio(qapp):
    assert not make_icon("play").isNull()


def test_el_play_circular_es_blanco(qapp):
    boton = IconButton("play", size=40, circle=True)
    imagen = boton.grab().toImage()
    assert _brillo(imagen, 6, 20) > 240
