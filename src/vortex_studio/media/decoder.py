"""Decodificación de video con PyAV (FFmpeg).

PyAV es opcional: si no está instalado, `HAS_PYAV` queda en False y la app
arranca igual, solo que sin imagen. Nunca revienta al importar.

Esta capa no sabe nada de Qt: entrega pixeles crudos en RGB y que la UI
arme la imagen.
"""

from __future__ import annotations

import math
import struct
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from vortex_studio.media.color import ColorProcessor
from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.project import SAMPLE_BLEND, SAMPLE_FLOW

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False


@dataclass(frozen=True)
class Frame:
    """Un frame decodificado, en RGB de 8 bits.

    `stride` son los bytes por renglón. FFmpeg alinea los renglones, así que
    puede ser mayor que `width * 3`: hay que respetarlo o la imagen sale
    inclinada.
    """

    data: bytes
    width: int
    height: int
    stride: int
    alpha: bool = False     # RGBA en vez de RGB: trae transparencia (llave de croma)


def blend_frames(a: Frame, b: Frame, amount: float) -> Frame:
    """`a` y `b` mezclados: 0 es todo `a`, 1 todo `b`. En NumPy, con pesos enteros."""
    if (a.width, a.height, a.stride, a.alpha) != (b.width, b.height, b.stride, b.alpha):
        return a if amount < 0.5 else b
    peso = int(round(max(0.0, min(1.0, amount)) * 256))
    x = np.frombuffer(a.data, dtype=np.uint8).astype(np.uint16)
    y = np.frombuffer(b.data, dtype=np.uint8).astype(np.uint16)
    mezcla = (x * (256 - peso) + y * peso + 128) >> 8
    return Frame(mezcla.astype(np.uint8).tobytes(), a.width, a.height, a.stride, a.alpha)


FLOW_STEPS = 16


def flow_frame(a: Frame, b: Frame, amount: float) -> Frame:
    """El cuadro de en medio siguiendo el movimiento, con `minterpolate`.

    El filtro está hecho para subir los fps de un video entero, no para un
    par suelto: con dos cuadros no suelta nada. Se le da `a`, y `b` tres
    veces —relleno para que su ventana tenga con qué trabajar— a un cuadro
    por segundo, se le pide `FLOW_STEPS` por segundo y se toma el más cercano
    a `amount`. Medido sobre un cuadrito que se mueve, cae exactamente a la
    mitad del camino; sobre textura, se equivoca la mitad que una mezcla.

    Cuesta: más de un segundo por cuadro de 720p. Por eso la zona se marca
    en rojo para renderizarla, como en Premiere.
    """
    def arreglo(frame: Frame) -> np.ndarray:
        crudo = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.stride)
        return np.ascontiguousarray(crudo[:, :frame.width * 3].reshape(frame.height, frame.width, 3))

    grafo = av.filter.Graph()
    fuente = grafo.add("buffer", f"video_size={a.width}x{a.height}:pix_fmt=rgb24"
                                 f":time_base=1/1:frame_rate=1/1:pixel_aspect=1/1")
    anterior = fuente
    for nodo in (grafo.add("format", "yuv444p"),
                 grafo.add("minterpolate", f"fps={FLOW_STEPS}:mi_mode=mci:mc_mode=aobmc"
                                           f":me_mode=bidir:vsbmc=1:scd=none"),
                 grafo.add("format", "rgb24"),
                 grafo.add("buffersink")):
        anterior.link_to(nodo)
        anterior = nodo
    grafo.configure()

    salidas = []
    for indice, datos in enumerate((arreglo(a), arreglo(b), arreglo(b), arreglo(b))):
        cuadro = av.VideoFrame.from_ndarray(datos, format="rgb24")
        cuadro.pts, cuadro.time_base = indice, Fraction(1, 1)
        grafo.push(cuadro)
        while True:
            try:
                salidas.append(grafo.pull())
            except (av.error.BlockingIOError, av.error.EOFError):
                break
        if any(s.pts is not None and float(s.pts * s.time_base) >= amount - 1e-9
               for s in salidas):
            break
    if not salidas:
        return blend_frames(a, b, amount)
    mejor = min(salidas, key=lambda s: abs(float(s.pts * s.time_base) - amount))
    rgb = mejor.reformat(format="rgb24")
    plano = rgb.planes[0]
    return Frame(bytes(plano), rgb.width, rgb.height, plano.line_size)


# Cuánto puede quedar el instante pedido después del cuadro y seguir siendo
# ese cuadro. Los trabajos del servidor redondean el tiempo a 4 decimales: con
# 1e-6, a 29.97 fps el redondeo a veces caía un pelo después del cuadro, se
# servía el siguiente y el que venía repetía ese mismo.
TOLERANCIA = 1e-4


def frame_rotation(frame) -> int:
    """Cuánto hay que girar el cuadro para verlo derecho, en grados.

    Un celular grabando vertical guarda la imagen acostada y aparte una
    matriz que dice cómo girarla. Quien no la lee muestra el video de lado;
    los reproductores y `ffmpeg` la aplican solos. FFmpeg la entrega cruda
    —nueve enteros en coma fija— y de ahí sale el ángulo.
    """
    datos = None
    for parte in getattr(frame, "side_data", None) or ():
        if getattr(getattr(parte, "type", None), "name", "") == "DISPLAYMATRIX":
            datos = bytes(parte)
            break
    if not datos or len(datos) < 36:
        return 0
    matriz = struct.unpack("<9i", datos[:36])
    grados = round(-math.degrees(math.atan2(matriz[1] / 65536.0, matriz[0] / 65536.0)))
    return grados % 360 if grados % 90 == 0 else 0


def rotate_rgb(datos: np.ndarray, grados: int) -> np.ndarray:
    """Gira el arreglo de pixeles para que quede como lo muestra ffmpeg.

    El lado se comprobó contra el propio ffmpeg, que aplica el giro solo al
    exportar un cuadro: con la marca de 90 el cuadro coincide exacto.
    """
    vueltas = {90: 1, 180: 2, 270: 3}.get(grados % 360)
    if not vueltas:
        return datos
    return np.ascontiguousarray(np.rot90(datos, vueltas))


class VideoSource:
    """Lee frames de un archivo de video por tiempo, no por orden.

    Mantiene abierto el contenedor y hace seek al keyframe anterior al tiempo
    pedido, avanzando hasta el frame correcto. Guarda el último frame servido
    para que arrastrar el playhead hacia adelante no vuelva a hacer seek.
    """

    def __init__(self, path: str | Path) -> None:
        if not HAS_PYAV:
            raise RuntimeError("PyAV no está instalado: no se puede decodificar video")

        self.path = Path(path)
        self._container = av.open(str(self.path))
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"

        self.width = self._stream.codec_context.width
        self.height = self._stream.codec_context.height
        self.fps = float(self._stream.average_rate or 30)
        self.rotation = 0               # lo dice el primer cuadro que se decodifique
        self.duration = float(self._container.duration / av.time_base) if self._container.duration else 0.0
        inicio = self._stream.start_time
        self._origin = float(inicio * self._stream.time_base) if inicio is not None else 0.0
        self._recent: OrderedDict[tuple, Frame] = OrderedDict()   # vecinos para mezclar

        self._last_time = -1.0
        self._next_time = float("-inf")     # cuándo empieza el cuadro que sigue al que se tiene
        self._pending = None                # ese cuadro, ya decodificado
        self._gen = None                    # la decodificación en curso
        self._raw = None
        self._tail: float | None = None     # cuándo cae el último cuadro, si ya se buscó
        self._cached: Frame | None = None
        self._color = ColorProcessor()
        self._applied: tuple | None = None

    def frame_at(self, t: float, adjust: ColorAdjust | None = None,
                 key=None, sampling: str | None = None) -> Frame | None:
        """Devuelve el frame que se ve en el segundo `t`, ya corregido.

        Con `sampling` en mezcla o flujo óptico, un instante que cae entre
        dos cuadros del archivo sale de los dos. Ver `_between`.
        """
        t = max(0.0, t)
        if sampling in (SAMPLE_BLEND, SAMPLE_FLOW) and self.fps > 0:
            entre = self._between(t, adjust, key, sampling)
            if entre is not None:
                return entre
        # De aquí para abajo se trabaja con los tiempos del archivo, que no
        # siempre empiezan en cero: mucho material de cámara trae su primer
        # cuadro en otro segundo. Sin sumar ese arranque, todo lo que se pedía
        # caía antes del primer cuadro y el clip se veía congelado.
        t += self._origin
        self._key = key
        settings = self._settings(adjust) + (key.signature if key is not None else (),)

        # Más allá del último cuadro se sostiene el último, sin volver a buscarlo.
        if (self._tail is not None and self._cached is not None and t >= self._tail - 1e-6
                and abs(self._last_time - self._tail) < 1e-9):
            return self._cached if settings == self._applied else self._recolor(adjust)

        # Si el instante cae en el cuadro que ya se tiene —desde que empieza
        # hasta que empieza el siguiente— no hay que decodificar nada; si
        # cambió el color, se vuelve a filtrar el mismo. Así mover un
        # deslizador con el video en pausa se siente inmediato, y reproducir
        # no vuelve a buscar el keyframe cada vez que el reloj pide un
        # instante un pelo antes o después del cuadro recién servido.
        if self._cached is not None and self._covers(t):
            return self._cached if settings == self._applied else self._recolor(adjust)

        # Solo hacemos seek si vamos hacia atrás o saltamos lejos; avanzar
        # poco a poco es mucho más barato decodificando en orden.
        if self._cached is None or t < self._last_time - TOLERANCIA or t - self._last_time > 1.0:
            self._seek(t)

        try:
            hallado = self._decode_until(t, adjust, key, settings)
        except av.error.EOFError:
            # Con hilos el decodificador lee por adelantado: en un archivo
            # corto, o cerca del final, ya se vació, y pedirle otro cuadro
            # hacia adelante sin buscar truena con fin de archivo. Se vuelve a
            # buscar y se intenta una vez más.
            self._seek(t)
            hallado = self._decode_until(t, adjust, key, settings)
        return hallado if hallado is not None else self._hold_last(adjust, key, settings)

    def _covers(self, t: float) -> bool:
        """¿El cuadro que se tiene es el que se ve en `t`?"""
        if abs(t - self._last_time) < TOLERANCIA:
            return True
        return self._last_time - TOLERANCIA <= t < self._next_time - TOLERANCIA

    def _next_decoded(self):
        """El siguiente cuadro en orden: el que sobró de la vuelta anterior, o uno nuevo."""
        if self._pending is not None:
            frame, self._pending = self._pending, None
            return frame
        if self._gen is None:
            self._gen = self._container.decode(self._stream)
        try:
            return next(self._gen)
        except StopIteration:
            self._gen = None
            return None

    def _decode_until(self, t: float, adjust, key, settings: tuple) -> Frame | None:
        """Decodifica en orden hasta el cuadro que se ve en `t`.

        El que se ve es el último que empieza en `t` o antes, y para saberlo
        hay que sacar uno de más: ese se guarda y es el primero que se mira la
        próxima vez. Antes se entregaba el primero que empezaba en `t` o
        después, que entre dos cuadros es el siguiente: la cámara lenta con
        cuadro más cercano iba un cuadro adelantada, y en el monitor la
        estabilización corregía con un cuadro de retraso.
        """
        previo = None
        while True:
            frame = self._next_decoded()
            if frame is None:
                break
            when = float(frame.pts * self._stream.time_base) if frame.pts is not None else t
            if when <= t + TOLERANCIA:
                previo = (frame, when)
                continue
            if previo is None:
                # Se pidió antes del primer cuadro que hay: se da ese.
                return self._keep(frame, when, float("inf"), adjust, key, settings)
            self._pending = frame
            return self._keep(previo[0], previo[1], when, adjust, key, settings)
        if previo is not None:
            # Se acabó el archivo: el último cuadro vale para lo que siga.
            return self._keep(previo[0], previo[1], float("inf"), adjust, key, settings)
        return None

    def _keep(self, frame, when: float, siguiente: float, adjust, key, settings: tuple) -> Frame:
        """Deja ese cuadro como el que se tiene, válido hasta `siguiente`."""
        if frame is not self._raw or settings != self._applied or self._cached is None:
            self._raw = frame
            self._applied = settings
            self._cached = self._to_rgb(self._color.apply(frame, adjust, key)
                                        if adjust or key else frame)
        self._last_time = when
        self._next_time = siguiente
        return self._cached

    def _hold_last(self, adjust, key, settings: tuple) -> Frame | None:
        """El último cuadro del archivo, para lo que se pida después del final.

        Un clip estirado más allá de su material —o con un punto de entrada
        pasado de largo— se quedaba en negro: el seek caía después del
        último cuadro, no salía ninguno, y el servidor daba el cuadro por
        perdido. Ahora se sostiene el último, como un cuadro congelado.
        """
        final = self._origin + max(0.0, self.duration - 2.0)
        self._container.seek(int(final / self._stream.time_base),
                             stream=self._stream, backward=True, any_frame=False)
        self._gen = None
        self._pending = None
        self._next_time = float("inf")
        ultimo = None
        for frame in self._container.decode(self._stream):
            ultimo = frame
        if ultimo is None:
            return self._cached
        when = float(ultimo.pts * self._stream.time_base) if ultimo.pts is not None else 0.0
        self._tail = self._last_time = when
        self._raw = ultimo
        self._applied = settings
        self._cached = self._to_rgb(self._color.apply(ultimo, adjust, key)
                                    if adjust or key else ultimo)
        return self._cached

    def _between(self, t: float, adjust, key, sampling: str) -> Frame | None:
        """El cuadro de un instante entre dos cuadros del archivo, o None si cae en uno.

        En cámara lenta a 0.25× cada cuadro del archivo se repite cuatro
        veces y la imagen avanza a saltos. Aquí se toman los dos vecinos y se
        mezclan, o se inventa el de en medio con flujo óptico.

        Los dos vecinos se recuerdan: el siguiente instante casi siempre cae
        entre los mismos dos, y sin recordarlos cada cuadro volvería a buscar
        hacia atrás en el archivo.
        """
        posicion = t * self.fps          # `t` ya viene contado desde el material
        n = math.floor(posicion + 1e-6)
        fraccion = posicion - n
        if n < 0 or fraccion < 0.02 or fraccion > 0.98:
            return None
        antes = self._grid(n, adjust, key)
        despues = self._grid(n + 1, adjust, key)
        if antes is None or despues is None:
            return antes or despues
        if sampling == SAMPLE_FLOW and not antes.alpha and not despues.alpha:
            try:
                return flow_frame(antes, despues, fraccion)
            except Exception:
                pass            # un grafo que no se pudo armar: mejor mezcla que negro
        return blend_frames(antes, despues, fraccion)

    def _grid(self, n: int, adjust, key) -> Frame | None:
        firma = self._settings(adjust) + (key.signature if key is not None else (),)
        clave = (n, firma)
        listo = self._recent.get(clave)
        if listo is not None:
            return listo
        cuadro = self.frame_at(n / self.fps, adjust, key)
        if cuadro is not None:
            self._recent[clave] = cuadro
            while len(self._recent) > 4:
                self._recent.popitem(last=False)
        return cuadro

    def _recolor(self, adjust: ColorAdjust | None) -> Frame | None:
        """Vuelve a filtrar el último cuadro decodificado, sin volver a leerlo."""
        raw = getattr(self, "_raw", None)
        if raw is None:
            return self._cached
        llave = getattr(self, "_key", None)
        self._applied = self._settings(adjust) + (llave.signature if llave is not None else (),)
        self._cached = self._to_rgb(self._color.apply(raw, adjust, llave)
                                    if adjust or llave else raw)
        return self._cached

    @staticmethod
    def _settings(adjust: ColorAdjust | None) -> tuple:
        """Ver `ColorAdjust.signature`: aquí antes se comparaban solo cuatro
        ajustes, y cambiar cualquier otro con el video en pausa avanzaba un
        cuadro en vez de recolorear el que ya estaba."""
        if adjust is None:
            return ()
        return adjust.signature

    def _seek(self, t: float) -> None:
        offset = int(t / self._stream.time_base)
        self._container.seek(offset, stream=self._stream, backward=True, any_frame=False)
        # Lo que se tenía ya no sirve: el cuadro guardado es de otro lugar
        # del archivo, y el que sobró también.
        self._last_time = t
        self._next_time = float("-inf")
        self._pending = None
        self._gen = None
        self._cached = None

    def _to_rgb(self, frame) -> Frame:
        """Convierte a RGB —o RGBA si trae alfa— y lo deja derecho."""
        giro = frame_rotation(frame)
        if giro:
            self.rotation = giro
            if giro % 180:
                self.width, self.height = self.height, self.width

        if frame.format.name == "rgba":
            plane = frame.planes[0]
            if not self.rotation:
                return Frame(bytes(plane), frame.width, frame.height, plane.line_size, True)
            crudo = np.frombuffer(bytes(plane), dtype=np.uint8).reshape(
                frame.height, plane.line_size)[:, :frame.width * 4].reshape(
                frame.height, frame.width, 4)
            girado = rotate_rgb(crudo, self.rotation)
            return Frame(girado.tobytes(), girado.shape[1], girado.shape[0],
                         girado.shape[1] * 4, True)

        rgb = frame.reformat(format="rgb24")
        plane = rgb.planes[0]
        if not self.rotation:
            return Frame(bytes(plane), rgb.width, rgb.height, plane.line_size)
        crudo = np.frombuffer(bytes(plane), dtype=np.uint8).reshape(
            rgb.height, plane.line_size)[:, :rgb.width * 3].reshape(
            rgb.height, rgb.width, 3)
        girado = rotate_rgb(crudo, self.rotation)
        return Frame(girado.tobytes(), girado.shape[1], girado.shape[0],
                     girado.shape[1] * 3)

    def close(self) -> None:
        self._container.close()

    def __enter__(self) -> VideoSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# Códecs de imagen fija. Un PNG abierto con FFmpeg también es un "stream de
# video", así que por sí solo eso no distingue una foto de un clip.
STILL_CODECS = {"png", "mjpeg", "webp", "bmp", "gif", "tiff", "jpeg2000"}


def probe_media(path: str | Path):
    """Todo lo que se puede saber del archivo sin decodificarlo.

    Distingue tres clases de archivo, porque cada una va a otra pista:

    - **imagen**: un solo cuadro con códec de imagen fija;
    - **audio**: sin video, o con video que solo es la carátula del disco
      (un MP3 con portada trae un "stream de video" de un cuadro);
    - **video**: todo lo demás.
    """
    from vortex_studio.model.media import AUDIO, IMAGE, VIDEO, MediaInfo

    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado: no se puede sondear")

    with av.open(str(path)) as container:
        video = container.streams.video[0] if container.streams.video else None
        audio = container.streams.audio[0] if container.streams.audio else None

        if video is not None and _is_cover_art(video):
            video = None

        duration = 0.0
        if container.duration:
            duration = float(container.duration / av.time_base)
        elif video is not None and video.duration and video.time_base:
            duration = float(video.duration * video.time_base)
        elif audio is not None and audio.duration and audio.time_base:
            duration = float(audio.duration * audio.time_base)

        info = MediaInfo(path=Path(path), duration=duration)

        if video is not None:
            codec = video.codec_context.name or ""
            info.video_codec = codec
            info.width = video.codec_context.width
            info.height = video.codec_context.height
            info.fps = float(video.average_rate or 0) or 30.0
            # Vertical de celular: la imagen viene acostada con una marca de
            # giro. El tamaño que importa es el que se ve.
            if rotation_of(container, video) % 180:
                info.width, info.height = info.height, info.width
            info.color_transfer = _transfer_name(video)
            info.kind = IMAGE if codec in STILL_CODECS and (video.frames or 0) <= 1 else VIDEO
        else:
            info.kind = AUDIO

        if audio is not None:
            info.audio_codec = audio.codec_context.name or ""
            info.channels = audio.codec_context.channels or 0
            info.sample_rate = audio.codec_context.sample_rate or 0

    return info


def rotation_of(container, stream) -> int:
    """El giro del archivo, del primer cuadro que se pueda decodificar."""
    try:
        for cuadro in container.decode(stream):
            return frame_rotation(cuadro)
    except Exception:
        return 0
    finally:
        try:
            container.seek(0, stream=stream)
        except Exception:
            pass
    return 0


_TRANSFERS = {16: "smpte2084", 18: "arib-std-b67"}


def _transfer_name(stream) -> str:
    """La curva de transferencia que declara el video, en el nombre de FFmpeg."""
    try:
        valor = stream.codec_context.color_trc
    except Exception:
        return ""
    nombre = getattr(valor, "name", None)
    if nombre:
        return str(nombre).lower().replace("_", "-")
    try:
        return _TRANSFERS.get(int(valor), "")
    except (TypeError, ValueError):
        return ""


def _is_cover_art(stream) -> bool:
    try:
        return bool(stream.disposition & av.stream.Disposition.attached_pic)
    except Exception:           # PyAV viejo sin `Disposition`
        return False


def probe(path: str | Path) -> dict:
    """Datos básicos del archivo, sin decodificar nada.

    Se queda por compatibilidad; lo nuevo usa `probe_media`, que además
    trae códecs y canales y no truena con un archivo que solo tiene audio.
    """
    if not HAS_PYAV:
        return {}

    info = probe_media(path)
    return {
        "width": info.width,
        "height": info.height,
        "fps": info.fps or 30.0,
        "duration": info.duration,
    }
