"""Exportar la edición a AAF, para Avid Media Composer y Pro Tools.

AAF es un formato binario de Microsoft (un archivo compuesto, como los .doc
viejos) y escribirlo a mano no tiene caso: se usa `pyaaf2`, que es
**opcional**. Sin él, el editor abre igual y exportar AAF dice qué instalar.

Se lleva la edición: una composición con una pista por pista de video y de
audio, cada clip como referencia al archivo original (no se incrusta el
material), con huecos donde no hay nada. Igual que el XML, sin color ni
efectos.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from vortex_studio.model.interchange import exportable_clips


def available() -> bool:
    try:
        import aaf2  # noqa: F401
    except ImportError:
        return False
    return True


def _frames(seconds: float, fps: float) -> int:
    return int(round(max(0.0, seconds) * fps))


def write_aaf(path: str | Path, sequence) -> Path:
    try:
        import aaf2
    except ImportError:
        raise RuntimeError("Para exportar AAF hace falta pyaaf2:  pip install pyaaf2") from None

    ruta = Path(path)
    tasa = max(1, round(sequence.fps or 30.0))
    pistas = [("picture", p) for p in reversed(sequence.video_tracks())] + \
             [("sound", p) for p in sequence.audio_tracks()]

    # Cuánto material hace falta de cada archivo, por clase: el clip maestro
    # tiene que alcanzar hasta el último cuadro que se usa.
    largos: dict[tuple[str, str], int] = {}
    for clase, pista in pistas:
        for clip in exportable_clips(pista):
            fin = clip.source_time(clip.start) + clip.duration * max(clip.speed, 0.0)
            clave = (str(Path(clip.source).resolve()), clase)
            largos[clave] = max(largos.get(clave, 0), _frames(fin, tasa) + tasa)

    with aaf2.open(str(ruta), "w") as archivo:
        composicion = archivo.create.CompositionMob(sequence.name)
        composicion.usage = "Usage_TopLevel"
        archivo.content.mobs.append(composicion)
        maestros: dict[tuple[str, str], object] = {}

        def maestro(clip, clase):
            clave = (str(Path(clip.source).resolve()), clase)
            if clave in maestros:
                return maestros[clave]
            nombre = Path(clip.source).name
            fuente = archivo.create.SourceMob()
            fuente.name = nombre
            descriptor = archivo.create.ImportDescriptor()
            localizador = archivo.create.NetworkLocator()
            localizador["URLString"].value = "file://" + quote(Path(clip.source).resolve()
                                                                .as_posix(), safe="/:")
            descriptor["Locator"].append(localizador)
            fuente.descriptor = descriptor
            archivo.content.mobs.append(fuente)
            ranura = fuente.create_empty_slot(tasa, media_kind=clase)
            ranura.segment.length = largos[clave]

            principal = archivo.create.MasterMob(nombre)
            archivo.content.mobs.append(principal)
            ranura_principal = principal.create_timeline_slot(tasa)
            ranura_principal.segment = fuente.create_source_clip(ranura.slot_id, 0, largos[clave],
                                                                 clase)
            maestros[clave] = (principal, ranura_principal.slot_id)
            return maestros[clave]

        for clase, pista in pistas:
            clips = exportable_clips(pista)
            if not clips:
                continue
            secuencia = archivo.create.Sequence(media_kind=clase)
            ranura = composicion.create_timeline_slot(tasa)
            ranura.segment = secuencia
            ranura.name = pista.name
            cursor = 0
            for clip in clips:
                inicio = _frames(clip.start, tasa)
                if inicio > cursor:
                    secuencia.components.append(archivo.create.Filler(clase, inicio - cursor))
                    cursor = inicio
                largo = max(1, _frames(clip.duration, tasa))
                principal, ranura_id = maestro(clip, clase)
                secuencia.components.append(principal.create_source_clip(
                    ranura_id, _frames(clip.source_time(clip.start), tasa), largo, clase))
                cursor += largo
    return ruta


def read_aaf(path: str | Path) -> list[dict]:
    """Las pistas de la composición: `[{nombre, clase, clips: [(inicio, largo, entrada, archivo)]}]`.

    Para las pruebas: se lee de vuelta lo que se escribió.
    """
    import aaf2

    salida = []
    with aaf2.open(str(path), "r") as archivo:
        composicion = next(iter(archivo.content.compositionmobs()))
        for ranura in composicion.slots:
            segmento = ranura.segment
            clips, cursor = [], 0
            for componente in segmento.components:
                if componente.__class__.__name__ == "SourceClip":
                    clips.append((cursor, componente.length, componente.start,
                                  componente.mob.name if componente.mob is not None else ""))
                cursor += componente.length
            salida.append({"nombre": ranura.name, "clase": segmento.media_kind, "clips": clips})
    return salida
