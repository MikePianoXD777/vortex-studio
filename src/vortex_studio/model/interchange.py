"""Exportar la edición para Premiere, Resolve y Final Cut: EDL y XML.

Lo que se lleva es la **edición**, no el render: qué pedazo de cada archivo
va en qué lugar de la línea de tiempo. El color, los textos y los efectos no
viajan —ningún formato de intercambio los describe de forma que el otro
programa los entienda igual—, así que cada formato lleva lo que sí puede.

- **EDL CMX 3600**: el más viejo y el que todo el mundo lee. Una pista de
  video y dos de audio, sin nombres de archivo más que en comentarios, y
  con códigos de tiempo. Sirve para conformar en color.
- **XML de Final Cut 7 (xmeml)**: todas las pistas, con la ruta de cada
  archivo, velocidad y opacidad. Premiere y Resolve lo importan tal cual;
  es el que conviene para seguir editando en otro lado.
- **AAF**: el de Avid y Pro Tools, en `media/aaf_export.py` porque necesita
  `pyaaf2`, que es opcional.

Python puro.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

from vortex_studio.model import timeremap
from vortex_studio.model.project import Clip, NestedClip


def _frames(seconds: float, fps: float) -> int:
    return int(round(max(0.0, seconds) * fps))


def tc(seconds: float, fps: float) -> str:
    """Código de tiempo sin drop frame, con base entera de fps."""
    base = max(1, round(fps))
    total = _frames(seconds, base)
    return (f"{total // (3600 * base):02d}:{total // (60 * base) % 60:02d}:"
            f"{total // base % 60:02d}:{total % base:02d}")


def exportable_clips(track) -> list:
    """Los clips de archivo de la pista que un formato de intercambio puede describir."""
    return [c for c in track.clips if isinstance(c, Clip) and not isinstance(c, NestedClip)
            and str(c.source) not in ("", ".")]


def _reel(clip) -> str:
    """El carrete: ocho letras o números del nombre del archivo, como piden los EDL."""
    limpio = re.sub(r"[^A-Za-z0-9]", "", Path(clip.source).stem).upper()
    return (limpio or "AX")[:8]


def to_edl(sequence, title: str = "") -> str:
    """El EDL CMX 3600: V1, A1 y A2."""
    fps = sequence.fps or 30.0
    lineas = [f"TITLE: {(title or sequence.name)[:60]}", "FCM: NON-DROP FRAME", ""]
    numero = 0
    pistas = []
    videos = sequence.video_tracks()
    if videos:
        pistas.append(("V", videos[-1]))                  # V1: la de más abajo
    for indice, pista in enumerate(sequence.audio_tracks()[:2]):
        pistas.append(("A" if indice == 0 else "A2", pista))

    for canal, pista in pistas:
        for clip in exportable_clips(pista):
            numero += 1
            velocidad = timeremap.speed_at(clip, 0.0) if timeremap.is_remapped(clip) else clip.speed
            entrada = clip.source_time(clip.start)
            salida = entrada + clip.duration * max(velocidad, 0.0)
            lineas.append(f"{numero:03d}  {_reel(clip):<8} {canal:<5} C        "
                          f"{tc(entrada, fps)} {tc(salida, fps)} "
                          f"{tc(clip.start, fps)} {tc(clip.end, fps)}")
            if abs(velocidad - 1.0) > 1e-6:
                lineas.append(f"M2   {_reel(clip):<8}       {velocidad * fps:05.1f}    "
                              f"{tc(entrada, fps)}")
            lineas.append(f"* FROM CLIP NAME: {Path(clip.source).name}")
            lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


_EVENT = re.compile(r"^(\d{3})\s+(\S+)\s+(\S+)\s+C\s+([\d:]{11})\s+([\d:]{11})\s+"
                    r"([\d:]{11})\s+([\d:]{11})\s*$")


def parse_tc(texto: str, fps: float) -> float:
    horas, minutos, segundos, cuadros = (int(p) for p in texto.split(":"))
    return horas * 3600 + minutos * 60 + segundos + cuadros / max(1, round(fps))


def parse_edl(texto: str, fps: float) -> list[dict]:
    """Los eventos de un EDL, para las pruebas y para leerlo de vuelta."""
    eventos = []
    for linea in texto.splitlines():
        coincide = _EVENT.match(linea)
        if coincide:
            numero, carrete, canal, a, b, c, d = coincide.groups()
            eventos.append({"numero": int(numero), "carrete": carrete, "canal": canal,
                            "entrada": parse_tc(a, fps), "salida": parse_tc(b, fps),
                            "inicio": parse_tc(c, fps), "fin": parse_tc(d, fps), "nombre": ""})
        elif linea.startswith("* FROM CLIP NAME:") and eventos:
            eventos[-1]["nombre"] = linea.split(":", 1)[1].strip()
    return eventos


def _rate(padre, fps: float) -> None:
    rate = ET.SubElement(padre, "rate")
    ET.SubElement(rate, "timebase").text = str(max(1, round(fps)))
    ET.SubElement(rate, "ntsc").text = "TRUE" if abs(fps - round(fps)) > 1e-3 else "FALSE"


def _pathurl(path: Path) -> str:
    return "file://" + quote(Path(path).resolve().as_posix(), safe="/:")


def to_fcpxml(sequence, media: dict | None = None) -> str:
    """El XML de Final Cut 7 (xmeml v4), con todas las pistas de video y audio."""
    fps = sequence.fps or 30.0
    raiz = ET.Element("xmeml", version="4")
    sec = ET.SubElement(raiz, "sequence", id="sequence-1")
    ET.SubElement(sec, "name").text = sequence.name
    ET.SubElement(sec, "duration").text = str(_frames(sequence.duration, fps))
    _rate(sec, fps)
    medios = ET.SubElement(sec, "media")
    video = ET.SubElement(medios, "video")
    formato = ET.SubElement(ET.SubElement(video, "format"), "samplecharacteristics")
    ET.SubElement(formato, "width").text = str(sequence.width)
    ET.SubElement(formato, "height").text = str(sequence.height)
    audio = ET.SubElement(medios, "audio")

    archivos: dict[str, str] = {}
    contador = [0]

    def clipitem(padre, clip, tipo: str):
        contador[0] += 1
        item = ET.SubElement(padre, "clipitem", id=f"clipitem-{contador[0]}")
        ET.SubElement(item, "name").text = clip.name
        ET.SubElement(item, "enabled").text = "TRUE"
        velocidad = clip.speed if clip.speed > 0 else 1.0
        entrada = clip.source_time(clip.start)
        ET.SubElement(item, "duration").text = str(_frames(clip.duration, fps))
        _rate(item, fps)
        ET.SubElement(item, "start").text = str(_frames(clip.start, fps))
        ET.SubElement(item, "end").text = str(_frames(clip.end, fps))
        ET.SubElement(item, "in").text = str(_frames(entrada, fps))
        ET.SubElement(item, "out").text = str(_frames(entrada + clip.duration * velocidad, fps))
        clave = str(Path(clip.source).resolve())
        if clave in archivos:
            ET.SubElement(item, "file", id=archivos[clave])
        else:
            archivos[clave] = f"file-{len(archivos) + 1}"
            archivo = ET.SubElement(item, "file", id=archivos[clave])
            ET.SubElement(archivo, "name").text = Path(clip.source).name
            ET.SubElement(archivo, "pathurl").text = _pathurl(clip.source)
            _rate(archivo, fps)
        if abs(velocidad - 1.0) > 1e-6:
            efecto = ET.SubElement(ET.SubElement(item, "filter"), "effect")
            ET.SubElement(efecto, "name").text = "Time Remap"
            ET.SubElement(efecto, "effectid").text = "timeremap"
            parametro = ET.SubElement(efecto, "parameter")
            ET.SubElement(parametro, "parameterid").text = "speed"
            ET.SubElement(parametro, "value").text = f"{velocidad * 100:.2f}"
        if tipo == "video" and abs(clip.transform.opacity - 1.0) > 1e-6:
            efecto = ET.SubElement(ET.SubElement(item, "filter"), "effect")
            ET.SubElement(efecto, "name").text = "Opacity"
            parametro = ET.SubElement(efecto, "parameter")
            ET.SubElement(parametro, "parameterid").text = "opacity"
            ET.SubElement(parametro, "value").text = f"{clip.transform.opacity * 100:.1f}"
        return item

    for pista in reversed(sequence.video_tracks()):          # V1 primero, como en Premiere
        nodo = ET.SubElement(video, "track")
        for clip in exportable_clips(pista):
            clipitem(nodo, clip, "video")
        ET.SubElement(nodo, "enabled").text = "TRUE" if pista.enabled else "FALSE"
    for pista in sequence.audio_tracks():
        nodo = ET.SubElement(audio, "track")
        for clip in exportable_clips(pista):
            clipitem(nodo, clip, "audio")
        ET.SubElement(nodo, "enabled").text = "FALSE" if pista.muted else "TRUE"

    ET.indent(raiz)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + \
        ET.tostring(raiz, encoding="unicode") + "\n"


def write_file(path: str | Path, sequence, media: dict | None = None) -> Path:
    """Escribe EDL o XML según la extensión."""
    ruta = Path(path)
    if ruta.suffix.lower() == ".edl":
        ruta.write_text(to_edl(sequence), encoding="utf-8")
    elif ruta.suffix.lower() == ".xml":
        ruta.write_text(to_fcpxml(sequence, media), encoding="utf-8")
    elif ruta.suffix.lower() == ".aaf":
        from vortex_studio.media.aaf_export import write_aaf
        write_aaf(ruta, sequence)
    else:
        raise ValueError(f"No sé exportar a «{ruta.suffix}»: usa .edl, .xml o .aaf")
    return ruta
