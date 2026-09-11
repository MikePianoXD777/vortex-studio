"""Corrección de color con filtros de FFmpeg.

Se hace aquí y no en Python porque son casi un millón de pixeles por cuadro:
recorrerlos en un bucle sería inservible. Un grafo de libavfilter corre en C
y sostiene reproducción en vivo.

Los filtros usados son `lutrgb` (brillo, contraste y gamma, con una tabla de
256 entradas por canal) y `hue` (saturación). El filtro `eq`, que haría todo
junto, es GPL y no viene en las ruedas de PyAV, que se compilan LGPL.
"""

from __future__ import annotations

from vortex_studio.model.color import ColorAdjust

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False


def _channel_expression(brightness: float, contrast: float, gamma: float) -> str:
    """Expresión que FFmpeg evalúa una vez por cada uno de los 256 niveles.

    El orden importa y es el de siempre en corrección de color: contraste
    girando alrededor del gris medio, luego brillo, y hasta el final gamma,
    que es lo que abre las sombras sin quemar las luces.
    """
    return (
        f"clip("
        f"pow("
        f"clip((val-128)*{contrast:.4f}+128+{brightness:.4f},0,255)/255"
        f",1/{gamma:.4f})*255"
        f",0,255)"
    )


class ColorProcessor:
    """Aplica un `ColorAdjust` a los cuadros que le pasen.

    El grafo se arma una sola vez y se reutiliza; solo se vuelve a armar si
    cambian los ajustes o el tamaño del cuadro, porque libavfilter fija la
    geometría al configurarse.
    """

    def __init__(self) -> None:
        self._graph = None
        self._signature: tuple | None = None

    def apply(self, frame, adjust: ColorAdjust):
        """Devuelve el cuadro corregido, o el mismo si no hay nada que hacer."""
        if not HAS_PYAV or adjust is None or adjust.is_neutral:
            return frame

        signature = (
            adjust.brightness, adjust.contrast, adjust.saturation, adjust.gamma,
            adjust.temperature, frame.width, frame.height, frame.format.name,
        )
        if signature != self._signature:
            self._build(frame, adjust)
            self._signature = signature

        self._graph.push(frame)
        return self._graph.pull()

    def _build(self, frame, adjust: ColorAdjust) -> None:
        expression = _channel_expression(
            adjust.brightness_offset, adjust.contrast_factor, adjust.gamma_value
        )

        graph = av.filter.Graph()
        source = graph.add(
            "buffer",
            f"video_size={frame.width}x{frame.height}:pix_fmt={frame.format.name}"
            f":time_base=1/1000:pixel_aspect=1/1",
        )

        calor = adjust.warmth
        chain = [
            graph.add("format", "rgb24"),
            graph.add("lutrgb", f"r={expression}:g={expression}:b={expression}"),
            graph.add("hue", f"s={adjust.saturation_factor:.4f}"),
        ]
        if abs(calor) > 1e-6:
            # `colorchannelmixer` y no `colorbalance`: este último pesa por
            # zonas de luminancia y deja intacto el gris medio exacto, así
            # que un plano parejo no cambiaba nada. La matriz directa sí.
            chain.append(graph.add(
                "colorchannelmixer",
                f"rr={1 + calor:.4f}:gg=1.0:bb={1 - calor:.4f}"))
        chain += [
            graph.add("format", "rgb24"),
            graph.add("buffersink"),
        ]

        previous = source
        for node in chain:
            previous.link_to(node)
            previous = node

        graph.configure()
        self._graph = graph

    def invalidate(self) -> None:
        """Tira el grafo. Se usa al cambiar de archivo fuente."""
        self._graph = None
        self._signature = None
