"""Suma varias pistas de audio en una sola.

`AudioRenderer` recorre los clips hacia adelante y nunca regresa, que es lo
que le permite decodificar en corrido. El precio es que no puede oír dos
cosas a la vez: si dos clips se encimaban, el cursor ya iba pasado cuando
llegaba el segundo y ese se perdía. Música y voz encimadas sonaban a música
sola, sin ningún aviso.

Aquí los clips se reparten en **carriles** sin traslape, cada carril se
renderiza con su propio `AudioRenderer`, y los carriles se suman con el
filtro `amix` de FFmpeg.

Los carriles no son las pistas del timeline a propósito: así también se
resuelve el caso de dos clips encimados dentro de la misma pista, que con
una mezcla pista por pista se seguiría perdiendo.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from vortex_studio.media.audio import (
    FORMAT,
    HAS_PYAV,
    LAYOUT,
    RATE,
    AudioRenderer,
    silence,
)

try:
    import av
    from av.audio.fifo import AudioFifo
except ImportError:  # pragma: no cover - depende del entorno
    av = None

BLOCK = 1.0     # segundos de audio por bloque de mezcla


def lanes(clips: list) -> list[list]:
    """Reparte los clips en el menor número de carriles sin traslape.

    Es el reparto codicioso de intervalos: en orden de inicio, cada clip se
    mete al primer carril que ya esté libre, y si no hay ninguno se abre uno
    nuevo. Con la lista ordenada por inicio, ese reparto usa el mínimo de
    carriles posible, que es lo que conviene: cada carril de más es un
    `AudioRenderer` de más abriendo archivos.
    """
    carriles: list[list] = []
    for clip in sorted(clips, key=lambda c: c.start):
        for carril in carriles:
            if carril[-1].end <= clip.start + 1e-9:
                carril.append(clip)
                break
        else:
            carriles.append([clip])
    return carriles


class AudioMixer:
    """La mezcla de todo el audio de la secuencia, lista para exportar o oír.

    Con un solo carril no monta ningún filtro: entrega el `AudioRenderer`
    tal cual. El caso común —una voz, una música, sin encimar— no paga nada
    por la existencia de la mezcla.
    """

    def __init__(self, clips: list, rate: int = RATE,
                 layout: str = LAYOUT, fmt: str = FORMAT,
                 voices=None, ducked=None, depth: float = 12.0) -> None:
        self.lanes = lanes(clips)
        self.rate = rate
        self.layout = layout
        self.format = fmt
        self.voices = set(voices or ())
        self.ducked = set(ducked or ())
        self.depth = depth
        self._duck = _Ducker(rate, depth)

    @property
    def count(self) -> int:
        return len(self.lanes)

    def stream(self, start: float, end: float) -> Iterator:
        """Entrega bloques de audio que cubren exactamente [start, end)."""
        if not HAS_PYAV:
            return

        if not self.lanes:
            yield from silence(end - start, self.rate, self.layout, self.format)
            return

        if len(self.lanes) == 1:
            yield from self._renderer(self.lanes[0]).stream(start, end)
            return

        yield from self._mix(start, end)

    # --- piezas -----------------------------------------------------------

    def _renderer(self, carril: list) -> AudioRenderer:
        return AudioRenderer(carril, self.rate, self.layout, self.format)

    def _mix(self, start: float, end: float) -> Iterator:
        """Empuja un bloque del mismo tamaño por carril y jala la suma.

        Los bloques tienen que ir parejos. `AudioRenderer` no los entrega
        así —al final de cada clip suelta uno corto— así que en medio va un
        FIFO por carril que absorbe la diferencia. Sin eso, `amix` se queda
        esperando al carril más corto y la mezcla sale a tirones.
        """
        fuentes = [self._renderer(c).stream(start, end) for c in self.lanes]
        fifos = [AudioFifo() for _ in fuentes]
        graph, entradas = self._graph(len(fuentes))

        pendientes = int(round((end - start) * self.rate))
        tamano = int(BLOCK * self.rate)

        while pendientes > 0:
            objetivo = min(tamano, pendientes)
            for fifo, fuente in zip(fifos, fuentes):
                while fifo.samples < objetivo:
                    frame = next(fuente, None)
                    if frame is None:
                        break
                    frame.pts = None
                    fifo.write(frame)

            bloque = min(objetivo, min(f.samples for f in fifos))
            if bloque <= 0:
                break

            trozos = [fifo.read(bloque) for fifo in fifos]
            if self.voices and self.ducked:
                inicio = start + (int(round((end - start) * self.rate)) - pendientes) / self.rate
                trozos = self._duck.apply(trozos, self.lanes, inicio, self.voices, self.ducked)
            for entrada, trozo in zip(entradas, trozos):
                trozo.pts = None
                entrada.push(trozo)

            salida = graph.pull()
            salida.sample_rate = self.rate
            pendientes -= salida.samples
            yield salida

        if pendientes > 0:
            # Alguno de los carriles se acabó antes: la salida sigue
            # durando lo que la imagen, aunque el resto vaya mudo.
            yield from silence(pendientes / self.rate, self.rate,
                               self.layout, self.format)

    def _graph(self, n: int):
        """Grafo de mezcla: n entradas, `amix`, salida.

        `normalize=0` es lo importante. Por omisión `amix` divide entre el
        número de entradas, así que agregar una pista muda bajaría a la
        mitad el volumen de las demás — que no es lo que nadie espera al
        poner un clip en otra pista.

        Sumar sí puede pasarse de 1.0 y recortar, igual que en Premiere. Se
        deja recortar en vez de meter un limitador porque un limitador
        necesita mirar hacia adelante, y ese adelanto desfasaría el sonido
        de la imagen.

        El `aformat` del final no es adorno: `amix` elige el formato que le
        acomoda para sumar y devolvió `flt` empaquetado cuando le pedimos
        `s16`. La reproducción lee esos bytes como enteros de 16 bits, así
        que sin esta línea el play sonaba a ruido blanco a todo volumen.
        """
        graph = av.filter.Graph()
        spec = (f"sample_rate={self.rate}:sample_fmt={self.format}"
                f":channel_layout={self.layout}:time_base=1/{self.rate}")

        entradas = [graph.add("abuffer", spec) for _ in range(n)]
        mezcla = graph.add("amix", f"inputs={n}:duration=longest:normalize=0")
        formato = graph.add(
            "aformat",
            f"sample_fmts={self.format}:channel_layouts={self.layout}"
            f":sample_rates={self.rate}",
        )
        sink = graph.add("abuffersink")

        for indice, entrada in enumerate(entradas):
            entrada.link_to(mezcla, 0, indice)
        mezcla.link_to(formato)
        formato.link_to(sink)
        graph.configure()

        return graph, entradas


class _Ducker:
    """Agacha la música cuando suena la voz: el ducking de Premiere y CapCut.

    Se hace sobre los bloques parejos que ya se le mandan a `amix`, así que
    no retrasa nada ni necesita un segundo paso. Muestra por muestra:

    1. la voz se mide con un RMS de 20 ms; hay voz donde pasa de −40 dB;
    2. la voz "se sostiene" 300 ms después de callar, para que la música no
       suba entre palabra y palabra;
    3. la ganancia objetivo —`depth` dB abajo donde hay voz— se suaviza con
       un promedio de 80 ms, para que bajar y subir no sean un salto.

    El estado de los últimos milisegundos pasa de un bloque al siguiente: si
    no, cada segundo habría un escalón.
    """

    UMBRAL = 10 ** (-40 / 20)

    def __init__(self, rate: int, depth: float) -> None:
        self.rate = rate
        self.depth = 10 ** (-abs(depth) / 20)
        self.ventana = max(1, int(0.020 * rate))
        self.sostener = int(0.300 * rate)
        self.suavizar = max(1, int(0.080 * rate))
        self._desde_voz = 10 ** 9           # muestras desde la última voz
        self._cola = np.ones(self.suavizar, dtype=np.float64)

    @staticmethod
    def _matriz(frame) -> np.ndarray:
        crudo = frame.to_ndarray()
        datos = crudo.astype(np.float64)
        if not frame.format.is_planar:
            # Empaquetado viene como (1, n × canales), entrelazado.
            datos = datos.reshape(-1, len(frame.layout.channels)).T
        if np.issubdtype(crudo.dtype, np.integer):
            datos = datos / 32768.0
        return datos

    @staticmethod
    def _cuadro(original, datos: np.ndarray):
        tipo = original.to_ndarray().dtype
        if np.issubdtype(tipo, np.integer):
            datos = np.clip(np.rint(datos * 32768.0), -32768, 32767)
        if not original.format.is_planar:
            datos = datos.T.reshape(1, -1)
        nuevo = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos.astype(tipo)),
                                           format=original.format.name,
                                           layout=original.layout.name)
        nuevo.sample_rate = original.sample_rate
        return nuevo

    def _mascara(self, carril, inicio: float, n: int, ids: set) -> np.ndarray:
        mascara = np.zeros(n, dtype=bool)
        for clip in carril:
            if id(clip) not in ids:
                continue
            a = int(round((clip.start - inicio) * self.rate))
            b = int(round((clip.end - inicio) * self.rate))
            if b > 0 and a < n:
                mascara[max(0, a):min(n, b)] = True
        return mascara

    def apply(self, trozos, carriles, inicio: float, voices: set, ducked: set):
        n = trozos[0].samples
        matrices = [self._matriz(t) for t in trozos]

        voz = np.zeros(n, dtype=np.float64)
        for matriz, carril in zip(matrices, carriles):
            mascara = self._mascara(carril, inicio, n, voices)
            if mascara.any():
                voz += np.where(mascara, np.mean(matriz * matriz, axis=0), 0.0)

        acumulado = np.concatenate([[0.0], np.cumsum(voz)])
        izquierda = np.maximum(0, np.arange(n) - self.ventana + 1)
        rms = np.sqrt((acumulado[np.arange(n) + 1] - acumulado[izquierda])
                      / (np.arange(n) + 1 - izquierda))
        activa = rms > self.UMBRAL

        # Muestras desde la última voz, arrastrando lo que traía el bloque anterior.
        indices = np.arange(n)
        ultima = np.where(activa, indices, -10 ** 9)
        ultima = np.maximum.accumulate(ultima)
        desde = np.where(ultima >= 0, indices - ultima, self._desde_voz + indices + 1)
        self._desde_voz = int(desde[-1])
        objetivo = np.where(desde <= self.sostener, self.depth, 1.0)

        relleno = np.concatenate([self._cola, objetivo])
        suave = self._promedio(relleno)[-n:]
        self._cola = relleno[-self.suavizar:]

        salida = []
        for trozo, matriz, carril in zip(trozos, matrices, carriles):
            mascara = self._mascara(carril, inicio, n, ducked)
            if not mascara.any():
                salida.append(trozo)
                continue
            ganancia = np.where(mascara, suave, 1.0)
            salida.append(self._cuadro(trozo, matriz * ganancia[None, :]))
        return salida

    def _promedio(self, valores: np.ndarray) -> np.ndarray:
        acumulado = np.concatenate([[0.0], np.cumsum(valores)])
        k = self.suavizar
        salida = np.empty_like(valores)
        salida[k - 1:] = (acumulado[k:] - acumulado[:-k]) / k
        salida[:k - 1] = valores[:k - 1]
        return salida
