"""El diseño de Vortex Photo: un lienzo con capas.

Todo aquí es dato puro, sin Qt ni numpy, para que deshacer, guardar y copiar
sean triviales: un diseño entero cabe en un diccionario de JSON. Los píxeles
no viven aquí sino en el almacén (`assets.AssetStore`); las capas solo
guardan el id de su imagen.

Coordenadas: en píxeles del lienzo, con el origen arriba a la izquierda.
Cada capa ocupa una caja de `width × height` cuyo **centro** está en
`(cx, cy)` y que gira `rotation` grados (positivo = a favor del reloj)
alrededor de ese centro. Voltear se aplica antes de girar.

Las capas van de abajo hacia arriba: `layers[0]` es la del fondo.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields

# --- modos de fusión (los de Photoshop que se usan de verdad) -------------

BLENDS = (
    "Normal",
    "Multiplicar", "Oscurecer", "Subexponer color",
    "Trama", "Aclarar", "Sobreexponer color",
    "Superponer", "Luz suave", "Luz fuerte",
    "Diferencia", "Exclusión",
    "Tono", "Saturación", "Color", "Luminosidad",
)
NORMAL = "Normal"

KIND_IMAGE = "image"        # foto o pintura (una capa de pincel es una imagen transparente)
KIND_TEXT = "text"
KIND_SHAPE = "shape"
KIND_ADJUST = "adjust"      # capa de ajuste: corrige todo lo que tiene debajo

SHAPES = ("rect", "ellipse", "triangle", "star", "line", "arrow", "heart")

ALIGNS = ("left", "center", "right")

# Las 8 franjas de color del panel HSL, como en Lightroom.
HSL_BANDS = ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta")


def new_id() -> str:
    return uuid.uuid4().hex


# --- piezas ---------------------------------------------------------------

@dataclass
class Transform:
    cx: float = 0.0
    cy: float = 0.0
    width: float = 100.0
    height: float = 100.0
    rotation: float = 0.0
    flip_h: bool = False
    flip_v: bool = False


@dataclass
class Adjustments:
    """Ajustes de foto. Todos en 0 = la foto como está.

    Rangos: −100…100, salvo los que solo suben (0…100): `clarity` puede ser
    negativo (suaviza), `sharpen`, `blur`, `vignette` y `grain` no.
    `exposure` va en pasos de luz × 100 (100 = el doble), de −300 a 300.
    """
    exposure: float = 0.0
    contrast: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    whites: float = 0.0
    blacks: float = 0.0
    temperature: float = 0.0     # negativo azul, positivo ámbar
    tint: float = 0.0            # negativo verde, positivo magenta
    vibrance: float = 0.0
    saturation: float = 0.0
    clarity: float = 0.0
    sharpen: float = 0.0         # 0…100
    blur: float = 0.0            # 0…100
    vignette: float = 0.0        # 0…100
    grain: float = 0.0           # 0…100
    # Curva maestra: puntos (x, y) en 0…1, ordenados por x. Vacía = recta.
    curve: list[tuple[float, float]] = field(default_factory=list)
    # Por franja: (tono −100…100, saturación −100…100, luminosidad −100…100).
    hsl: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # Viraje por zonas (split toning): un color para las sombras y otro para las
    # luces. Tono en grados (0…360), intensidad 0…100; `split_balance` −100…100
    # mueve el punto donde una zona cede a la otra (negativo = más luces).
    split_shadow_hue: float = 0.0
    split_shadow_sat: float = 0.0
    split_light_hue: float = 0.0
    split_light_sat: float = 0.0
    split_balance: float = 0.0
    # Brillo difuso (efecto Orton): mezcla con una versión desenfocada en «Trama». 0…100.
    softness: float = 0.0

    def is_neutral(self) -> bool:
        return self == Adjustments()

    def signature(self) -> tuple:
        """Llave estable para cachés."""
        d = asdict(self)
        d["curve"] = tuple(tuple(p) for p in self.curve)
        d["hsl"] = tuple(sorted((k, tuple(v)) for k, v in self.hsl.items()))
        return tuple(sorted(d.items()))


@dataclass
class Filter:
    """Un filtro de un clic (`photo.filters.FILTERS`) con su intensidad 0…100."""
    name: str = ""
    intensity: float = 100.0

    def is_off(self) -> bool:
        return not self.name or self.intensity <= 0


@dataclass
class Shadow:
    enabled: bool = False
    color: str = "#000000"
    opacity: float = 0.5
    blur: float = 12.0           # px del lienzo
    dx: float = 0.0
    dy: float = 8.0


@dataclass
class Outline:
    enabled: bool = False
    color: str = "#ffffff"
    width: float = 4.0


@dataclass
class Glow:
    enabled: bool = False
    color: str = "#ffffff"
    opacity: float = 0.7
    radius: float = 16.0


@dataclass
class Effects:
    shadow: Shadow = field(default_factory=Shadow)
    outline: Outline = field(default_factory=Outline)
    glow: Glow = field(default_factory=Glow)

    def is_off(self) -> bool:
        return not (self.shadow.enabled or self.outline.enabled or self.glow.enabled)


# --- capas ----------------------------------------------------------------

@dataclass
class Layer:
    kind: str = KIND_IMAGE
    id: str = field(default_factory=new_id)
    name: str = ""
    transform: Transform = field(default_factory=Transform)
    opacity: float = 1.0                 # 0…1
    blend: str = NORMAL
    visible: bool = True
    locked: bool = False
    # Máscara: imagen gris (id del almacén) del tamaño de la caja de la capa en
    # su resolución propia; blanco = se ve, negro = se oculta. None = sin máscara.
    mask: str | None = None
    effects: Effects = field(default_factory=Effects)

    # --- imagen ---
    asset: str = ""                      # id en el almacén (RGBA)
    # Recorte en píxeles de la imagen original: (x, y, ancho, alto). None = entera.
    crop: tuple[float, float, float, float] | None = None
    adjustments: Adjustments = field(default_factory=Adjustments)
    filter: Filter = field(default_factory=Filter)

    # --- texto ---
    text: str = ""
    font_family: str = "Inter"
    font_size: float = 48.0              # px del lienzo
    bold: bool = False
    italic: bool = False
    underline: bool = False
    uppercase: bool = False
    color: str = "#ffffff"               # texto; en formas es el relleno
    align: str = "center"
    letter_spacing: float = 0.0          # px
    line_height: float = 1.2             # veces el tamaño

    # --- forma ---
    shape: str = "rect"
    fill: str | None = "#7c5cff"         # None = sin relleno
    stroke: str | None = None
    stroke_width: float = 0.0
    corner_radius: float = 0.0           # px; solo «rect»

    def copy(self, *, new_identity: bool = True) -> "Layer":
        nueva = layer_from_dict(layer_to_dict(self))
        if new_identity:
            nueva.id = new_id()
        return nueva


@dataclass
class Document:
    width: int = 1080
    height: int = 1080
    background: str | None = "#ffffff"   # None = transparente
    name: str = "Diseño sin título"
    layers: list[Layer] = field(default_factory=list)

    def layer(self, layer_id: str) -> Layer | None:
        return next((c for c in self.layers if c.id == layer_id), None)

    def index(self, layer_id: str) -> int:
        for i, c in enumerate(self.layers):
            if c.id == layer_id:
                return i
        return -1

    def assets(self) -> set[str]:
        """Los ids del almacén que este diseño usa."""
        usados = set()
        for c in self.layers:
            if c.asset:
                usados.add(c.asset)
            if c.mask:
                usados.add(c.mask)
        return usados

    def copy(self) -> "Document":
        return document_from_dict(document_to_dict(self))


# --- a diccionario y de vuelta ---------------------------------------------
# Lo que falte en un archivo toma el valor por omisión, y lo que sobre se
# ignora: así un .vphoto de una versión nueva abre en una vieja y al revés.

FORMAT_VERSION = 1


def _from(cls, data):
    if not isinstance(data, dict):
        return cls()
    nombres = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in nombres})


def layer_to_dict(layer: Layer) -> dict:
    d = asdict(layer)
    d["crop"] = list(layer.crop) if layer.crop is not None else None
    d["adjustments"]["curve"] = [list(p) for p in layer.adjustments.curve]
    d["adjustments"]["hsl"] = {k: list(v) for k, v in layer.adjustments.hsl.items()}
    return d


def layer_from_dict(data: dict) -> Layer:
    data = dict(data or {})
    t = _from(Transform, data.pop("transform", None))
    a = data.pop("adjustments", None) or {}
    curva = [tuple(map(float, p)) for p in a.pop("curve", []) or []]
    hsl = {k: tuple(map(float, v)) for k, v in (a.pop("hsl", {}) or {}).items()
           if k in HSL_BANDS}
    ajustes = _from(Adjustments, a)
    ajustes.curve, ajustes.hsl = curva, hsl
    filtro = _from(Filter, data.pop("filter", None))
    e = data.pop("effects", None) or {}
    efectos = Effects(_from(Shadow, e.get("shadow")), _from(Outline, e.get("outline")),
                      _from(Glow, e.get("glow")))
    crop = data.pop("crop", None)
    capa = _from(Layer, data)
    capa.transform, capa.adjustments, capa.filter, capa.effects = t, ajustes, filtro, efectos
    capa.crop = tuple(map(float, crop)) if crop else None
    if capa.blend not in BLENDS:
        capa.blend = NORMAL
    return capa


def document_to_dict(doc: Document) -> dict:
    return {
        "format": FORMAT_VERSION,
        "width": doc.width, "height": doc.height,
        "background": doc.background, "name": doc.name,
        "layers": [layer_to_dict(c) for c in doc.layers],
    }


def document_from_dict(data: dict) -> Document:
    return Document(
        width=max(1, int(data.get("width", 1080))),
        height=max(1, int(data.get("height", 1080))),
        background=data.get("background", "#ffffff"),
        name=str(data.get("name", "Diseño sin título")),
        layers=[layer_from_dict(c) for c in data.get("layers", [])],
    )
