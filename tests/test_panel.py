"""El panel de propiedades con pestañas."""


def pestana(ventana) -> str:
    tabs = ventana.panel._tabs
    return tabs.tabText(tabs.currentIndex()).split()[-1]


def test_las_cinco_paginas_estan(ventana):
    tabs = ventana.panel._tabs
    titulos = [tabs.tabText(i).split()[-1] for i in range(tabs.count())]
    assert titulos == ["Transformar", "Color", "Clip", "Texto", "Imagen"]


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
