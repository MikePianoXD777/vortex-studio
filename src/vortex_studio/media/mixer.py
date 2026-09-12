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
                 layout: str = LAYOUT, fmt: str = FORMAT) -> None:
        self.lanes = lanes(clips)
        self.rate = rate
        self.layout = layout
        self.format = fmt

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

            for entrada, fifo in zip(entradas, fifos):
                trozo = fifo.read(bloque)
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
