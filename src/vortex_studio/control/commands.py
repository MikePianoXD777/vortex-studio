"""Las órdenes que el editor acepta por el socket de control.

Cada una usa los mismos caminos que la interfaz —`_commit`, `_run`, los
comandos de `model/commands.py`, los métodos de la ventana— para que lo que
haga Claude se vea en vivo, entre al historial con su nombre y se deshaga con
Ctrl+Z igual que lo hecho a mano. Antes de cada cambio se lleva el playhead y
la selección a donde ocurre, así la persona ve dónde está editando.

Los clips se nombran por su `uid`, que sobrevive a deshacer y a guardar. Los
textos y lo demás que no tiene `uid` se nombran por su lugar: `t2.0` es el
primer elemento de la pista 2.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt

from vortex_studio.model.overlays import ANCHORS, Title


class CommandError(Exception):
    """Algo que la persona (o Claude) pidió mal: se responde con el texto tal cual."""


OPS: dict[str, callable] = {}


def op(nombre: str):
    def registrar(fn):
        OPS[nombre] = fn
        return fn
    return registrar


def run(window, nombre: str, args: dict):
    fn = OPS.get(nombre)
    if fn is None:
        raise CommandError(f"No conozco la orden «{nombre}». Las que hay: {', '.join(sorted(OPS))}.")
    if not isinstance(args, dict):
        raise CommandError("Los argumentos van en un objeto.")
    return fn(window, args)


# --- ayudantes ---------------------------------------------------------------

def _num(args: dict, clave: str, defecto=None, minimo=None, maximo=None):
    if clave not in args or args[clave] is None:
        if defecto is None:
            raise CommandError(f"Falta «{clave}».")
        return defecto
    try:
        valor = float(args[clave])
    except (TypeError, ValueError):
        raise CommandError(f"«{clave}» tiene que ser un número.") from None
    if not math.isfinite(valor):
        raise CommandError(f"«{clave}» tiene que ser un número finito.")
    if minimo is not None and valor < minimo:
        raise CommandError(f"«{clave}» no puede ser menor que {minimo:g}.")
    if maximo is not None and valor > maximo:
        raise CommandError(f"«{clave}» no puede ser mayor que {maximo:g}.")
    return valor


def _item_id(item, pista: int, indice: int) -> str:
    return getattr(item, "uid", None) or f"t{pista}.{indice}"


def _find(window, ident) -> tuple[object, object]:
    """El elemento y su pista, por `uid` o por `tP.I`."""
    if not isinstance(ident, str) or not ident:
        raise CommandError("Falta el «id» del clip (sale en «estado»).")
    pistas = window.sequence.tracks
    for pista in pistas:
        for item in pista.clips:
            if getattr(item, "uid", None) == ident:
                return item, pista
    if ident.startswith("t") and "." in ident:
        try:
            p, i = (int(x) for x in ident[1:].split("."))
            return pistas[p].clips[i], pistas[p]
        except (ValueError, IndexError):
            pass
    raise CommandError(f"No hay ningún clip con id «{ident}». Pide «estado» para ver los que hay.")


def _show(window, texto: str, item=None, t: float | None = None) -> None:
    """Lleva la vista a donde se edita y lo dice en la barra de estado."""
    if item is not None:
        window.timeline.select(item)
    if t is not None:
        t = max(0.0, t)
        window._pause()
        window._scrubbed(t)
        window.timeline.ensure_visible(t)
    window.statusBar().showMessage(f"Claude · {texto}", 6000)


def _editable(window, item) -> None:
    pista = window._track_of(item)
    if pista is not None and pista.locked:
        raise CommandError(f"La pista «{pista.name}» está bloqueada.")


def _png(image, ancho: int) -> str:
    if image is None or image.isNull():
        raise CommandError("No hay nada que mostrar.")
    if image.width() > ancho:
        image = image.scaledToWidth(ancho, Qt.SmoothTransformation)
    datos = QByteArray()
    buf = QBuffer(datos)
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return base64.b64encode(bytes(datos)).decode()


def _describe(item, pista: int, indice: int) -> dict:
    d = {"id": _item_id(item, pista, indice),
         "tipo": "texto" if isinstance(item, Title) else type(item).__name__.lower(),
         "inicio": round(item.start, 3), "fin": round(item.start + item.duration, 3),
         "duracion": round(item.duration, 3)}
    if isinstance(item, Title):
        d["texto"] = item.text
        return d
    fuente = getattr(item, "source", None)
    if fuente is not None:
        d["archivo"] = str(fuente)
        d["entrada"] = round(getattr(item, "in_point", 0.0), 3)
    for campo, clave in (("name", "nombre"), ("speed", "velocidad"), ("fade_in", "fundido_entrada"),
                         ("fade_out", "fundido_salida"), ("dissolve", "transicion")):
        valor = getattr(item, campo, None)
        if valor not in (None, "", 0.0) and not (campo == "speed" and valor == 1.0):
            d[clave] = round(valor, 3) if isinstance(valor, float) else valor
    gain = getattr(item, "gain", 1.0)
    if gain != 1.0:
        d["volumen_db"] = round(20 * math.log10(gain), 1) if gain > 0 else -120.0
    if getattr(item, "link", ""):
        d["enlazado"] = True
    return d


def _new_items(window, antes: set) -> list[str]:
    return [_item_id(c, p, i) for p, pista in enumerate(window.sequence.tracks)
            for i, c in enumerate(pista.clips) if id(c) not in antes]


def _ids_now(window) -> set:
    return {id(c) for pista in window.sequence.tracks for c in pista.clips}


# --- mirar -------------------------------------------------------------------

@op("estado")
def estado(window, args):
    seq = window.sequence
    return {
        "proyecto": str(window._path) if window._path else None,
        "sin_guardar": bool(window._dirty),
        "secuencia": {"nombre": seq.name, "ancho": seq.width, "alto": seq.height,
                      "fps": seq.fps, "duracion": round(seq.duration, 3)},
        "playhead": round(window.timeline.playhead, 3),
        "reproduciendo": bool(window._playing),
        "pistas": [{"indice": p, "nombre": pista.name, "tipo": pista.kind,
                    "bloqueada": pista.locked, "silenciada": pista.muted,
                    "clips": [_describe(c, p, i) for i, c in enumerate(pista.clips)]}
                   for p, pista in enumerate(seq.tracks)],
        "medios": sorted(str(m) for m in window.project.media),
        "deshacer": window.history.undo_label if window.history.can_undo else None,
    }


@op("ver_cuadro")
def ver_cuadro(window, args):
    """El cuadro de la secuencia en ese segundo, como lo exportaría."""
    t = _num(args, "t", window.timeline.playhead, minimo=0)
    ancho = int(_num(args, "ancho", 640, minimo=64, maximo=1920))
    _show(window, f"mirando el cuadro de {t:.2f} s", t=t)
    seq = window.sequence
    escala = min(1.0, ancho / max(1, seq.width))
    image = window._renderer().compose(t, max(2, round(seq.width * escala)),
                                       max(2, round(seq.height * escala)))
    return {"t": round(t, 3), "imagen_png": _png(image, ancho)}


@op("ver_editor")
def ver_editor(window, args):
    """La ventana entera, como la ve la persona."""
    ancho = int(_num(args, "ancho", 1280, minimo=320, maximo=2560))
    return {"imagen_png": _png(window.grab().toImage(), ancho)}


# --- traer material ----------------------------------------------------------

def _rutas(args) -> list[Path]:
    rutas = args.get("rutas")
    if isinstance(rutas, str):
        rutas = [rutas]
    if not isinstance(rutas, list) or not rutas:
        raise CommandError("Falta «rutas»: una lista de archivos.")
    salida = []
    for r in rutas:
        p = Path(str(r)).expanduser()
        if not p.is_file():
            raise CommandError(f"No existe el archivo «{r}».")
        salida.append(p)
    return salida


@op("importar")
def importar(window, args):
    rutas = _rutas(args)
    window.import_to_bin([str(p) for p in rutas])
    _show(window, f"importó {len(rutas)} archivo{'s' if len(rutas) != 1 else ''}")
    return {"medios": sorted(str(m) for m in window.project.media)}


@op("colocar")
def colocar(window, args):
    """Pone un archivo en el timeline. Sin «en», al final de lo que haya."""
    (ruta,) = _rutas({"rutas": [args.get("ruta")] if args.get("ruta") else None})
    en = args.get("en")
    en = None if en is None else _num(args, "en", minimo=0)
    pista = int(_num(args, "pista", -1))
    if en is None:
        en = window.sequence.duration
    antes = _ids_now(window)
    window.place_media(ruta, at=en, track_index=pista)
    nuevos = _new_items(window, antes)
    if not nuevos:
        raise CommandError(f"No se pudo poner «{ruta.name}» (mira la barra de estado del editor).")
    item, _ = _find(window, nuevos[0])
    _show(window, f"puso {ruta.name}", item, item.start)
    return {"nuevos": nuevos}


# --- cortar y acomodar ---------------------------------------------------------

@op("cortar")
def cortar(window, args):
    """Corta en «t». Con «id», solo ese clip (y su enlazado); sin él, todo lo que cruce."""
    t = _num(args, "t", minimo=0)
    window.timeline.select(None)
    window.timeline.extra = []
    if args.get("id"):
        item, _ = _find(window, args["id"])
        _editable(window, item)
        if not item.start < t < item.start + item.duration:
            raise CommandError("Ese segundo no cae dentro del clip.")
        window.timeline.select(item)
    antes = _ids_now(window)
    _show(window, f"corta en {t:.2f} s", t=t)
    window.cut_at_playhead()
    return {"nuevos": _new_items(window, antes)}


@op("borrar")
def borrar(window, args):
    """Borra clips. Con «cerrar_hueco», lo de después se recorre (borrado en onda)."""
    ids = args.get("ids") or ([args["id"]] if args.get("id") else None)
    if not isinstance(ids, list) or not ids:
        raise CommandError("Falta «ids»: la lista de clips a borrar.")
    items = [_find(window, i)[0] for i in ids]
    for item in items:
        _editable(window, item)
    window._select_many(items)
    _show(window, f"borra {len(items)} clip{'s' if len(items) != 1 else ''}", t=items[0].start)
    if args.get("cerrar_hueco"):
        window.ripple_delete()
    else:
        window.delete_selected()
    return {"borrados": len(items)}


def _overlaps(pista, item, inicio: float, dur: float, ignorar) -> bool:
    return any(c is not item and id(c) not in ignorar and c.start < inicio + dur - 1e-6
               and inicio < c.start + c.duration - 1e-6 for c in pista.clips)


@op("mover")
def mover(window, args):
    """Cambia un clip de lugar (y su enlazado con él). No pisa a otros clips."""
    item, pista = _find(window, args.get("id"))
    _editable(window, item)
    inicio = _num(args, "inicio", minimo=0)
    destino = pista
    if args.get("pista") is not None:
        indice = int(_num(args, "pista", minimo=0))
        try:
            destino = window.sequence.tracks[indice]
        except IndexError:
            raise CommandError(f"No hay pista {indice}.") from None
        if destino.kind != pista.kind:
            raise CommandError(f"Un clip de {pista.kind} no va en una pista de {destino.kind}.")
        if destino.locked:
            raise CommandError(f"La pista «{destino.name}» está bloqueada.")
    grupo = window.sequence.with_linked([item])
    delta = inicio - item.start
    ids_grupo = {id(c) for c in grupo}
    for c in grupo:
        p = destino if c is item else window._track_of(c)
        if c.start + delta < -1e-9:
            raise CommandError("Moverlo ahí deja parte del grupo antes del cero.")
        if _overlaps(p, c, c.start + delta, c.duration, ids_grupo):
            raise CommandError(f"Ahí ya hay otro clip en la pista «{p.name}». Bórralo o muévelo antes.")
    if destino is not pista:
        pista.clips.remove(item)
        destino.add(item)
    for c in grupo:
        c.start = max(0.0, c.start + delta)
    for p in {id(window._track_of(c)): window._track_of(c) for c in grupo}.values():
        p.clips.sort(key=lambda c: c.start)
    window._commit("Mover")
    _show(window, f"movió el clip a {inicio:.2f} s", item, inicio)
    return {"inicio": round(item.start, 3)}


@op("recortar")
def recortar(window, args):
    """Mueve las orillas de un clip dentro del timeline: «inicio» y/o «fin», en segundos."""
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    viejo_inicio, viejo_fin = item.start, item.start + item.duration
    inicio = _num(args, "inicio", viejo_inicio, minimo=0)
    fin = _num(args, "fin", viejo_fin, minimo=0)
    if fin - inicio < 1.0 / max(1.0, window.sequence.fps):
        raise CommandError("Así el clip queda más corto que un cuadro.")
    grupo = window.sequence.with_linked([item])
    for c in grupo:
        velocidad = getattr(c, "speed", 1.0) or 1.0
        entrada = getattr(c, "in_point", 0.0) + (inicio - viejo_inicio) * velocidad
        if hasattr(c, "in_point") and entrada < -1e-6:
            raise CommandError("No hay material antes de ese punto en el archivo.")
        if getattr(c, "source", None) is not None:
            total = window._source_duration(c)
            if total is not None and entrada + (fin - inicio) * velocidad > total + 1e-3:
                raise CommandError("No hay material después de ese punto en el archivo.")
        p = window._track_of(c)
        if _overlaps(p, c, c.start + (inicio - viejo_inicio), fin - inicio, {id(x) for x in grupo}):
            raise CommandError(f"Se encimaría con otro clip en «{p.name}».")
    for c in grupo:
        if hasattr(c, "in_point"):
            c.in_point = max(0.0, c.in_point + (inicio - viejo_inicio) * (getattr(c, "speed", 1.0) or 1.0))
        c.start += inicio - viejo_inicio
        c.duration = fin - inicio
        for campo in ("fade_in", "fade_out"):
            if hasattr(c, campo):
                setattr(c, campo, min(getattr(c, campo), c.duration))
    window._commit("Recortar")
    _show(window, "recortó el clip", item, inicio)
    return _describe(item, *_where(window, item))


def _where(window, item) -> tuple[int, int]:
    for p, pista in enumerate(window.sequence.tracks):
        for i, c in enumerate(pista.clips):
            if c is item:
                return p, i
    return -1, -1


@op("quitar_silencios")
def quitar_silencios(window, args):
    """Corta los silencios del clip y cierra los huecos (cortes rápidos)."""
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    umbral = _num(args, "umbral_db", -40.0, minimo=-90, maximo=-5)
    minimo = _num(args, "minimo", 0.5, minimo=0.1, maximo=10)
    _show(window, "quita silencios", item, item.start + min(0.01, item.duration / 2))
    cuantos = window.remove_silences(umbral, minimo)
    return {"silencios_quitados": cuantos, "duracion": round(window.sequence.duration, 3)}


@op("detectar_escenas")
def detectar_escenas(window, args):
    """Corta el clip en cada cambio de escena (o solo pone marcadores)."""
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    _show(window, "busca cambios de escena", item, item.start + min(0.01, item.duration / 2))
    cuantos = window.detect_scenes(split=bool(args.get("cortar", True)),
                                   sensitivity=_num(args, "sensibilidad", 50.0, minimo=0, maximo=100))
    return {"escenas": cuantos}


# --- texto -------------------------------------------------------------------

def _title(window, datos: dict, pista) -> Title:
    texto = str(datos.get("texto", "")).strip()
    if not texto:
        raise CommandError("Falta «texto».")
    inicio = _num(datos, "inicio", window.timeline.playhead, minimo=0)
    duracion = _num(datos, "duracion", 3.0, minimo=0.05, maximo=3600)
    lugar = str(datos.get("posicion", "Subtítulo"))
    if lugar not in ANCHORS:
        raise CommandError(f"«posicion» va una de: {', '.join(ANCHORS)}.")
    x, y = ANCHORS[lugar]
    titulo = Title(start=inicio, duration=duracion, text=texto, x=x, y=y)
    if datos.get("tamano") is not None:
        titulo.size = _num(datos, "tamano", minimo=0.01, maximo=0.5)
    if datos.get("color"):
        titulo.color = str(datos["color"])
    for clave, campo in (("negrita", "bold"), ("fondo", "background"), ("sombra", "shadow")):
        if datos.get(clave) is not None:
            setattr(titulo, campo, bool(datos[clave]))
    if _overlaps(pista, titulo, inicio, duracion, set()):
        raise CommandError(f"Ya hay un texto en «{pista.name}» entre {inicio:.2f} y "
                           f"{inicio + duracion:.2f} s.")
    return titulo


def _text_track(window):
    pista = window._free_track("texto")
    if pista is None:
        raise CommandError("Todas las pistas de texto están bloqueadas.")
    return pista


@op("texto")
def texto(window, args):
    """Un texto en pantalla: título, subtítulo, rótulo."""
    pista = _text_track(window)
    titulo = _title(window, args, pista)
    pista.add(titulo)
    pista.clips.sort(key=lambda c: c.start)
    window._commit("Texto")
    _show(window, f"escribió «{titulo.text[:40]}»", titulo, titulo.start)
    window._sync_panels(window.timeline.playhead)
    return {"id": _item_id(titulo, *_where(window, titulo))}


@op("subtitulos")
def subtitulos(window, args):
    """Varios textos de un jalón (p. ej. subtítulos de lo que se dice). Un solo paso de deshacer."""
    lista = args.get("lineas")
    if not isinstance(lista, list) or not lista:
        raise CommandError("Falta «lineas»: [{texto, inicio, duracion}, …].")
    pista = _text_track(window)
    nuevos = []
    for datos in lista:
        if not isinstance(datos, dict):
            raise CommandError("Cada línea va como {texto, inicio, duracion}.")
        datos = {"posicion": args.get("posicion", "Subtítulo"), **datos}
        for clave in ("tamano", "color", "fondo", "negrita", "sombra"):
            if clave in args and clave not in datos:
                datos[clave] = args[clave]
        titulo = _title(window, datos, pista)
        if any(n.start < titulo.start + titulo.duration and titulo.start < n.start + n.duration
               for n in nuevos):
            raise CommandError(f"La línea «{titulo.text[:30]}» se encima con otra.")
        nuevos.append(titulo)
    for titulo in nuevos:
        pista.add(titulo)
    pista.clips.sort(key=lambda c: c.start)
    window._commit("Subtítulos")
    _show(window, f"puso {len(nuevos)} subtítulos", nuevos[0], nuevos[0].start)
    return {"ids": [_item_id(t, *_where(window, t)) for t in nuevos]}


@op("editar_texto")
def editar_texto(window, args):
    item, _ = _find(window, args.get("id"))
    if not isinstance(item, Title):
        raise CommandError("Ese id no es un texto.")
    _editable(window, item)
    if args.get("texto") is not None:
        item.text = str(args["texto"])
    if args.get("posicion") is not None:
        if args["posicion"] not in ANCHORS:
            raise CommandError(f"«posicion» va una de: {', '.join(ANCHORS)}.")
        item.x, item.y = ANCHORS[args["posicion"]]
    if args.get("tamano") is not None:
        item.size = _num(args, "tamano", minimo=0.01, maximo=0.5)
    if args.get("color"):
        item.color = str(args["color"])
    for clave, campo in (("negrita", "bold"), ("fondo", "background"), ("sombra", "shadow")):
        if args.get(clave) is not None:
            setattr(item, campo, bool(args[clave]))
    window._commit("Editar texto")
    _show(window, "cambió un texto", item, item.start)
    window._sync_panels(window.timeline.playhead)
    return _describe(item, *_where(window, item))


# --- color, sonido, transiciones ---------------------------------------------

COLOR = {   # nombre en la orden → (campo, mínimo, máximo)
    "exposicion": ("exposure", -300, 300),
    "brillo": ("brightness", -100, 100),
    "contraste": ("contrast", 0, 200),
    "saturacion": ("saturation", 0, 200),
    "temperatura": ("temperature", -100, 100),
    "matiz": ("tint", -100, 100),
    "vineta": ("vignette", 0, 100),
}


@op("color")
def color(window, args):
    """Corrección de color de un clip. Contraste y saturación: 100 = como viene."""
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    ajuste = getattr(item, "color", None)
    if ajuste is None or isinstance(item, Title):
        raise CommandError("Ese elemento no tiene corrección de color.")
    cambios = {}
    for clave, (campo, lo, hi) in COLOR.items():
        if args.get(clave) is not None:
            cambios[campo] = int(round(_num(args, clave, minimo=lo, maximo=hi)))
    if not cambios:
        raise CommandError(f"Di qué cambiar: {', '.join(COLOR)}.")
    for campo, valor in cambios.items():
        setattr(ajuste, campo, valor)
    window._commit("Color")
    _show(window, "ajustó el color", item, item.start + item.duration / 2)
    window._sync_panels(window.timeline.playhead)
    return {k: getattr(ajuste, COLOR[k][0]) for k in COLOR}


@op("volumen")
def volumen(window, args):
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    if not hasattr(item, "gain"):
        raise CommandError("Ese elemento no tiene volumen.")
    db = _num(args, "db", minimo=-60, maximo=24)
    item.gain = 10 ** (db / 20)
    window._commit("Volumen")
    _show(window, f"puso el volumen en {db:+.1f} dB", item)
    return {"volumen_db": round(db, 1)}


@op("fundido")
def fundido(window, args):
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    window.timeline.select(item)
    entrada = args.get("entrada")
    salida = args.get("salida")
    window.set_fade(None if entrada is None else _num(args, "entrada", minimo=0),
                    None if salida is None else _num(args, "salida", minimo=0))
    _show(window, "puso un fundido", item)
    return {"fundido_entrada": item.fade_in, "fundido_salida": item.fade_out}


@op("transicion")
def transicion(window, args):
    """Transición con el clip de la izquierda: cruzada, a negro o a blanco."""
    from vortex_studio.model.project import TRANSITIONS, Clip

    item, pista = _find(window, args.get("id"))
    _editable(window, item)
    if not isinstance(item, Clip):
        raise CommandError("Las transiciones van entre clips de video o audio.")
    segundos = _num(args, "segundos", 0.5, minimo=0, maximo=10)
    tipo = args.get("tipo")
    if tipo is not None and tipo not in TRANSITIONS:
        raise CommandError(f"«tipo» va uno de: {', '.join(TRANSITIONS)}.")
    if segundos > 0 and pista.before(item) is None:
        raise CommandError("La transición necesita otro clip pegado a la izquierda de este.")
    _show(window, "puso una transición", item, item.start)
    window.set_dissolve(segundos, args.get("tipo"))
    return {"transicion": round(getattr(item, "dissolve", 0.0), 3),
            "tipo": getattr(item, "transition", "")}


@op("velocidad")
def velocidad(window, args):
    item, _ = _find(window, args.get("id"))
    _editable(window, item)
    factor = _num(args, "factor", minimo=0.05, maximo=16)
    window.timeline.select(item)
    window.set_clip_speed(factor)
    _show(window, f"puso la velocidad en {factor:g}×", item, item.start)
    return _describe(item, *_where(window, item))


@op("normalizar_volumen")
def normalizar_volumen(window, args):
    objetivo = _num(args, "lufs", -14.0, minimo=-40, maximo=-5)
    _show(window, f"normaliza el volumen a {objetivo:g} LUFS")
    window.normalize_loudness(objetivo)
    return {"lufs": objetivo}


@op("formato")
def formato(window, args):
    """Tamaño del cuadro: 1080×1920 vertical, 1920×1080, 1080×1080…"""
    ancho = int(_num(args, "ancho", minimo=16, maximo=8192))
    alto = int(_num(args, "alto", minimo=16, maximo=8192))
    window.set_format(ancho, alto)
    _show(window, f"cambió el formato a {ancho}×{alto}")
    return {"ancho": window.sequence.width, "alto": window.sequence.height}


# --- reproducir, deshacer, guardar, exportar -----------------------------------

@op("ir_a")
def ir_a(window, args):
    t = _num(args, "t", minimo=0)
    _show(window, f"va a {t:.2f} s", t=t)
    return {"playhead": round(window.timeline.playhead, 3)}


@op("reproducir")
def reproducir(window, args):
    if args.get("desde") is not None:
        _show(window, "reproduce", t=_num(args, "desde", minimo=0))
    if not window._playing:
        window._play()
    return {"reproduciendo": bool(window._playing)}


@op("pausar")
def pausar(window, args):
    window._pause()
    return {"playhead": round(window.timeline.playhead, 3)}


@op("deshacer")
def deshacer(window, args):
    if not window.history.can_undo:
        raise CommandError("No hay nada que deshacer.")
    etiqueta = window.history.undo_label
    window.undo()
    _show(window, f"deshizo «{etiqueta}»")
    return {"deshecho": etiqueta}


@op("rehacer")
def rehacer(window, args):
    if not window.history.can_redo:
        raise CommandError("No hay nada que rehacer.")
    etiqueta = window.history.redo_label
    window.redo()
    _show(window, f"rehizo «{etiqueta}»")
    return {"rehecho": etiqueta}


@op("guardar")
def guardar(window, args):
    """Guarda el proyecto. La primera vez hace falta «ruta» (un .vortex)."""
    if args.get("ruta"):
        ruta = Path(str(args["ruta"])).expanduser()
        if ruta.suffix.lower() != ".vortex":
            ruta = ruta.with_suffix(".vortex")
        if not ruta.parent.is_dir():
            raise CommandError(f"No existe la carpeta «{ruta.parent}».")
        window._path = ruta
    elif window._path is None:
        raise CommandError("El proyecto nunca se ha guardado: di en qué «ruta».")
    if not window.save():
        raise CommandError("No se pudo guardar (mira la barra de estado del editor).")
    _show(window, f"guardó {window._path.name}")
    return {"proyecto": str(window._path)}


EXPORTS: dict[int, object] = {}


@op("exportar")
def exportar(window, args):
    """Manda la secuencia a la cola de exportación (un .mp4). Sigue en segundo plano."""
    if window.sequence.duration <= 0:
        raise CommandError("La secuencia está vacía.")
    ruta = Path(str(args.get("ruta") or "")).expanduser()
    if not args.get("ruta"):
        raise CommandError("Falta «ruta» del archivo a crear.")
    if ruta.suffix == "":
        ruta = ruta.with_suffix(".mp4")
    if not ruta.parent.is_dir():
        raise CommandError(f"No existe la carpeta «{ruta.parent}».")
    calidad = str(args.get("calidad", "Normal"))
    if calidad not in ("Borrador", "Normal", "Alta"):
        raise CommandError("«calidad» va Borrador, Normal o Alta.")
    inicio = _num(args, "inicio", 0.0, minimo=0)
    fin = _num(args, "fin", window.sequence.duration, minimo=0)
    if fin <= inicio:
        raise CommandError("«fin» tiene que ir después de «inicio».")
    job = window.queue_export(ruta, inicio, fin, calidad)
    EXPORTS[job.id] = job
    _show(window, f"exporta {ruta.name}")
    return {"exportacion": job.id, "estado": job.status}


@op("estado_exportacion")
def estado_exportacion(window, args):
    job = EXPORTS.get(int(_num(args, "exportacion")))
    if job is None:
        raise CommandError("No conozco esa exportación.")
    return {"estado": job.status, "avance": round(job.done / max(1, job.total), 3),
            "error": job.error or None, "ruta": str(job.path)}


@op("abrir_proyecto")
def abrir_proyecto(window, args):
    """Abre un .vortex. Si hay cambios sin guardar, no los tira sin «descartar»."""
    from vortex_studio.model.serialize import load_project

    ruta = Path(str(args.get("ruta") or "")).expanduser()
    if not args.get("ruta") or not ruta.is_file():
        raise CommandError(f"No existe el proyecto «{args.get('ruta')}».")
    if window._dirty and not args.get("descartar"):
        raise CommandError("El proyecto abierto tiene cambios sin guardar. Guárdalo antes, "
                           "o repite con «descartar»: true si la persona lo autoriza.")
    try:
        proyecto = load_project(ruta)
    except Exception as error:
        raise CommandError(f"No se pudo abrir: {error}") from None
    window.adopt_project(proyecto, ruta)
    _show(window, f"abrió {ruta.name}")
    return estado(window, {})


@op("nuevo_proyecto")
def nuevo_proyecto(window, args):
    if window._dirty and not args.get("descartar"):
        raise CommandError("El proyecto abierto tiene cambios sin guardar. Guárdalo antes, "
                           "o repite con «descartar»: true si la persona lo autoriza.")
    window._dirty = False
    window.new_project()
    if args.get("ancho") and args.get("alto"):
        formato(window, args)
    _show(window, "empezó un proyecto nuevo")
    return estado(window, {})
