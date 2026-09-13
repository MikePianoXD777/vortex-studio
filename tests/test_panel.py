"""El panel de propiedades con pestañas."""

import pytest


def pestana(ventana) -> str:
    tabs = ventana.panel._tabs
    return tabs.tabText(tabs.currentIndex()).split()[-1]


def test_las_paginas_estan_y_en_orden(ventana):
    tabs = ventana.panel._tabs
    titulos = [tabs.tabText(i).split()[-1] for i in range(tabs.count())]
    assert titulos == ["Transformar", "Color", "Máscara", "Efectos", "Clip", "Audio",
                       "Texto", "Imagen"]


def test_insertar_texto_lleva_a_su_pestaña(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    assert pestana(ventana) == "Texto"


def test_insertar_imagen_lleva_a_su_pestaña(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._place_image(media["logo"])
    assert pestana(ventana) == "Imagen"


def test_seleccionar_un_clip_sale_de_la_pestaña_que_no_aplica(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    assert pestana(ventana) == "Texto"

    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    assert pestana(ventana) == "Transformar"


def test_un_clip_de_audio_abre_la_pestaña_de_clip(ventana, media):
    ventana._place_video(media["sonoro"])
    ventana.add_title()
    ventana.timeline.select(ventana.sequence.audio_tracks()[0].clips[0])
    assert pestana(ventana) == "Clip"


def test_respeta_la_pestaña_elegida_a_mano(ventana, media):
    """Arrancarle la pestaña al usuario en cada selección estorba."""
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])

    ventana.panel.show_page(ventana.color_panel)
    ventana._seek(3.0)
    ventana.timeline.select(None)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    assert pestana(ventana) == "Color"


def test_las_pestañas_que_no_aplican_se_apagan(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)

    tabs = ventana.panel._tabs
    def activa(pagina):
        return tabs.isTabEnabled(tabs.indexOf(pagina))

    assert not activa(ventana.text_panel), "sin texto, la pestaña debería estar apagada"
    assert not activa(ventana.image_panel)
    assert activa(ventana.transform_panel)
    assert activa(ventana.color_panel)


def test_al_haber_texto_su_pestaña_se_enciende(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.add_title()
    ventana._seek(1.5)

    tabs = ventana.panel._tabs
    assert tabs.isTabEnabled(tabs.indexOf(ventana.text_panel))


# --- la pestaña de máscara ------------------------------------------------

def test_la_mascara_se_apaga_en_una_pista_de_audio(ventana, media):
    """En una pista de audio no hay nada que tapar ni con qué fusionar."""
    ventana._place_video(media["sonoro"])
    ventana.timeline.select(ventana.sequence.audio_tracks()[0].clips[0])

    tabs = ventana.panel._tabs
    assert not tabs.isTabEnabled(tabs.indexOf(ventana.mask_panel))


def test_la_mascara_se_enciende_con_un_clip_de_video(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    tabs = ventana.panel._tabs
    assert tabs.isTabEnabled(tabs.indexOf(ventana.mask_panel))


def test_poner_una_mascara_lleva_a_su_pestaña(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.set_mask_shape("Círculo")
    assert pestana(ventana) == "Máscara"


def test_el_panel_escribe_en_el_clip(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    clip = ventana.sequence.top_clip_at(2.0)
    ventana.timeline.select(clip)

    ventana.mask_panel._shape.setCurrentText("Rectángulo")
    ventana.mask_panel._rows["feather"].set_value(12)
    ventana.mask_panel._push()

    assert clip.mask.shape == "Rectángulo"
    assert clip.mask.feather == pytest.approx(0.12)


def test_el_ancho_se_apaga_en_la_mascara_lineal(ventana, media):
    """Un control encendido que no hace nada parece un programa roto."""
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.set_mask_shape("Lineal")

    panel = ventana.mask_panel
    assert not panel._rows["width"].isEnabled()
    assert panel._rows["rotation"].isEnabled()

    ventana.set_mask_shape("Círculo")
    assert panel._rows["width"].isEnabled()


def test_quitar_la_mascara_apaga_sus_controles(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.set_mask_shape("Círculo")
    ventana.set_mask_shape("Ninguna")
    assert not ventana.mask_panel._rows["feather"].isEnabled()


def test_la_mascara_entra_al_historial(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    clip = ventana.sequence.top_clip_at(2.0)
    ventana.set_mask_shape("Círculo")
    assert not clip.mask.is_off

    ventana.undo()
    assert ventana.sequence.top_clip_at(2.0).mask.is_off


# --- la curva dentro del panel de color -----------------------------------

def test_la_curva_arranca_cerrada(ventana, media):
    """Once deslizadores a la vista y se acabó el "fácil de usar"."""
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    assert not ventana.color_panel._curve_group.abierto


def test_un_look_con_curva_abre_el_grupo(ventana, media):
    """Si no, el look le hace algo a la imagen que no se ve de dónde sale."""
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.timeline.select(ventana.sequence.top_clip_at(2.0))
    ventana.color_panel._apply_look("Cine")
    ventana._seek(2.0)
    assert ventana.color_panel._curve_group.abierto


def test_los_deslizadores_de_la_curva_escriben_en_el_clip(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    clip = ventana.sequence.top_clip_at(2.0)

    ventana.color_panel._curve_rows["highs"].set_value(-35)
    ventana.color_panel._push()
    assert clip.color.curves.highs == -35


def test_una_curva_lista_escribe_en_los_deslizadores(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.color_panel._apply_curve_look("Contraste en S")

    panel = ventana.color_panel
    assert panel._curve_rows["shadows"].value() < 0
    assert panel._curve_rows["highs"].value() > 0
    assert ventana.sequence.top_clip_at(2.0).color.curves.highs > 0


def test_restablecer_limpia_curva_y_vinieta(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    clip = ventana.sequence.top_clip_at(2.0)

    ventana.color_panel._apply_look("Noche")
    assert clip.color.vignette > 0
    ventana.color_panel._reset()
    assert clip.color.is_neutral


# --- animación de texto en su panel ---------------------------------------

def test_las_animaciones_estan_en_el_panel_de_texto(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    panel = ventana.text_panel
    assert panel._anim_in.count() > 5
    assert panel._anim_in.currentText() == "Ninguna"


def test_escoger_una_animacion_escribe_en_el_texto(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    titulo = ventana._title

    ventana.text_panel._anim_in.setCurrentText("Desde la izquierda")
    ventana.text_panel._anim_time.setValue(0.7)
    assert titulo.anim_in == "Desde la izquierda"
    assert titulo.anim_time == pytest.approx(0.7)


def test_la_animacion_entra_al_historial(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    ventana.text_panel._anim_in.setCurrentText("Acercarse")
    ventana._flush()

    ventana.undo()
    assert ventana.sequence.text_tracks()[0].clips[0].anim_in == "Ninguna"
