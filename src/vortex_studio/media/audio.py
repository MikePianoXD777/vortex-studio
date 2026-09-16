"""Lectura de audio: picos para el timeline y el audio de cada clip.

La onda completa, con mínimo y máximo y caché en disco, vive en
`media/waveform.py`. Aquí queda `peaks()`, que la resume en picos de 0 a 1.
Se saca el pico y no el promedio a propósito: promediar aplana los golpes,
que es justo lo que uno busca cuando mira una onda para cortar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np

from vortex_studio.media.waveform import compute as compute_waveform
from vortex_studio.model.keyframes import evaluate_many
from vortex_studio.model.project import KEEP_PITCH, MUTE_AUDIO, SHIFT_PITCH

try:
    import av
    from av.audio.fifo import AudioFifo
    from av.audio.resampler import AudioResampler

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

PEAK_RATE = 8000          # frecuencia a la que se mide la onda
RATE = 48000              # frecuencia de salida al exportar
LAYOUT = "stereo"
FORMAT = "fltp"


def silence(seconds: float, rate: int = RATE,
            layout: str = LAYOUT, fmt: str = FORMAT) -> Iterator:
    """Bloques de silencio que suman `seconds`.

    Vive suelta y no dentro de `AudioRenderer` porque el mezclador también
    la necesita: cuando no hay ninguna pista con sonido, la salida sigue
    teniendo que durar lo mismo que la imagen.
    """
    pendientes = int(round(seconds * rate))
    while pendientes > 0:
        bloque = min(pendientes, rate)
        frame = av.AudioFrame(format=fmt, layout=layout, samples=bloque)
        frame.sample_rate = rate
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        yield frame
        pendientes -= bloque


def has_audio(path: str | Path) -> bool:
    if not HAS_PYAV:
        return False
    try:
        with av.open(str(path)) as container:
            return bool(container.streams.audio)
    except Exception:
        return False


def peaks(path: str | Path, per_second: int = 60) -> list[float]:
    """Picos normalizados de 0 a 1, `per_second` por cada segundo de audio."""
    datos = compute_waveform(path, per_second)
    if datos.shape[1] == 0:
        return []
    return np.maximum(np.abs(datos[0]), np.abs(datos[1])).clip(0.0, 1.0).tolist()


def fade_envelope(clip, tiempos: np.ndarray) -> np.ndarray:
    """La opacidad de los fundidos, muestra por muestra.

    Es la misma cuenta que `fade_at` del modelo, pero sobre un arreglo de
    tiempos en vez de un solo instante: si los dos fundidos no caben en el
    clip se reparten a prorrata, y cada uno es una rampa lineal.
    """
    alfa = np.ones_like(tiempos, dtype=np.float64)
    entrada = float(getattr(clip, "fade_in", 0.0))
    salida = float(getattr(clip, "fade_out", 0.0))
    if entrada <= 0 and salida <= 0:
        return alfa

    duracion = float(clip.duration)
    total = entrada + salida
    if total > duracion > 0:
        factor = duracion / total
        entrada, salida = entrada * factor, salida * factor

    dentro = tiempos - clip.start
    if entrada > 0:
        alfa = np.minimum(alfa, np.clip(dentro / entrada, 0.0, 1.0))
    if salida > 0:
        alfa = np.minimum(alfa, np.clip((duracion - dentro) / salida, 0.0, 1.0))
    return alfa


class AudioRenderer:
    """Arma la pista de audio de salida recorriendo los clips en orden.

    Va hacia adelante y nunca regresa, que es como avanza una exportación.
    Eso permite ir decodificando en corrido en vez de hacer un seek por cada
    cuadro, que sería inservible.

    Los huecos entre clips se rellenan con silencio: sin eso, el audio se
    recorrería y perdería la sincronía con la imagen a partir del hueco.
    """

    def __init__(self, clips: list, rate: int = RATE,
                 layout: str = LAYOUT, fmt: str = FORMAT) -> None:
        self.clips = sorted(clips, key=lambda c: c.start)
        self.rate = rate
        self.layout = layout
        self.format = fmt

    def stream(self, start: float, end: float) -> Iterator:
        """Entrega cuadros de audio que cubren exactamente [start, end)."""
        if not HAS_PYAV:
            return

        cursor = start
        for clip in self.clips:
            if clip.end <= cursor or clip.start >= end:
                continue

            if clip.start > cursor:
                yield from self._silence(clip.start - cursor)
                cursor = clip.start

            # `source_time` y no `in_point + (cursor - start)`: la cuenta vieja
            # ignoraba la velocidad, y el audio de un clip a 2× que empezaba
            # a oírse a la mitad salía de otro punto del archivo.
            desde = clip.source_time(cursor)
            hasta = min(clip.end, end)
            fuente = self._from_clip(clip, desde, hasta - cursor)
            fx = getattr(clip, "audio_fx", None)
            if fx is not None and not fx.is_neutral:
                fuente = self._with_fx(fx, fuente, int(round((hasta - cursor) * self.rate)))
            for frame in fuente:
                yield self._apply_level(frame, clip, cursor)
                cursor += frame.samples / self.rate
            cursor = hasta

        if cursor < end:
            yield from self._silence(end - cursor)

    # --- volumen y fundidos -----------------------------------------------

    def _apply_level(self, frame, clip, cuando: float):
        """Aplica volumen y fundidos del clip a un bloque de audio.

        Con una rampa **muestra por muestra**, multiplicando con NumPy.

        Antes el nivel se calculaba una sola vez al centro de cada bloque y
        se aplicaba con el filtro `volume` de FFmpeg. Con bloques de un
        segundo, un fundido de tres segundos eran tres escalones de volumen:
        yo había escrito que el oído no distinguía la escalera de la rampa,
        y en una voz sí se oye, como tres saltos. Con NumPy la multiplicación
        corre en C igual que el filtro, pero con un nivel por muestra.
        """
        n = frame.samples
        tiempos = cuando + np.arange(n, dtype=np.float64) / self.rate
        puntos = (getattr(clip, "anim", None) or {}).get("gain")
        if puntos:
            # Volumen con keyframes: evaluado muestra por muestra, igual que
            # los fundidos, para que una subida no se oiga en escalones.
            ganancia = np.maximum(0.0, evaluate_many(puntos, tiempos - clip.start))
        else:
            ganancia = max(0.0, float(getattr(clip, "gain", 1.0)))
        nivel = ganancia * fade_envelope(clip, tiempos)

        if np.all(np.abs(nivel - 1.0) < 1e-4):
            return frame            # nada que hacer: ni se copia el bloque

        datos = frame.to_ndarray()
        if frame.format.is_planar:
            datos = datos * nivel[np.newaxis, :]
        else:
            canales = len(frame.layout.channels)
            datos = datos * np.repeat(nivel, canales)[np.newaxis, :]

        original = frame.to_ndarray().dtype
        if np.issubdtype(original, np.integer):
            limites = np.iinfo(original)
            datos = np.clip(np.rint(datos), limites.min, limites.max)
        salida = av.AudioFrame.from_ndarray(
            np.ascontiguousarray(datos.astype(original)),
            format=frame.format.name, layout=frame.layout.name)
        salida.sample_rate = self.rate
        salida.pts = None
        return salida

    def _silence(self, seconds: float) -> Iterator:
        yield from silence(seconds, self.rate, self.layout, self.format)

    def _from_clip(self, clip, source_start: float, seconds: float) -> Iterator:
        """Saca `seconds` de audio de línea de tiempo, desde `source_start`.

        A velocidad normal es leer y ya. A otra velocidad se leen
        `seconds × velocidad` segundos de archivo y se pasan por un filtro
        que los estira o los encoge a `seconds`:

        - **Mantener tono**: `atempo`, que cambia la duración sin cambiar el
          tono. Es lo que hace Premiere por omisión y lo que uno quiere con
          una voz;
        - **Cambiar tono**: `asetrate` + `aresample`, que es tocar la cinta
          más rápido: más agudo al acelerar, más grave al frenar;
        - **Silenciar**, o un cuadro congelado: silencio del mismo largo.

        Antes el archivo se leía siempre a velocidad normal: un clip a 2×
        sonaba al doble de largo que su imagen y el resto de la pista se
        desfasaba.
        """
        faltan = int(round(seconds * self.rate))
        if faltan <= 0:
            return

        velocidad = float(getattr(clip, "speed", 1.0))
        modo = getattr(clip, "audio_mode", KEEP_PITCH)
        # Con remapeo de tiempo la velocidad cambia dentro del clip, y un
        # audio que acelera y frena a pedazos no se entiende: como en
        # Premiere, el remapeo es solo de la imagen y ese tramo va mudo.
        remapeado = bool((getattr(clip, "anim", None) or {}).get("time"))
        if velocidad <= 0 or modo == MUTE_AUDIO or remapeado:
            yield from self._silence(seconds)
            return

        if abs(velocidad - 1.0) < 1e-6:
            for frame in self._decoded(clip, source_start, faltan):
                faltan -= frame.samples
                yield frame
        else:
            necesarias = int(round(seconds * velocidad * self.rate))
            for frame in self._retimed(clip, source_start, necesarias, faltan,
                                       velocidad, modo):
                faltan -= frame.samples
                yield frame

        if faltan > 0:   # el archivo se acabó antes de tiempo
            yield from self._silence(faltan / self.rate)

    def _retimed(self, clip, source_start: float, necesarias: int, faltan: int,
                 velocidad: float, modo: str) -> Iterator:
        """El audio del archivo pasado por el filtro de velocidad.

        Lo que sale del filtro va a un FIFO para entregar la cantidad exacta
        de muestras: `atempo` trabaja por ventanas y no suelta bloques del
        tamaño que uno le mete. Sin la cuenta exacta, cada clip acelerado
        correría la pista unos milisegundos.
        """
        graph, entrada = self._speed_graph(velocidad, modo)
        salida = AudioFifo()

        # El filtro de velocidad trabaja por ventanas y su salida arranca
        # atrasada respecto de lo que se le mete: medido, 40 ms a 0.5× y
        # 101 ms a 0.25×, o sea el audio adelantándose a la imagen. Se le da
        # un colchón de material de ANTES del punto de entrada y se tira de la
        # salida la parte que le toca: lo que queda empieza en el cuadro justo.
        colchon = min(0.5, max(0.0, source_start))
        extra = int(round(colchon * self.rate))
        # Del colchón se descuenta lo que el filtro ya se come solo.
        retraso = self._speed_delay(velocidad, modo)
        sobran = (int(round((colchon / max(velocidad, 1e-6) - retraso) * self.rate))
                  if extra else 0)
        sobran = max(0, sobran)
        source_start -= colchon
        necesarias += extra

        # Sin material antes del punto de entrada no hay colchón: el hueco que
        # deja el filtro se rellena con ese mismo silencio, para que el sonido
        # no se adelante a la imagen.
        if not extra and retraso > 0:
            hueco = int(round(retraso * self.rate))
            if hueco > 0:
                for cuadro in self._silence(min(hueco, faltan) / self.rate):
                    faltan -= cuadro.samples
                    yield cuadro

        def recortar():
            """Se traga el colchón antes de entregar nada."""
            nonlocal sobran
            while sobran > 0 and salida.samples > 0:
                basura = salida.read(min(sobran, salida.samples))
                if basura is None:
                    return
                sobran -= basura.samples

        def jalar():
            while True:
                try:
                    bloque = graph.pull()
                except (av.error.BlockingIOError, av.error.EOFError, EOFError):
                    return
                bloque.pts = None
                salida.write(bloque)

        for frame in self._decoded(clip, source_start, necesarias):
            frame.pts = None
            entrada.push(frame)
            jalar()
            recortar()
            while salida.samples >= self.rate and faltan > 0:
                trozo = salida.read(min(self.rate, faltan))
                faltan -= trozo.samples
                yield trozo
            if faltan <= 0:
                return

        try:
            entrada.push(None)          # que suelte lo que retiene la ventana
        except Exception:
            pass
        jalar()
        recortar()
        while faltan > 0 and salida.samples > 0:
            trozo = salida.read(min(self.rate, faltan, salida.samples))
            if trozo is None:
                break
            faltan -= trozo.samples
            yield trozo

    def _with_fx(self, fx, frames, total: int) -> Iterator:
        """Pasa el audio del clip por su ecualizador y su compresor.

        Los filtros biquad del ecualizador no retrasan nada y `acompressor`
        no mira hacia adelante, así que salen las mismas muestras que entran;
        igual se cuentan con un FIFO, porque los filtros sueltan bloques del
        tamaño que les acomoda.
        """
        graph = av.filter.Graph()
        entrada = graph.add("abuffer", f"sample_rate={self.rate}:sample_fmt={self.format}"
                                       f":channel_layout={self.layout}:time_base=1/{self.rate}")
        cadena = []
        if not fx.eq_is_flat:
            from vortex_studio.model.audio_fx import HIGH_HZ, LOW_HZ, MID_HZ
            cadena += [
                graph.add("bass", f"g={fx.low:.2f}:f={LOW_HZ}"),
                graph.add("equalizer", f"f={MID_HZ}:width_type=o:width=1.2:g={fx.mid:.2f}"),
                graph.add("treble", f"g={fx.high:.2f}:f={HIGH_HZ}"),
            ]
        if fx.compressor:
            cadena.append(graph.add(
                "acompressor",
                f"threshold={10 ** (fx.threshold / 20):.6f}:ratio={max(1.0, fx.ratio):.3f}"
                f":attack={max(0.01, fx.attack):.3f}:release={max(0.01, fx.release):.3f}"
                f":makeup={max(1.0, 10 ** (fx.makeup / 20)):.4f}"))
        cadena += [graph.add("aformat", f"sample_fmts={self.format}:channel_layouts={self.layout}"
                                        f":sample_rates={self.rate}"),
                   graph.add("abuffersink")]
        anterior = entrada
        for nodo in cadena:
            anterior.link_to(nodo)
            anterior = nodo
        graph.configure()

        salida = AudioFifo()
        faltan = total

        def jalar():
            while True:
                try:
                    bloque = graph.pull()
                except (av.error.BlockingIOError, av.error.EOFError, EOFError):
                    return
                bloque.pts = None
                salida.write(bloque)

        for frame in frames:
            frame.pts = None
            entrada.push(frame)
            jalar()
            while salida.samples > 0 and faltan > 0:
                trozo = salida.read(min(salida.samples, faltan))
                faltan -= trozo.samples
                yield trozo
        try:
            entrada.push(None)
        except Exception:
            pass
        jalar()
        while faltan > 0 and salida.samples > 0:
            trozo = salida.read(min(salida.samples, faltan))
            faltan -= trozo.samples
            yield trozo
        if faltan > 0:
            yield from self._silence(faltan / self.rate)

    # Cuánto se come el filtro al arrancar, por (velocidad, modo). Se mide una
    # vez y se guarda: es una propiedad del filtro, no del material.
    _RETRASOS: dict = {}

    def _speed_delay(self, velocidad: float, modo: str) -> float:
        """Segundos que el filtro pierde al principio de su salida.

        `atempo` trabaja por ventanas y su salida arranca recortada —unos
        37 ms a 0.5× y 76 ms a 0.25×—, sin que los tiempos de salida lo
        digan. Se mide pasándole un golpe seco en un instante conocido y
        viendo dónde sale.
        """
        clave = (round(float(velocidad), 6), modo, self.rate, self.layout)
        if clave in self._RETRASOS:
            return self._RETRASOS[clave]

        retraso = 0.0
        try:
            import numpy as np

            graph, entrada = self._speed_graph(velocidad, modo)
            canales = 2 if self.layout == "stereo" else 1
            largo = self.rate // 2                      # medio segundo basta
            golpe = self.rate // 4                      # con el golpe a la mitad
            datos = np.zeros((canales, largo), dtype=np.float32)
            datos[:, golpe:golpe + 240] = 0.9

            frame = av.AudioFrame.from_ndarray(datos, format="fltp", layout=self.layout)
            frame.sample_rate = self.rate
            frame.pts = None
            entrada.push(frame)
            entrada.push(None)

            salidas = []
            while True:
                try:
                    salidas.append(graph.pull())
                except (av.error.BlockingIOError, av.error.EOFError, EOFError):
                    break
            if salidas:
                sonido = np.concatenate([b.to_ndarray()[0] for b in salidas]).astype("float32")
                donde = int(np.argmax(np.abs(sonido))) / self.rate
                esperado = (golpe / self.rate) / max(velocidad, 1e-6)
                retraso = max(0.0, esperado - donde)
        except Exception:
            retraso = 0.0       # sin medición, se queda como estaba

        self._RETRASOS[clave] = retraso
        return retraso

    def _speed_graph(self, velocidad: float, modo: str):
        """abuffer → (atempo… | asetrate, aresample) → aformat → sink.

        `atempo` solo acepta de 0.5 a 100 por instancia, así que 0.25× son
        dos `atempo=0.5` seguidos. Encadenarlos es lo que recomienda la
        documentación de FFmpeg, y la calidad es la misma que uno solo.
        """
        graph = av.filter.Graph()
        entrada = graph.add(
            "abuffer",
            f"sample_rate={self.rate}:sample_fmt={self.format}"
            f":channel_layout={self.layout}:time_base=1/{self.rate}")

        cadena = []
        if modo == SHIFT_PITCH:
            cadena.append(graph.add("asetrate", f"r={int(round(self.rate * velocidad))}"))
            cadena.append(graph.add("aresample", f"{self.rate}"))
        else:
            resto = velocidad
            while resto < 0.5 - 1e-9:
                cadena.append(graph.add("atempo", "0.5"))
                resto /= 0.5
            cadena.append(graph.add("atempo", f"{resto:.6f}"))

        cadena.append(graph.add(
            "aformat", f"sample_fmts={self.format}:channel_layouts={self.layout}"
                       f":sample_rates={self.rate}"))
        cadena.append(graph.add("abuffersink"))

        anterior = entrada
        for nodo in cadena:
            anterior.link_to(nodo)
            anterior = nodo
        graph.configure()
        return graph, entrada

    def _decoded(self, clip, source_start: float, limite: int) -> Iterator:
        """Hasta `limite` muestras del archivo desde `source_start`, ya
        convertidas al formato de salida. Menos si el archivo se acaba."""
        try:
            container = av.open(str(clip.source))
            stream = container.streams.audio[0]
        except Exception:
            # Un clip sin audio no es un error: aporta lo que haya, o sea nada,
            # y quien llama rellena con silencio.
            return

        resampler = AudioResampler(format=self.format, layout=self.layout, rate=self.rate)
        fifo = AudioFifo()
        faltan = limite
        # El cuadro donde cae el punto de entrada empieza antes que él: hay
        # que tirar las muestras de más. Saltarse el cuadro entero deja hasta
        # 32 ms de error, y en cámara lenta ese error se multiplica por la
        # velocidad: a 0.25× son 124 ms de audio adelantado a la imagen.
        sobran = -1

        try:
            if source_start > 0:
                container.seek(int(source_start / stream.time_base),
                               stream=stream, backward=True)

            for frame in container.decode(stream):
                cuando = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
                if cuando + frame.samples / max(1, frame.sample_rate) < source_start:
                    continue    # todavía vamos antes del punto de entrada

                if sobran < 0:
                    sobran = max(0, int(round((source_start - cuando) * self.rate)))

                for chunk in resampler.resample(frame):
                    chunk.pts = None
                    fifo.write(chunk)

                while sobran > 0 and fifo.samples > 0:
                    basura = fifo.read(min(sobran, fifo.samples))
                    if basura is None:
                        break
                    sobran -= basura.samples

                while fifo.samples >= self.rate and faltan > 0:
                    salida = fifo.read(min(self.rate, faltan))
                    if salida is None:
                        break
                    faltan -= salida.samples
                    yield salida

                if faltan <= 0:
                    break

            # Al terminar el archivo: lo que quedó adentro del resampler, y
            # luego el FIFO hasta vaciarlo.
            #
            # Antes se pedía `fifo.read(1 segundo)` también aquí, y `read`
            # devuelve None si no hay tantas muestras. El pedazo final —hasta
            # un segundo— nunca se leía y se cambiaba por silencio: un clip
            # que llegaba al final de su archivo perdía el cierre de su audio,
            # en el play y en la exportación. Lo destapó una prueba de otra
            # cosa que medía el nivel justo en ese segundo.
            if faltan > 0:
                try:
                    for chunk in resampler.resample(None):
                        chunk.pts = None
                        fifo.write(chunk)
                except Exception:
                    pass

            while faltan > 0 and fifo.samples > 0:
                salida = fifo.read(min(self.rate, faltan, fifo.samples))
                if salida is None:
                    break
                faltan -= salida.samples
                yield salida
        finally:
            container.close()


def frame_seconds(frame) -> float:
    return frame.samples / float(frame.sample_rate or RATE)
