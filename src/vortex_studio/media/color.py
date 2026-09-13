"""Corrección de color con filtros de FFmpeg.

Se hace aquí y no en Python porque son casi un millón de pixeles por cuadro:
recorrerlos en un bucle sería inservible. Un grafo de libavfilter corre en C
y sostiene reproducción en vivo.

Los filtros usados son `lutrgb` (brillo, contraste y gamma, con una tabla de
256 entradas por canal), `hue` (saturación), `colorchannelmixer`
(temperatura), `curves` (la curva de cinco puntos) y `vignette`. El filtro
`eq`, que haría brillo, contraste, gamma y saturación de un jalón, es GPL y
no viene en las ruedas de PyAV, que se compilan LGPL.
"""

from __future__ import annotations

from pathlib import Path

from vortex_studio.model.color import ColorAdjust

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False


def _channel_expression(brightness: float, contrast: float, gamma: float,
                        exposure: float = 1.0, lift: float = 0.0,
                        channel_gamma: float = 1.0, gain: float = 1.0) -> str:
    """Expresión que FFmpeg evalúa una vez por cada uno de los 256 niveles.

    El orden importa y es el de siempre en corrección de color: exposición
    primero, como si fuera la cámara; contraste girando alrededor del gris
    medio, luego brillo y gamma; y al final lift, gamma y gain del canal,
    que son las ruedas de DaVinci:

        salida = (gain · (x + lift · (1 − x))) ^ (1 / gamma)

    El lift levanta las sombras sin tocar el blanco, el gain escala las
    luces sin tocar el negro, y la gamma dobla los medios.

    Todo va en una sola tabla de 256 entradas por canal, así que agregar las
    ruedas no le cuesta nada más a cada cuadro.
    """
    base = (f"pow(clip((clip(val*{exposure:.5f},0,255)-128)*{contrast:.4f}"
            f"+128+{brightness:.4f},0,255)/255,1/{gamma:.4f})")
    if abs(lift) < 1e-9 and abs(channel_gamma - 1.0) < 1e-9 and abs(gain - 1.0) < 1e-9:
        return f"clip({base}*255,0,255)"
    return (f"clip(pow(clip({gain:.4f}*({base}+{lift:.4f}*(1-{base})),0,1)"
            f",1/{channel_gamma:.4f})*255,0,255)")


class ColorProcessor:
    """Aplica un `ColorAdjust` —y la llave de croma, si hay— a los cuadros.

    El grafo se arma una sola vez y se reutiliza; solo se vuelve a armar si
    cambian los ajustes o el tamaño del cuadro, porque libavfilter fija la
    geometría al configurarse.
    """

    def __init__(self) -> None:
        self._graph = None
        self._signature: tuple | None = None

    def apply(self, frame, adjust: ColorAdjust | None, key=None):
        """Devuelve el cuadro corregido, o el mismo si no hay nada que hacer.

        Con llave de croma el cuadro sale en RGBA; sin ella, en RGB.
        """
        llave = key if key is not None and getattr(key, "is_on", False) else None
        neutro = adjust is None or adjust.is_neutral
        if not HAS_PYAV or (neutro and llave is None):
            return frame

        adjust = adjust or ColorAdjust()
        signature = (adjust.signature, llave.signature if llave else (),
                     frame.width, frame.height, frame.format.name)
        if signature != self._signature:
            self._build(frame, adjust, llave)
            self._signature = signature

        self._graph.push(frame)
        return self._graph.pull()

    def _build(self, frame, adjust: ColorAdjust, llave) -> None:
        graph = av.filter.Graph()
        source = graph.add(
            "buffer",
            f"video_size={frame.width}x{frame.height}:pix_fmt={frame.format.name}"
            f":time_base=1/1000:pixel_aspect=1/1",
        )

        def cadena(inicio, nodos):
            for nodo in nodos:
                inicio.link_to(nodo)
                inicio = nodo
            return inicio

        # La llave va primero, sobre el material tal como viene: el verde de
        # la pantalla es el de la toma, no el que queda después de corregir.
        # Luego la imagen se parte: el alfa por un lado, y el color por el
        # otro en RGB. Así ningún filtro de color —varios no saben de alfa—
        # se come la transparencia, y al final se vuelven a juntar.
        alfa = None
        if llave is not None:
            r, g, b = llave.rgb
            nodos = [
                graph.add("format", "rgba"),
                graph.add("colorkey", f"color=0x{r:02X}{g:02X}{b:02X}"
                                      f":similarity={max(0.01, llave.similarity / 100):.4f}"
                                      f":blend={max(0.0, llave.smoothness / 200):.4f}"),
            ]
            # `despill` va al revés de lo que parece: `mix=0` quita más verde
            # y `mix=1` casi nada. Medido: una piel de verde 190 queda en 140
            # con mix 0 y en 150 con mix 1. Por eso el derrame del panel se
            # invierte, y en 0 ni se monta el filtro.
            if llave.spill > 0:
                nodos.append(graph.add(
                    "despill", f"type={llave.spill_type}"
                               f":mix={1.0 - max(0.0, min(1.0, llave.spill / 100)):.4f}"
                               f":expand=0"))
            despues = cadena(source, nodos)
            partir = graph.add("split", "2")
            despues.link_to(partir)
            alfa = graph.add("alphaextract")
            partir.link_to(alfa, 1, 0)
            rgb = graph.add("format", "rgb24")
            partir.link_to(rgb, 0, 0)
            previous = rgb
        else:
            previous = source

        if not adjust.is_neutral:
            previous = self._color_chain(graph, previous, adjust)

        if alfa is not None:
            juntar = graph.add("alphamerge")
            previous.link_to(juntar, 0, 0)
            alfa.link_to(juntar, 0, 1)
            previous = cadena(juntar, [graph.add("format", "rgba")])
        else:
            previous = cadena(previous, [graph.add("format", "rgb24")])

        previous.link_to(graph.add("buffersink"))
        graph.configure()
        self._graph = graph

    def _color_chain(self, graph, previous, adjust: ColorAdjust):
        expresiones = {
            canal: _channel_expression(
                adjust.brightness_offset, adjust.contrast_factor, adjust.gamma_value,
                adjust.exposure_factor, *adjust.channel_lgg(canal))
            for canal in ("r", "g", "b")
        }

        calor = adjust.warmth
        tinte = adjust.tint / 400.0
        chain = [
            graph.add("format", "rgb24"),
            graph.add("lutrgb", f"r={expresiones['r']}:g={expresiones['g']}:b={expresiones['b']}"),
            graph.add("hue", f"s={adjust.saturation_factor:.4f}"),
        ]
        if abs(calor) > 1e-6 or abs(tinte) > 1e-6:
            # `colorchannelmixer` y no `colorbalance`: este último pesa por
            # zonas de luminancia y deja intacto el gris medio exacto, así
            # que un plano parejo no cambiaba nada. La matriz directa sí.
            # El tinte es el otro eje del balance: quitar verde es ir a
            # magenta.
            chain.append(graph.add(
                "colorchannelmixer",
                f"rr={1 + calor:.4f}:gg={1 - tinte:.4f}:bb={1 - calor:.4f}"))

        # La curva va después del resto y no antes: el usuario la ajusta
        # mirando la imagen ya corregida, así que tiene que ser lo último
        # que toque los niveles. Se le manda muestreada —ver
        # `model/curves.py`— para que la gráfica del panel y el resultado
        # sean la misma curva.
        if not adjust.curves.is_neutral:
            chain.append(graph.add(
                "curves", f"master={adjust.curves.ffmpeg_points()}"))

        for node in chain:
            previous.link_to(node)
            previous = node

        # El LUT va después de la corrección, como en DaVinci: se corrige la
        # toma y el LUT le pone el look encima. Con intensidad menor al 100 %
        # la imagen se parte en dos y `mix` las junta en esa proporción.
        if adjust.has_lut and Path(adjust.lut).exists():
            intensidad = max(0.0, min(1.0, adjust.lut_intensity / 100.0))
            lut = graph.add("lut3d", file=str(adjust.lut), interp="tetrahedral")
            if intensidad >= 0.999:
                previous.link_to(lut)
                previous = lut
            else:
                partir = graph.add("split", "2")
                mezcla = graph.add("mix", inputs="2",
                                   weights=f"{1 - intensidad:.4f} {intensidad:.4f}")
                previous.link_to(partir)
                partir.link_to(mezcla, 0, 0)
                partir.link_to(lut, 1, 0)
                lut.link_to(mezcla, 0, 1)
                previous = mezcla

        # La viñeta hasta el final, encima de todo lo demás. Si fuera antes,
        # el contraste y la curva la deformarían y el deslizador ya no
        # querría decir lo mismo en cada clip.
        if adjust.vignette > 0:
            viñeta = graph.add("vignette", f"a={adjust.vignette_angle:.4f}:mode=forward")
            previous.link_to(viñeta)
            previous = viñeta
        return previous

    def invalidate(self) -> None:
        """Tira el grafo. Se usa al cambiar de archivo fuente."""
        self._graph = None
        self._signature = None
