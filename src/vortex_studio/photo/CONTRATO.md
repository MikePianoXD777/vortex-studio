# Vortex Photo: contrato entre el motor y la interfaz

Vortex Photo es el modo **Fotos** de Vortex Studio (la 2.0). El eslogan manda:
**las funciones de los grandes, pero fáciles de usar**. Tiene el poder de
Photoshop (capas, máscaras, modos de fusión, capas de ajuste, curvas, HSL,
pincel, tampón de clonar, varita mágica) con la simplicidad de Canva: lo
básico a la vista y lo avanzado detrás de «Más opciones».

- `src/vortex_studio/photo/`: modelo y motor. **Sin QtWidgets.** Puede usar
  `QtGui` (`QImage`, `QPainter`, `QFont`) para leer y escribir imágenes y
  dibujar texto. numpy para todo lo demás. Nada de Pillow, OpenCV ni SciPy.
- `src/vortex_studio/ui/photo/`: la interfaz.

`document.py` ya existe y es la base de los dos lados. Si hace falta un campo
nuevo, se agrega ahí con valor por omisión (y en `layer_from_dict` si no es
plano). Los demás módulos del motor tienen estas firmas; la interfaz solo usa
esto.

## Imágenes en memoria

Arreglos numpy `uint8` de forma `(alto, ancho, 4)`, **RGBA sin
premultiplicar**. Las máscaras: `(alto, ancho)` `uint8`, 255 = se ve.
Internamente el motor puede trabajar en `float32`, pero entra y sale `uint8`.

## `assets.py`

```python
class AssetStore:
    def put(self, pixels: np.ndarray) -> str       # id = hash del contenido; el arreglo se guarda de solo lectura
    def get(self, asset_id: str) -> np.ndarray     # KeyError si no está
    def has(self, asset_id: str) -> bool
    def size(self, asset_id: str) -> tuple[int, int]   # (ancho, alto)
    def ids(self) -> set[str]
    def collect(self, keep: set[str]) -> None      # suelta lo que no esté en keep
```

## `render.py`

```python
class Renderer:
    def __init__(self, store: AssetStore): ...
    def render(self, doc: Document, scale: float = 1.0, *,
               hide: Collection[str] = (),      # ids de capas que no se dibujan (p. ej. la que se edita)
               original: bool = False           # «antes»: sin ajustes, filtros ni capas de ajuste
               ) -> np.ndarray                  # (round(alto*scale), round(ancho*scale), 4)
    def render_layer(self, doc: Document, layer: Layer, scale: float = 1.0) -> np.ndarray
        # la capa sola con sus ajustes y efectos, en su caja sin girar (ancho*scale × alto*scale)
    def thumbnail(self, doc: Document, max_side: int) -> np.ndarray
    def invalidate(self, layer_id: str | None = None) -> None
def to_qimage(pixels: np.ndarray) -> QImage     # copia; QImage.Format_RGBA8888
def from_qimage(image: QImage) -> np.ndarray
```

Rápido: caché por capa con llave (contenido de la capa, escala); mover una capa
no vuelve a calcular sus ajustes. A escala de pantalla (lienzo de 1080² a 0.5)
un `render` con 10 capas tiene que bajar de ~30 ms con caché caliente.

## `adjust.py` y `filters.py`

```python
def apply_adjustments(pixels: np.ndarray, adj: Adjustments, scale: float = 1.0) -> np.ndarray
    # scale: para que blur/sharpen/clarity/grano se vean igual en la vista previa que exportado
FILTERS: dict[str, FilterPreset]   # id → preset; orden = el de la galería
@dataclass class FilterPreset: id: str; name: str; adjustments: Adjustments  # nombre en español
def apply_filter(pixels, flt: Filter, scale=1.0) -> np.ndarray
def auto_enhance(pixels) -> Adjustments   # «Mejorar con un clic»: ajustes sugeridos
```

## `blend.py`, `effects.py`, `text.py`, `shapes.py`

```python
def composite(dst: np.ndarray, src: np.ndarray, mode: str, opacity: float,
              x: int, y: int) -> None     # en su lugar; src puede salirse del borde
def render_text(layer: Layer, scale: float) -> np.ndarray     # tamaño = caja de la capa
def text_height(layer: Layer) -> float      # alto que necesita el texto con el ancho de su caja
def render_shape(layer: Layer, scale: float) -> np.ndarray
def apply_effects(pixels: np.ndarray, effects: Effects, scale: float) -> tuple[np.ndarray, int, int]
    # devuelve la imagen con margen para la sombra o el brillo, y cuánto creció (izq, arriba)
```

## `paint.py`: pincel, borrador, máscara, clonar, varita

```python
@dataclass class Brush: size: float = 30; hardness: float = 0.8; opacity: float = 1.0
                        color: str = "#000000"; mode: str = "paint"   # "paint" | "erase"
def stroke(pixels: np.ndarray, points: list[tuple[float, float, float]], brush: Brush) -> np.ndarray
    # points = (x, y, presión 0…1) en píxeles de `pixels`; devuelve una copia
def stroke_mask(mask: np.ndarray, points, brush: Brush) -> np.ndarray   # paint=revelar, erase=ocultar
def clone(pixels, points, brush, offset: tuple[float, float]) -> np.ndarray
def magic_wand(pixels, x: int, y: int, tolerance: float = 32, contiguous: bool = True) -> np.ndarray  # máscara
def remove_background(pixels) -> np.ndarray   # máscara: lo que toca los bordes y se parece al borde, fuera
```

## `io.py`

```python
OPEN_FILTER: str          # filtro para QFileDialog ("Imágenes (*.png *.jpg …)")
def load_image(path) -> np.ndarray          # con la orientación EXIF aplicada
def add_image(doc, store, path_or_pixels, *, fit: bool = True) -> Layer
    # la agrega arriba, centrada y cabiendo en el lienzo si fit
def save_document(doc, store, path) -> None   # .vphoto: zip con document.json y assets/<id>.png
def load_document(path) -> tuple[Document, AssetStore]
EXPORT_FORMATS = ("PNG", "JPG", "WEBP")
def export(doc, store, path, fmt="PNG", quality=92, scale=1.0) -> None
    # JPG sin transparencia: se aplana sobre el fondo (blanco si no hay)
def export_batch(paths, adjustments, flt, out_dir, fmt="JPG", quality=92,
                 progress: Callable[[int, int], None] | None = None) -> list[Path]
```

## `history.py`

```python
class PhotoHistory:   # instantáneas de document_to_dict; las imágenes no se copian (están en el almacén)
    def reset(doc); push(doc, label); undo() -> Document | None; redo() -> Document | None
    can_undo; can_redo; undo_label; redo_label; assets_in_use() -> set[str]
```

## `templates.py`

```python
SIZES: list[tuple[str, str, int, int]]   # (grupo, nombre, ancho, alto)
def text_presets() -> list[tuple[str, Layer]]   # «Agregar un título», «subtítulo», «cuerpo»
```

## Lo que el motor agrega al contrato (compatible hacia atrás)

Todo lo anterior se cumple tal cual. Además, la interfaz puede usar:

- **`Renderer.render_layer_fx(doc, layer, scale) -> (imagen, margen_izq, margen_arriba)`**:
  la capa con sombra, contorno y brillo (la imagen es más grande que la caja).
  `render_layer` devuelve la capa **sin** efectos, exactamente del tamaño de su
  caja (los efectos agrandan la imagen, y el contrato pide el tamaño de la caja).
- **`Renderer(store, max_cache_bytes=512 MB)`**, `Renderer.cache_bytes()`, y los
  contadores `builds` / `hits` (cuántas veces se rehízo o se reutilizó el
  contenido de una capa).
- `apply_adjustments` devuelve **el mismo arreglo** (sin copiar) si los ajustes
  son neutros: no hay que modificarlo en su lugar. `apply_filter` igual si el
  filtro está apagado o no existe.
- `apply_filter` acepta en `Filter.name` el **id** (`"bn"`) o el nombre
  visible (`"Blanco y negro"`). La intensidad escala los ajustes del preset
  hacia cero (exacto, no mezcla dos imágenes). `FILTERS` tiene 22 presets;
  `filters.find_preset(nombre)` los busca.
- `io.PhotoFileError` (subclase de `ValueError`): archivo ilegible o dañado, con
  el mensaje listo para mostrar. `io.PROJECT_FILTER` para el diálogo de `.vphoto`.
  `load_image` y `load_document` lanzan esa excepción; si solo falta una imagen
  dentro del `.vphoto`, el diseño abre y esa capa no se dibuja.
- `AssetStore`: `hash_of(pixels)`, `adopt(id, pixels)` (guarda bajo un id dado,
  lo usa `load_document`), `len()` y `nbytes()`. Las máscaras son arreglos 2D
  `uint8` y viven en el mismo almacén.
- `PhotoHistory(limit=100)`; un `push` con un estado idéntico al actual no agrega
  paso; `undo_label` es la etiqueta de la acción que se deshará y `redo_label` la
  de la que se rehará; `assets_in_use()` incluye los de **todos** los pasos (también
  los deshechos), para que deshacer pueda traerlos de vuelta.
- `paint.coverage(...)` (el mapa de cobertura de un trazo, útil para mostrar el
  cursor o vista previa del pincel).

### Cómo se interpreta lo que el contrato dejaba abierto

- `scale` de `apply_adjustments` es la escala del **lienzo** a la que se ve la
  imagen: los radios (desenfoque, enfoque, claridad) están en píxeles del lienzo.
- Una capa de ajuste actúa en su caja (`transform`) y con su máscara; fuera de
  ella no toca nada. Su modo de fusión se ignora (siempre es una corrección).
  «Antes» (`original=True`) no aplica capas de ajuste.
- Una capa girada con sombra: el desplazamiento de la sombra se mide en el
  lienzo (cae hacia el mismo lado aunque la capa gire).
- El texto se acomoda siempre a escala 1 y solo se dibuja escalado: el corte de
  líneas es el mismo en la vista previa, en la exportación y en `text_height`.
- `paint.stroke`: la opacidad del pincel es el tope del trazo entero (un trazo
  que se cruza no se oscurece); la presión (0…1) escala el diámetro de 15 % a 100 %.
- Las pruebas de la interfaz que importen el motor deben usar la `qapp` del
  banco (una `QApplication`) antes de llamar al motor: si no hay aplicación,
  el motor crea una `QGuiApplication`, y después no se podría crear la `QApplication`.

Sin cambios a `document.py`.

### Viraje por zonas (agregado)

`Adjustments` tiene campos nuevos con valor 0 (neutros): `split_shadow_hue`,
`split_shadow_sat`, `split_light_hue`, `split_light_sat` (tono 0…360°, intensidad
0…100) y `split_balance` (−100…100). Tiñen sombras y luces con colores distintos
sin cambiar el brillo; sin intensidad no hacen nada. Los filtros Sepia, Atardecer,
Cian y naranja, Invierno, Matte, Pastel, Cálido y Desvanecido los usan. La
intensidad de un filtro escala las intensidades, no los tonos. `layer_from_dict`
no necesitó cambios (son campos planos). La interfaz puede mostrar «Tono de
sombras / luces» en «Más opciones».

### Velocidad de los ajustes (agregado)

Enfoque sobre la luminosidad (sin halos de color); desenfoque y claridad con
sigma ≥ 4 a resolución reducida; HSL con una rejilla de 64³ colores cacheada.

### Suavidad (agregado)

`Adjustments.softness` (0…100, neutro 0): brillo difuso tipo Orton, una versión
desenfocada de contraste recortado mezclada en Trama. Lo usa el filtro Suave y
la interfaz lo muestra como «Suavidad» en Detalle.
