"""El audio enlazado sigue a la transición de su video.

Antes, en una transición de video el sonido cortaba seco en el corte: la
imagen se cruzaba y el audio brincaba de un clip al otro.
"""

from pathlib import Path

import numpy as np
import pytest

from vortex_studio.media.audio import RATE, transition_envelope
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip
from vortex_studio.model.project import CROSS, DIP_BLACK


def muestras(frames) -> np.ndarray:
    trozos = []
    for f in frames:
        datos = f.to_ndarray().astype(np.float64)
        trozos.append(datos[0] if f.format.is_planar else datos[0, :: len(f.layout.channels)])
    return np.concatenate(trozos)


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def cortado(ventana, media, segundos=1.0, tipo=CROSS):
    """Un video con sonido partido a la mitad, con transición en el corte."""
    ventana._place_video(media["sonoro"])
    ventana._seek(3.0)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    ventana.cut_at_playhead()
    _, segundo = ventana.sequence.video_tracks()[-1].clips
    ventana.timeline.select(segundo)
    ventana.set_dissolve(segundos, tipo)
    return segundo


def audio_de(ventana):
    return sorted(ventana._audio_clips(), key=lambda c: c.start)


def test_el_corte_tiene_audio_enlazado(ventana, media):
    cortado(ventana, media)
    a1 = ventana.sequence.audio_tracks()[0]
    assert len(a1.clips) == 2 and all(c.link for c in a1.clips)


def test_en_la_cruzada_los_audios_se_enciman(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    corte = segundo.start
    sale, entra = audio_de(ventana)

    assert sale.end == pytest.approx(corte + 0.5)
    assert entra.start == pytest.approx(corte - 0.5)
    # El que entra toma material de antes de su punto de entrada.
    assert entra.in_point == pytest.approx(corte - 0.5, abs=1e-6)


def test_los_clips_del_timeline_no_se_tocan(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    a1 = ventana.sequence.audio_tracks()[0]
    antes = [(c.start, c.duration, c.in_point) for c in a1.clips]
    ventana._audio_clips()
    assert [(c.start, c.duration, c.in_point) for c in a1.clips] == antes
    assert a1.clips[0].end == pytest.approx(segundo.start)


def test_las_curvas_son_de_potencia_constante(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    sale, entra = audio_de(ventana)
    t = np.linspace(segundo.start - 0.5, segundo.start + 0.5, 41)
    energia = transition_envelope(sale, t) ** 2 + transition_envelope(entra, t) ** 2
    assert energia == pytest.approx(np.ones_like(t), abs=1e-9)
    # En el corte, cada uno a −3 dB.
    medio = np.array([segundo.start])
    assert transition_envelope(sale, medio)[0] == pytest.approx(np.sqrt(0.5))


def test_a_negro_el_audio_pasa_por_silencio(ventana, media):
    segundo = cortado(ventana, media, 1.0, DIP_BLACK)
    corte = segundo.start
    sale, entra = audio_de(ventana)
    # No se enciman: cada uno se apaga o se enciende en su mitad.
    assert sale.end == pytest.approx(corte) and entra.start == pytest.approx(corte)

    arr = muestras(AudioMixer(ventana._audio_clips()).stream(0.0, 6.0))
    en_el_corte = rms(arr[int((corte - 0.02) * RATE):int((corte + 0.02) * RATE)])
    normal = rms(arr[int(1.0 * RATE):int(1.5 * RATE)])
    assert en_el_corte < normal * 0.1


def test_la_cruzada_no_se_hunde_en_el_corte(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    corte = segundo.start
    arr = muestras(AudioMixer(ventana._audio_clips()).stream(0.0, 6.0))
    normal = rms(arr[int(1.0 * RATE):int(1.5 * RATE)])
    for t in (corte - 0.3, corte, corte + 0.3):
        tramo = rms(arr[int((t - 0.05) * RATE):int((t + 0.05) * RATE)])
        assert tramo > normal * 0.7


def test_sin_material_antes_el_cruce_empieza_donde_puede(secuencia):
    """Si el que entra arranca en el segundo 0.2 del archivo, solo hay 0.2 s
    para encimar: no se inventa material de antes del principio."""
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    v_a = v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v_b = v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=0.2, link="b"))
    a1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    a1.add(Clip("/b.mp4", 3.0, 3.0, in_point=0.2, link="b"))
    v_b.dissolve = 1.0

    sale, entra = sorted(secuencia.audio_clips(), key=lambda c: c.start)
    assert entra.start == pytest.approx(2.8)
    assert entra.in_point == pytest.approx(0.0)
    assert sale.end == pytest.approx(3.5)
    assert v_a.end == pytest.approx(3.0)


def test_audio_suelto_no_se_toca(secuencia):
    """Si el audio no está enlazado al video, no sabemos que van juntos."""
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=1.0, link="b")).dissolve = 1.0
    sueltos = [a1.add(Clip("/m.wav", 0.0, 3.0)), a1.add(Clip("/m.wav", 3.0, 3.0))]
    assert secuencia.audio_clips() == sueltos


def test_el_ducking_reconoce_las_copias(secuencia):
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    a1.role = "Voz"
    v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=1.0, link="b")).dissolve = 1.0
    a1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    a1.add(Clip("/b.mp4", 3.0, 3.0, in_point=1.0, link="b"))
    voces = secuencia.audio_mix_options()["voices"]
    assert {c.uid for c in secuencia.audio_clips()} == voces


# --- los fundidos y el volumen no se mueven con el cruce -------------------

def par_enlazado(secuencia, in_b=1.0):
    """A en [0, 3] y B en [3, 6], cada uno con su audio enlazado, y una
    cruzada de 1 s en B."""
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v_b = v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=in_b, link="b"))
    a_a = a1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    a_b = a1.add(Clip("/b.mp4", 3.0, 3.0, in_point=in_b, link="b"))
    v_b.dissolve = 1.0
    return a_a, a_b


def nivel(clip, desde: float, segundos: float = 0.1) -> np.ndarray:
    """El nivel que el render le aplica al clip: volumen, fundidos y cruce."""
    import av

    from vortex_studio.media.audio import AudioRenderer

    n = int(round(segundos * RATE))
    unos = av.AudioFrame.from_ndarray(np.ones((2, n), np.float32), format="fltp",
                                      layout="stereo")
    unos.sample_rate = RATE
    return AudioRenderer([clip])._apply_level(unos, clip, desde).to_ndarray()[0]


def test_los_fundidos_siguen_donde_los_pusiste(secuencia):
    """Las copias del cruce empiezan antes o acaban después que el clip, y
    los fundidos se medían contra la copia: el de entrada de B corría medio
    segundo antes y el de salida de A caía pasado el corte."""
    from vortex_studio.media.audio import fade_envelope

    a_a, a_b = par_enlazado(secuencia)
    a_a.fade_out, a_b.fade_in = 0.5, 1.0
    sale, entra = sorted(secuencia.audio_clips(), key=lambda c: c.start)
    assert entra.start < a_b.start and sale.end > a_a.end       # sí hay cruce

    t = np.array([2.5, 2.75, 2.9, 3.0, 3.25, 3.5, 3.75, 4.0])
    assert fade_envelope(sale, t) == pytest.approx(fade_envelope(a_a, t))
    assert fade_envelope(entra, t) == pytest.approx(fade_envelope(a_b, t))


def test_el_volumen_con_keyframes_sigue_en_su_lugar(secuencia):
    """B se calla 1.21 s después de su inicio, en t = 4.21. Con el cruce se
    callaba en 3.71: los keyframes se evaluaban contra la copia, que empieza
    media transición antes."""
    from vortex_studio.model.keyframes import HOLD

    _, a_b = par_enlazado(secuencia)
    a_b.anim = {"gain": [[0.0, 1.0], [1.2, 1.0, HOLD], [1.21, 0.0]]}
    entra = max(secuencia.audio_clips(), key=lambda c: c.start)

    assert nivel(entra, 3.8) == pytest.approx(1.0)
    assert nivel(entra, 4.1) == pytest.approx(1.0)
    assert nivel(entra, 4.3) == pytest.approx(0.0)
    assert a_b.anim["gain"][0] == [0.0, 1.0]           # el del timeline, intacto


def test_en_una_anidada_los_fundidos_tampoco_se_mueven(secuencia):
    """La anidada recorta el clip de la hija y la copia empieza donde empieza
    la anidada: el fundido de entrada del clip —que en la hija ya pasó— se
    volvía a oír ahí."""
    from vortex_studio.media.audio import fade_envelope
    from vortex_studio.model import Sequence
    from vortex_studio.model.project import NestedClip

    hija = Sequence.default()
    hija.audio_tracks()[0].add(Clip("/voz.wav", 0.0, 6.0, fade_in=1.0, fade_out=1.0))
    anidada = secuencia.video_tracks()[-1].add(
        NestedClip(Path(""), 10.0, 3.0, in_point=2.0, sequence_id=hija.id))
    copia = secuencia.audio_clips({hija.id: hija}.get)[0]
    assert copia.start == pytest.approx(10.0)
    t = np.array([10.0, 10.5, 12.9])
    assert fade_envelope(copia, t) == pytest.approx([1.0, 1.0, 1.0])
    # Si la anidada sí llega al final del clip, el de salida sigue ahí.
    anidada.duration = 4.0
    copia = secuencia.audio_clips({hija.id: hija}.get)[0]
    assert fade_envelope(copia, np.array([13.5]))[0] == pytest.approx(0.5)


# --- solo se encima el material que hay -----------------------------------

def test_el_que_sale_no_se_alarga_mas_alla_de_su_archivo(secuencia):
    """A usa su archivo hasta 0.2 s antes del final: no se le puede sacar
    media transición de más. Antes se alargaba igual, el render rellenaba
    con silencio y A se cortaba seco a −3 dB en pleno cruce."""
    par_enlazado(secuencia)
    largos = {"/a.mp4": 3.2, "/b.mp4": 6.0}
    sale, entra = sorted(secuencia.audio_clips(source_duration=lambda p: largos[str(p)]),
                         key=lambda c: c.start)
    assert sale.end == pytest.approx(3.2)
    assert entra.start == pytest.approx(2.5)
    # Las dos curvas en la misma ventana: si no, no suman la misma energía.
    assert sale._xfade == [pytest.approx((2.5, 3.2, False))]
    assert entra._xfade == [pytest.approx((2.5, 3.2, True))]
    t = np.linspace(2.5, 3.2, 29)
    energia = transition_envelope(sale, t) ** 2 + transition_envelope(entra, t) ** 2
    assert energia == pytest.approx(np.ones_like(t), abs=1e-9)


def test_con_poco_material_antes_las_curvas_siguen_parejas(secuencia):
    """B arranca en el segundo 0.2 de su archivo: el cruce empieza 0.2 s
    antes del corte. La curva de A empezaba media transición antes y en el
    corte los dos sumaban menos energía."""
    par_enlazado(secuencia, in_b=0.2)
    sale, entra = sorted(secuencia.audio_clips(), key=lambda c: c.start)
    t = np.linspace(2.8, 3.5, 29)
    energia = transition_envelope(sale, t) ** 2 + transition_envelope(entra, t) ** 2
    assert energia == pytest.approx(np.ones_like(t), abs=1e-9)


def test_sin_material_de_ningun_lado_pasa_por_silencio(secuencia):
    """Dos clips enteros pegados: no hay nada que encimar. En vez de un corte
    seco a −3 dB seguido de un hueco, se apaga uno y se enciende el otro."""
    par_enlazado(secuencia, in_b=0.0)
    sale, entra = sorted(secuencia.audio_clips(source_duration=lambda p: 3.0),
                         key=lambda c: c.start)
    assert sale.end == pytest.approx(3.0) and entra.start == pytest.approx(3.0)
    assert sale._xfade == [pytest.approx((2.5, 3.0, False))]
    assert entra._xfade == [pytest.approx((3.0, 3.5, True))]


def test_sin_saber_cuanto_dura_el_archivo_se_alarga_como_antes(secuencia):
    par_enlazado(secuencia)
    sale, entra = sorted(secuencia.audio_clips(source_duration=lambda p: None),
                         key=lambda c: c.start)
    assert sale.end == pytest.approx(3.5) and entra.start == pytest.approx(2.5)


def test_dos_clips_enteros_no_se_cortan_seco(ventana, media):
    """Lo de siempre: dos clips completos uno tras otro y una cruzada. El que
    sale no tiene material después de su final, y eso sonaba peor que un
    corte: se cortaba a −3 dB y luego venía un hueco casi mudo."""
    ventana._place_video(media["sonoro"])
    ventana._place_video(media["sonoro"])
    _, segundo = ventana.sequence.video_tracks()[-1].clips
    ventana.timeline.select(segundo)
    ventana.set_dissolve(1.0)
    corte = segundo.start
    sale, entra = audio_de(ventana)
    assert sale.end == pytest.approx(corte) and entra.start == pytest.approx(corte)

    arr = muestras(AudioMixer(ventana._audio_clips()).stream(0.0, corte + 1.0))
    normal = rms(arr[int(1.0 * RATE):int(1.5 * RATE)])
    justo_antes = rms(arr[int((corte - 0.03) * RATE):int(corte * RATE)])
    assert justo_antes < normal * 0.1          # bajó hasta cero, no se cortó a −3 dB


# --- una sola vez por par de audios ----------------------------------------

def test_dos_pistas_de_video_con_transicion_cruzan_el_audio_una_vez(secuencia):
    """Un grupo enlazado V1 + V2 + A1 (un cuadro dentro del cuadro) partido en
    el mismo punto, con transición en las dos mitades de video. El par de
    audio se cruzaba una vez por pista de video: el doble de alargue y dos
    curvas multiplicadas, que ya no son de potencia constante."""
    v2, v1 = secuencia.video_tracks()
    a1 = secuencia.audio_tracks()[0]
    for pista in (v2, v1, a1):
        pista.add(Clip("/a.mp4", 0.0, 3.0, in_point=0.1, link="izq"))
        pista.add(Clip("/a.mp4", 3.0, 3.0, in_point=3.1, link="der"))
    v2.clips[1].dissolve = 0.6
    v1.clips[1].dissolve = 1.0

    sale, entra = sorted(secuencia.audio_clips(), key=lambda c: c.start)
    # Gana la más larga, y se aplica una sola vez.
    assert sale._xfade == [pytest.approx((2.5, 3.5, False))]
    assert entra._xfade == [pytest.approx((2.5, 3.5, True))]
    assert sale.end == pytest.approx(3.5)
    assert entra.start == pytest.approx(2.5) and entra.in_point == pytest.approx(2.6)


def test_la_exportacion_suena_igual_que_el_play(ventana, media, tmp_path):
    """La cola de render armaba el audio sin saber cuánto duran los archivos:
    al exportar, el que sale se alargaba más allá de su final y el archivo se
    cortaba a −3 dB justo donde el play ya pasaba por silencio."""
    import time

    import av
    from PySide6.QtWidgets import QApplication

    ventana._place_video(media["sonoro"])
    ventana._place_video(media["sonoro"])
    _, segundo = ventana.sequence.video_tracks()[-1].clips
    ventana.timeline.select(segundo)
    ventana.set_dissolve(1.0)
    corte = segundo.start

    job = ventana.queue_export(tmp_path / "cruce.mp4", 0.0, corte + 1.0, "Borrador")
    assert ventana.render_queue.wait(60), "la exportación no terminó"
    fin = time.monotonic() + 2
    while time.monotonic() < fin:
        QApplication.processEvents()
    assert job.path.exists(), job.error

    with av.open(str(job.path)) as contenedor:
        flujo = contenedor.streams.audio[0]
        tasa = flujo.rate
        arr = np.concatenate([f.to_ndarray()[0] for f in contenedor.decode(flujo)])
    normal = rms(arr[int(1.0 * tasa):int(1.5 * tasa)])
    justo_antes = rms(arr[int((corte - 0.03) * tasa):int(corte * tasa)])
    assert justo_antes < normal * 0.15
