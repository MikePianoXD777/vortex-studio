"""Mezcla de pistas de audio: dos clips encimados tienen que oírse los dos."""

from vortex_studio.media.audio import RATE
from vortex_studio.media.mixer import AudioMixer, lanes
from vortex_studio.model import Clip

from test_audio import energia


def clip(media, start, duration, **kw):
    return Clip(source=media["sonoro"], start=start, duration=duration, **kw)


# --- reparto en carriles --------------------------------------------------

def test_clips_pegados_caben_en_un_carril(media):
    uno = clip(media, 0.0, 2.0)
    dos = clip(media, 2.0, 2.0)
    assert len(lanes([uno, dos])) == 1


def test_dos_clips_encimados_piden_dos_carriles(media):
    uno = clip(media, 0.0, 3.0)
    dos = clip(media, 1.0, 3.0)
    assert len(lanes([uno, dos])) == 2


def test_el_reparto_usa_el_minimo_de_carriles(media):
    """Tres clips con solo dos encimados a la vez caben en dos carriles."""
    a = clip(media, 0.0, 2.0)
    b = clip(media, 1.0, 2.0)
    c = clip(media, 2.5, 2.0)
    carriles = lanes([a, b, c])
    assert len(carriles) == 2
    assert [len(x) for x in carriles] == [2, 1]


def test_el_reparto_no_depende_del_orden_de_entrada(media):
    a = clip(media, 4.0, 1.0)
    b = clip(media, 0.0, 1.0)
    assert len(lanes([a, b])) == 1
    assert len(lanes([b, a])) == 1


def test_sin_clips_no_hay_carriles():
    assert lanes([]) == []


# --- mezcla ---------------------------------------------------------------

def test_un_solo_carril_no_monta_mezcla(media):
    """El caso común no paga nada por que exista el mezclador."""
    mixer = AudioMixer([clip(media, 0.0, 2.0)])
    assert mixer.count == 1
    frames = list(mixer.stream(0.0, 2.0))
    assert abs(sum(f.samples for f in frames) - 2 * RATE) < RATE * 0.02


def test_dos_clips_encimados_suman(media):
    """Era el bug: el segundo clip se perdía porque el cursor ya iba pasado."""
    solo = list(AudioMixer([clip(media, 0.0, 4.0)]).stream(0.0, 4.0))
    juntos = list(AudioMixer([clip(media, 0.0, 4.0),
                              clip(media, 0.0, 4.0)]).stream(0.0, 4.0))

    uno = energia(solo, 0.5, 3.5)
    dos = energia(juntos, 0.5, 3.5)
    assert uno > 0.05
    assert 1.7 * uno < dos < 2.3 * uno


def test_la_mezcla_dura_exactamente_lo_pedido(media):
    mixer = AudioMixer([clip(media, 0.0, 3.0), clip(media, 1.0, 3.0)])
    assert mixer.count == 2
    frames = list(mixer.stream(0.0, 5.0))
    assert abs(sum(f.samples for f in frames) - 5 * RATE) < RATE * 0.03


def test_el_clip_de_la_otra_pista_se_oye_en_su_hueco(media):
    """Con el bug, el segundo clip quedaba mudo por entero."""
    encimados = [clip(media, 0.0, 2.0, gain=0.0), clip(media, 0.5, 2.0)]
    frames = list(AudioMixer(encimados).stream(0.0, 3.0))
    assert energia(frames, 1.0, 2.0) > 0.05


def test_el_volumen_de_cada_clip_se_respeta_en_la_mezcla(media):
    fuerte = list(AudioMixer([clip(media, 0.0, 3.0),
                              clip(media, 0.0, 3.0)]).stream(0.0, 3.0))
    suave = list(AudioMixer([clip(media, 0.0, 3.0),
                             clip(media, 0.0, 3.0, gain=0.1)]).stream(0.0, 3.0))
    assert energia(suave, 0.5, 2.5) < energia(fuerte, 0.5, 2.5) * 0.75


def test_sin_audio_la_salida_sigue_durando_lo_mismo():
    """Sin esto, una secuencia sin sonido saldría con el audio recortado."""
    frames = list(AudioMixer([]).stream(0.0, 2.0))
    assert abs(sum(f.samples for f in frames) - 2 * RATE) < RATE * 0.02


def test_la_mezcla_tambien_funciona_en_s16(media):
    """La reproducción usa `s16` entrelazado, no `fltp`.

    `amix` devuelve el formato que a él le acomoda para sumar: pedimos
    `s16` y salió `flt` empaquetado. Leído como enteros de 16 bits eso se
    oye como ruido blanco a todo volumen, y solo al darle play — la
    exportación se veía perfecta. De ahí el `aformat` a la salida.
    """
    mixer = AudioMixer([clip(media, 0.0, 2.0), clip(media, 0.5, 2.0)], fmt="s16")
    assert mixer.count == 2
    frames = list(mixer.stream(0.0, 3.0))
    assert abs(sum(f.samples for f in frames) - 3 * RATE) < RATE * 0.03
    assert all(f.format.name == "s16" for f in frames)
    assert all(len(f.planes) == 1 for f in frames)      # entrelazado
    assert all(f.sample_rate == RATE for f in frames)


def test_tres_carriles_tambien_mezclan(media):
    mixer = AudioMixer([clip(media, 0.0, 3.0), clip(media, 0.5, 3.0),
                        clip(media, 1.0, 3.0)])
    assert mixer.count == 3
    frames = list(mixer.stream(0.0, 4.0))
    assert abs(sum(f.samples for f in frames) - 4 * RATE) < RATE * 0.03
    assert energia(frames, 1.5, 2.5) > 0.05
