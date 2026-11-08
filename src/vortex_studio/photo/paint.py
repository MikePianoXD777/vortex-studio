"""Pincel, borrador, máscaras, tampón de clonar, varita mágica y quitar fondo.

Cada trazo se resuelve en dos pasos: (1) un mapa de **cobertura** 0…1 en el
rectángulo que toca el trazo —se sellan círculos suaves a lo largo del camino,
con una separación pequeña respecto al grosor para que no queden huecos aunque
el mouse vaya muy rápido—, y (2) se aplica esa cobertura a los píxeles. La
cobertura se junta con «máximo», no con suma: un trazo lento no se vuelve más
opaco que uno rápido, y la opacidad del pincel es el tope del trazo entero.
Todas las funciones devuelven copias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ._util import gaussian_blur, parse_color


@dataclass
class Brush:
    size: float = 30
    hardness: float = 0.8
    opacity: float = 1.0
    color: str = "#000000"
    mode: str = "paint"            # "paint" | "erase"


_MAX_SELLOS = 6000


def _camino(points, brush: Brush):
    """Sellos (x, y, radio) a lo largo del camino, con presión interpolada."""
    pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 1.0) for p in points]
    base = max(float(brush.size), 0.5) / 2.0
    radio = lambda pr: base * (0.15 + 0.85 * min(1.0, max(0.0, pr)))
    if len(pts) == 1:
        return np.array([pts[0][0]]), np.array([pts[0][1]]), np.array([radio(pts[0][2])])
    P = np.array(pts, np.float64)
    seg = np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1]))
    total = float(seg.sum())
    paso = max(0.5, base * 0.25)               # a lo más un cuarto del radio entre sellos
    if total / paso > _MAX_SELLOS:
        paso = total / _MAX_SELLOS
    if total <= 0:
        return np.array([P[0, 0]]), np.array([P[0, 1]]), np.array([radio(P[0, 2])])
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = int(total / paso) + 1
    t = np.linspace(0.0, total, n + 1)
    x = np.interp(t, s, P[:, 0])
    y = np.interp(t, s, P[:, 1])
    pr = np.interp(t, s, P[:, 2])
    return x, y, base * (0.15 + 0.85 * np.clip(pr, 0, 1))


def _perfil(d: np.ndarray, r: float, dureza: float) -> np.ndarray:
    """Cobertura de un sello a distancia d del centro (con borde antialias)."""
    dureza = min(1.0, max(0.0, dureza))
    if r <= 0:
        return np.zeros_like(d)
    t = d / r
    if dureza >= 0.995:
        return np.clip(r + 0.5 - d, 0.0, 1.0)             # borde duro de 1 px
    suave = np.clip((1.0 - t) / (1.0 - dureza), 0.0, 1.0)
    suave = suave * suave * (3.0 - 2.0 * suave)
    return np.where(t <= dureza, 1.0, suave)


def coverage(shape: tuple[int, int], points, brush: Brush):
    """(y0, y1, x0, x1, cobertura) del trazo recortado al lienzo, o None."""
    if not points:
        return None
    h, w = shape
    x, y, r = _camino(points, brush)
    m = float(r.max()) + 1.5
    x0 = max(0, int(math.floor(x.min() - m)))
    x1 = min(w, int(math.ceil(x.max() + m)) + 1)
    y0 = max(0, int(math.floor(y.min() - m)))
    y1 = min(h, int(math.ceil(y.max() + m)) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    cob = np.zeros((y1 - y0, x1 - x0), np.float32)
    for cx, cy, ra in zip(x, y, r):
        sx0 = max(x0, int(math.floor(cx - ra - 1)))
        sx1 = min(x1, int(math.ceil(cx + ra + 1)) + 1)
        sy0 = max(y0, int(math.floor(cy - ra - 1)))
        sy1 = min(y1, int(math.ceil(cy + ra + 1)) + 1)
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        xs = np.arange(sx0, sx1, dtype=np.float32) + 0.5            # centro del píxel
        ys = np.arange(sy0, sy1, dtype=np.float32) + 0.5
        d = np.hypot(xs[None, :] - cx, ys[:, None] - cy)
        v = _perfil(d, float(ra), brush.hardness)
        sub = cob[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        np.maximum(sub, v, out=sub)
    return y0, y1, x0, x1, np.clip(cob * float(min(1.0, max(0.0, brush.opacity))), 0.0, 1.0)


def stroke(pixels: np.ndarray, points: list[tuple[float, float, float]], brush: Brush) -> np.ndarray:
    """Pinta (o borra) un trazo sobre una imagen RGBA. Devuelve una copia."""
    out = pixels.copy()
    cov = coverage(pixels.shape[:2], points, brush)
    if cov is None:
        return out
    y0, y1, x0, x1, a = cov
    reg = out[y0:y1, x0:x1]
    if brush.mode == "erase":
        reg[..., 3] = np.clip(reg[..., 3].astype(np.float32) * (1.0 - a) + 0.5, 0, 255).astype(np.uint8)
        return out
    r, g, b, ca = parse_color(brush.color, (0, 0, 0, 255))
    a = a * (ca / 255.0)
    ab = reg[..., 3].astype(np.float32) * np.float32(1 / 255.0)
    ar = a + ab * (1.0 - a)
    col = np.array([r, g, b], np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(ar > 0, a / np.where(ar > 0, ar, 1.0), 0.0)[..., None]
    nuevo = reg[..., :3].astype(np.float32) * (1.0 - k) + col * k
    reg[..., :3] = np.clip(nuevo + 0.5, 0, 255).astype(np.uint8)
    reg[..., 3] = np.clip(ar * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out


def stroke_mask(mask: np.ndarray, points, brush: Brush) -> np.ndarray:
    """Pinta en una máscara (alto, ancho): «paint» revela (hacia 255) y
    «erase» oculta (hacia 0). Con opacidad y dureza como el pincel."""
    out = mask.copy()
    cov = coverage(mask.shape[:2], points, brush)
    if cov is None:
        return out
    y0, y1, x0, x1, a = cov
    reg = out[y0:y1, x0:x1].astype(np.float32)
    destino = 255.0 if brush.mode != "erase" else 0.0
    out[y0:y1, x0:x1] = np.clip(reg + (destino - reg) * a + 0.5, 0, 255).astype(np.uint8)
    return out


def clone(pixels: np.ndarray, points, brush: Brush, offset: tuple[float, float]) -> np.ndarray:
    """Tampón de clonar: pinta con los píxeles que están a `offset` del pincel
    (se toman de la imagen original, no de lo ya clonado, para que no se
    arrastre). Lo que cae fuera de la imagen no se copia."""
    out = pixels.copy()
    cov = coverage(pixels.shape[:2], points, brush)
    if cov is None:
        return out
    y0, y1, x0, x1, a = cov
    h, w = pixels.shape[:2]
    ox, oy = int(round(offset[0])), int(round(offset[1]))
    ys = np.arange(y0, y1)[:, None] + oy
    xs = np.arange(x0, x1)[None, :] + ox
    dentro = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
    src = pixels[np.clip(ys, 0, h - 1), np.clip(xs, 0, w - 1)]
    a = a * dentro
    reg = out[y0:y1, x0:x1]
    # Mezcla en premultiplicado para que los bordes translúcidos no se ensucien.
    pd = reg.astype(np.float32)
    ps = src.astype(np.float32)
    pd[..., :3] *= pd[..., 3:4] / 255.0
    ps[..., :3] *= ps[..., 3:4] / 255.0
    k = a[..., None]
    m = pd * (1.0 - k) + ps * k
    al = m[..., 3:4]
    with np.errstate(divide="ignore", invalid="ignore"):
        rgb = np.where(al > 0, m[..., :3] * 255.0 / np.where(al > 0, al, 1.0), 0.0)
    reg[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    reg[..., 3] = np.clip(al[..., 0] + 0.5, 0, 255).astype(np.uint8)
    return out


# --- selección -------------------------------------------------------------------

def _inundar(permitido: np.ndarray, semillas: np.ndarray) -> np.ndarray:
    """Zona conexa (4 vecinos) de `permitido` que contiene alguna semilla.
    Frente de onda vectorizado: cada paso expande todo el frente a la vez, así
    que el trabajo total es proporcional al área y no hay recursión."""
    h, w = permitido.shape
    ancho = w + 2
    marco = np.zeros((h + 2, ancho), bool)          # borde en falso: no se envuelve entre filas
    marco[1:-1, 1:-1] = permitido
    plano = marco.ravel()
    visto = np.zeros_like(plano)
    sem = np.zeros((h + 2, ancho), bool)
    sem[1:-1, 1:-1] = semillas & permitido
    frente = np.flatnonzero(sem.ravel())
    visto[frente] = True
    marca = np.zeros(plano.shape, np.int64)
    while frente.size:
        nb = np.concatenate((frente - 1, frente + 1, frente - ancho, frente + ancho))
        nb = nb[plano[nb] & ~visto[nb]]
        if nb.size == 0:
            break
        idx = np.arange(nb.size)
        marca[nb] = idx
        nb = nb[marca[nb] == idx]                   # quita repetidos sin ordenar
        visto[nb] = True
        frente = nb
    return visto.reshape(h + 2, ancho)[1:-1, 1:-1]


def magic_wand(pixels: np.ndarray, x: int, y: int, tolerance: float = 32,
               contiguous: bool = True) -> np.ndarray:
    """Máscara (255 = seleccionado) de los píxeles parecidos al de (x, y):
    cada canal (incluido el alfa) a no más de `tolerance` del color semilla."""
    h, w = pixels.shape[:2]
    x, y = int(x), int(y)
    if not (0 <= x < w and 0 <= y < h):
        return np.zeros((h, w), np.uint8)
    semilla = pixels[y, x].astype(np.int16)
    # Se compara canal por canal; los píxeles totalmente transparentes son
    # todos «iguales» sin importar el color que escondan.
    dif = np.abs(pixels.astype(np.int16) - semilla).max(axis=2)
    dif = np.where(pixels[..., 3] == 0, abs(int(semilla[3])), dif)
    parecido = dif <= float(tolerance)
    if not contiguous:
        return parecido.astype(np.uint8) * 255
    sem = np.zeros((h, w), bool)
    sem[y, x] = True
    return _inundar(parecido, sem).astype(np.uint8) * 255


def remove_background(pixels: np.ndarray) -> np.ndarray:
    """Máscara del sujeto (255) sin el fondo (0). Toma el color de los bordes
    de la imagen, marca como fondo lo que se le parece y está conectado a esos
    bordes (así un hueco del mismo color dentro del sujeto no se borra) y
    suaviza el contorno. Simple, pero sirve con fondos lisos o con degradados
    suaves."""
    h, w = pixels.shape[:2]
    if h < 3 or w < 3:
        return np.full((h, w), 255, np.uint8)
    rgb = pixels[..., :3].astype(np.float32)
    alfa = pixels[..., 3].astype(np.float32)
    grosor = max(1, min(h, w) // 100)
    lados = [pixels[:grosor].reshape(-1, 4), pixels[-grosor:].reshape(-1, 4),
             pixels[:, :grosor].reshape(-1, 4), pixels[:, -grosor:].reshape(-1, 4)]
    borde = np.concatenate(lados).astype(np.float32)
    if (borde[:, 3] < 8).mean() > 0.6:                  # ya es transparente por los bordes
        fondo_ref = [np.array([0, 0, 0, 0], np.float32)]
        tol = 24.0
    else:
        refs = [np.median(l.astype(np.float32), axis=0) for l in lados] + [np.median(borde, axis=0)]
        fondo_ref = refs
        dispersion = float(np.median(np.abs(borde[:, :3] - np.median(borde[:, :3], axis=0))))
        tol = float(min(60.0, max(22.0, 4.0 * dispersion + 18.0)))
    dist = np.full((h, w), np.inf, np.float32)
    for ref in fondo_ref:
        d = np.sqrt(((rgb - ref[:3]) ** 2).sum(axis=2))
        d = np.maximum(d, np.abs(alfa - ref[3]) * 0.5)
        dist = np.minimum(dist, d)
    parecido = dist <= tol
    sem = np.zeros((h, w), bool)
    sem[:grosor] = sem[-grosor:] = True
    sem[:, :grosor] = sem[:, -grosor:] = True
    fondo = _inundar(parecido, sem)
    sujeto = (~fondo).astype(np.float32)
    # Suaviza el borde: desenfoque y un contraste que lo deja con ~2 px de transición.
    if sujeto.any():
        sujeto = gaussian_blur(sujeto, 1.0)
        sujeto = np.clip((sujeto - 0.5) * 2.2 + 0.5, 0.0, 1.0)
    return np.clip(sujeto * 255.0 + 0.5, 0, 255).astype(np.uint8)
