"""Decodificación fuera del hilo de la interfaz, con búfer de cuadros."""

import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from vortex_studio.media import VideoSource
from vortex_studio.media.frameserver import FrameJob, FrameServer
from vortex_studio.model.color import ColorAdjust

PRINCIPAL = threading.get_ident()


def trabajo(media, t, clave=1, nombre="mudo", adjust=None):
    return FrameJob.make(clave, media[nombre], t, adjust)


@pytest.fixture
def servidor():
    s = FrameServer()
    yield s
    s.close()


@pytest.fixture
def lento(monkeypatch):
    """Decodificar tarda 60 ms: así se ve qué pasa mientras el hilo trabaja."""
    real = VideoSource.frame_at

    def despacio(self, t, adjust=None):
        time.sleep(0.06)
        return real(self, t, adjust)

    monkeypatch.setattr(VideoSource, "frame_at", despacio)


def esperar(condicion, segundos=5.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(0.005)
    return False


# --- el servidor, sin Qt --------------------------------------------------

def test_decodifica_en_otro_hilo(servidor, media):
    job = trabajo(media, 1.0)
    assert servidor.wait_for([job])
    assert servidor.get(job) is not None
    assert servidor.threads and PRINCIPAL not in servidor.threads


def test_el_cuadro_es_el_mismo_que_decodificando_directo(servidor, media):
    ajuste = ColorAdjust(temperature=40)
    job = trabajo(media, 2.0, adjust=ajuste)
    servidor.wait_for([job])
    with VideoSource(media["mudo"]) as fuente:
        directo = fuente.frame_at(2.0, ajuste)
    assert servidor.get(job).data == directo.data


def test_avisa_desde_su_hilo(media):
    avisos = []
    s = FrameServer(on_ready=lambda: avisos.append(threading.get_ident()))
    try:
        s.wait_for([trabajo(media, 1.0)])
        assert esperar(lambda: avisos)
        assert PRINCIPAL not in avisos
    finally:
        s.close()


def test_lo_que_ya_esta_no_se_vuelve_a_decodificar(servidor, media):
    job = trabajo(media, 1.0)
    servidor.wait_for([job])
    antes = servidor.decoded
    servidor.request([job])
    servidor.wait_for([job])
    assert servidor.decoded == antes


def test_gana_el_pedido_mas_nuevo(servidor, media, lento):
    """Arrastrar el playhead encarga un cuadro por posición: solo importa la última."""
    viejos = [trabajo(media, 0.2 * i) for i in range(10)]
    servidor.request(viejos)
    time.sleep(0.01)                       # que agarre el primero
    nuevo = trabajo(media, 5.5)
    servidor.request([nuevo])
    assert servidor.wait_for([nuevo])

    decodificados = sum(1 for j in viejos if servidor.get(j) is not None)
    assert decodificados <= 1, f"decodificó {decodificados} cuadros que ya nadie quería"


def test_lectura_adelantada(servidor, media):
    ahora = trabajo(media, 1.0)
    adelante = [trabajo(media, 1.0 + i / 30) for i in range(1, 6)]
    servidor.request([ahora], adelante)
    assert servidor.wait_for([ahora] + adelante)
    assert all(servidor.get(j) is not None for j in adelante)


def test_un_cuadro_que_falla_no_se_pide_para_siempre(servidor, tmp_path):
    """Si no se recordara la falla, cada repintado lo volvería a encargar."""
    malo = FrameJob.make(9, tmp_path / "no-existe.mp4", 1.0)
    assert servidor.wait_for([malo], timeout=5)
    assert servidor.failed(malo)
    intentos = servidor.decoded
    for _ in range(5):
        servidor.request([malo])
    time.sleep(0.05)
    assert servidor.decoded == intentos


def test_otro_color_es_otro_cuadro(servidor, media):
    normal = trabajo(media, 1.0)
    calido = trabajo(media, 1.0, adjust=ColorAdjust(temperature=60))
    servidor.wait_for([normal, calido])
    assert servidor.get(normal).data != servidor.get(calido).data


def test_el_trabajo_copia_el_color(media):
    """El usuario sigue moviendo deslizadores mientras el hilo decodifica."""
    ajuste = ColorAdjust(brightness=10)
    job = FrameJob.make(1, media["mudo"], 1.0, ajuste)
    ajuste.brightness = 90
    assert job.adjust.brightness == 10
    assert job.signature != ColorAdjust(brightness=90).signature


def test_el_bufer_respeta_su_limite(media):
    with VideoSource(media["mudo"]) as fuente:
        tamaño = len(fuente.frame_at(0.0).data)
    s = FrameServer(cache_bytes=3 * tamaño)
    try:
        for i in range(6):
            s.wait_for([trabajo(media, i * 0.5)])
        assert s.cached_count <= 3
        assert s.get(trabajo(media, 2.5)) is not None      # el más nuevo se queda
    finally:
        s.close()


def test_reiniciar_tira_el_bufer(servidor, media):
    servidor.wait_for([trabajo(media, 1.0)])
    assert servidor.cached_count == 1
    servidor.reset()
    assert servidor.cached_count == 0
    assert servidor.latest(1) is None
    assert servidor.wait_for([trabajo(media, 2.0)])        # y sigue funcionando


def test_cerrar_detiene_el_hilo(media):
    s = FrameServer()
    s.wait_for([trabajo(media, 1.0)])
    s.close()
    assert not s.alive


# --- el bug de recolorear en pausa ----------------------------------------

def test_cambiar_el_color_en_pausa_no_avanza_el_cuadro(media):
    """Era bug: solo se comparaban brillo, contraste, saturación y gamma.

    Mover la temperatura con el video en pausa decodificaba el cuadro
    siguiente en vez de recolorear el mismo.
    """
    for ajuste in (ColorAdjust(temperature=60), ColorAdjust(vignette=50)):
        with VideoSource(media["mudo"]) as fuente:
            fuente.frame_at(2.0)
            recoloreado = fuente.frame_at(2.0, ajuste)
        with VideoSource(media["mudo"]) as limpia:
            esperado = limpia.frame_at(2.0, ajuste)
        assert recoloreado.data == esperado.data, ajuste


def test_cambiar_la_curva_en_pausa_tampoco(media):
    ajuste = ColorAdjust()
    ajuste.curves.mids = 40
    with VideoSource(media["mudo"]) as fuente:
        fuente.frame_at(3.0)
        recoloreado = fuente.frame_at(3.0, ajuste)
    with VideoSource(media["mudo"]) as limpia:
        assert recoloreado.data == limpia.frame_at(3.0, ajuste).data


def test_la_firma_cubre_todos_los_ajustes():
    base = ColorAdjust().signature
    for campo, valor in (("brightness", 5), ("contrast", 90), ("saturation", 50),
                         ("gamma", 120), ("temperature", 30), ("vignette", 20)):
        otro = ColorAdjust()
        setattr(otro, campo, valor)
        assert otro.signature != base, campo
    con_curva = ColorAdjust()
    con_curva.curves.highs = -20
    assert con_curva.signature != base


# --- en la ventana --------------------------------------------------------

def test_la_ventana_nunca_decodifica_en_su_hilo(ventana, media, monkeypatch):
    hilos = []
    real = VideoSource.frame_at
    monkeypatch.setattr(VideoSource, "frame_at",
                        lambda self, t, adjust=None: hilos.append(threading.get_ident())
                        or real(self, t, adjust))

    ventana._place_video(media["mudo"])
    for t in (0.5, 2.0, 4.0, 1.0):
        ventana._seek(t)
    ventana.preview.current_image()

    assert hilos, "no se decodificó nada"
    assert PRINCIPAL not in hilos


def test_el_cuadro_llega_solo_sin_pedirlo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(3.0)
    assert esperar(lambda: ventana.preview._layers), "el cuadro nunca llegó al preview"


def test_mientras_llega_el_nuevo_se_ve_el_anterior(ventana, media, lento):
    """Al arrastrar se ve el cuadro de antes, no un negro."""
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    anterior = ventana.preview.current_image()
    assert anterior is not None

    ventana._seek(4.5)                         # el hilo tarda en tenerlo
    assert ventana.preview._layers, "se quedó en negro mientras decodificaba"


def test_sacar_el_cuadro_trae_el_exacto(ventana, media, lento):
    from vortex_studio.ui.compositor import compose

    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.preview.current_image()
    ventana._seek(3.3)
    imagen = ventana.preview.current_image()

    s = ventana.sequence
    exacta = compose(s.width, s.height, ventana._layers_at(3.3, sync=True),
                     [], s.titles_at(3.3), 3.3)
    assert imagen == exacta


def test_reproducir_con_decodificacion_lenta_suelta_cuadros(ventana, media, lento):
    """El reloj manda: si el hilo se atrasa se saltan cuadros, no se frena."""
    ventana._place_video(media["mudo"])
    ventana._seek(0.0)
    ventana.toggle_play()
    try:
        esperar(lambda: False, 0.5)
        ventana._tick()
        assert ventana.timeline.playhead > 0.35
        assert ventana.frames.decoded < 0.5 * 30, "decodificó todos, no soltó ninguno"
    finally:
        ventana._pause()


def test_al_reproducir_adelanta_cuadros(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana._playing = True
    try:
        ventana._render(1.0)
        siguiente = [j for _, j, _ in ventana._jobs_at(1.0 + 3 / 30)]
        assert ventana.frames.wait_for(siguiente, timeout=5)
        assert ventana.frames.get(siguiente[0]) is not None
    finally:
        ventana._playing = False


def test_en_pausa_no_adelanta(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._playing = False
    assert ventana._ahead(1.0) == []


def test_recolorear_en_pausa_desde_el_panel(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.preview.current_image()

    clip = ventana.sequence.top_clip_at(2.0)
    clip.color.temperature = 70
    ventana._refresh()
    imagen = ventana.preview.current_image()

    from vortex_studio.ui.compositor import compose
    s = ventana.sequence
    assert imagen == compose(s.width, s.height, ventana._layers_at(2.0, sync=True),
                             [], s.titles_at(2.0), 2.0)


def test_cerrar_la_ventana_detiene_el_hilo(qapp, media):
    from vortex_studio.ui import MainWindow

    w = MainWindow()
    w._place_video(media["mudo"])
    assert w.frames.alive
    w._dirty = False
    w.close()
    assert not w.frames.alive


def test_otro_proyecto_tira_el_bufer(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.preview.current_image()
    assert ventana.frames.cached_count > 0

    ventana._dirty = False
    ventana.new_project()
    assert ventana.frames.cached_count == 0
