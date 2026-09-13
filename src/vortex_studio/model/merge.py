"""Fusionar dos copias de un proyecto: la tuya, la de otro, y de dónde salieron.

Dos personas se llevan el mismo proyecto; una corrige color, la otra
recorta. Juntar a mano es rehacer el trabajo de una de las dos. Aquí se hace
una **fusión a tres vías**, como git: contra la versión de la que salieron
las dos copias se ve qué cambió cada quien, y se junta.

La unidad es el **elemento de la línea de tiempo**, reconocido por su `uid`
y no por su lugar: si tú moviste un clip y el otro le cambió el color, al
final el clip queda movido *y* con el color nuevo. Solo cuando los dos
cambiaron **el mismo campo del mismo elemento** a valores distintos hay
conflicto; se queda el tuyo y se reporta, para revisarlo.

Borrado contra modificado también es conflicto: si tú borraste un clip que
el otro retocó, se conserva —perder trabajo sin avisar es peor que tener
que borrarlo otra vez—.

Todo sobre los diccionarios del archivo (`project_to_dict`), así que es
Python puro y se prueba sin abrir nada.
"""

from __future__ import annotations

import copy

_MISSING = object()
SEQUENCE_FIELDS = ("name", "fps", "width", "height", "duck_depth")
TRACK_FIELDS = ("kind", "enabled", "locked", "muted", "solo", "role")


class Merger:
    def __init__(self) -> None:
        self.conflicts: list[str] = []

    # --- piezas -------------------------------------------------------------

    def value(self, base, mine, theirs, lugar: str):
        """El valor fusionado de un campo. Empate: gana el tuyo y se anota."""
        if mine == theirs:
            return mine
        if mine == base:
            return theirs
        if theirs == base:
            return mine
        self.conflicts.append(lugar)
        return mine

    def fields(self, base: dict, mine: dict, theirs: dict, lugar: str) -> dict:
        """Campo por campo; los subdiccionarios (color, máscara…) también por campo."""
        salida = {}
        for clave in list(dict.fromkeys([*mine, *theirs])):
            b = base.get(clave, _MISSING)
            m = mine.get(clave, _MISSING)
            t = theirs.get(clave, _MISSING)
            if all(isinstance(x, dict) for x in (b, m, t)):
                salida[clave] = self.fields(b, m, t, f"{lugar} → {clave}")
                continue
            elegido = self.value(b, m, t, f"{lugar} → {clave}")
            if elegido is not _MISSING:
                salida[clave] = copy.deepcopy(elegido)
        return salida

    def keyed(self, base: dict, mine: dict, theirs: dict, lugar, merge_one) -> dict:
        """Fusiona colecciones por clave: agregados, borrados y cambiados."""
        salida = {}
        for clave in list(dict.fromkeys([*mine, *theirs, *base])):
            b, m, t = base.get(clave), mine.get(clave), theirs.get(clave)
            nombre = lugar(clave, m or t or b)
            if b is None:
                elegido = m if m is not None else t          # agregado de un lado (o de los dos)
            elif m is None and t is None:
                continue                                      # borrado de los dos lados
            elif m is None:
                if t != b:
                    self.conflicts.append(f"{nombre}: lo borraste y la otra copia lo cambió; "
                                          f"se conservó")
                    elegido = t
                else:
                    continue
            elif t is None:
                if m != b:
                    self.conflicts.append(f"{nombre}: la otra copia lo borró y tú lo cambiaste; "
                                          f"se conservó")
                    elegido = m
                else:
                    continue
            else:
                elegido = merge_one(b, m, t, nombre)
            salida[clave] = copy.deepcopy(elegido)
        return salida

    # --- secuencias --------------------------------------------------------------

    @staticmethod
    def _items(secuencia: dict) -> dict:
        salida = {}
        for pista in secuencia.get("tracks", []):
            for posicion, item in enumerate(pista.get("clips", [])):
                uid = item.get("uid") or f"{pista.get('name')}#{posicion}"
                fila = dict(item)
                fila["_track"] = pista.get("name")
                salida[uid] = fila
        return salida

    def sequence(self, base: dict, mine: dict, theirs: dict, lugar: str) -> dict:
        salida = {"id": mine.get("id", theirs.get("id"))}
        for campo in SEQUENCE_FIELDS:
            elegido = self.value(base.get(campo), mine.get(campo), theirs.get(campo),
                                 f"{lugar} → {campo}")
            if elegido is not None:
                salida[campo] = elegido

        pistas = {nombre: t for nombre, t in
                  [(p["name"], p) for p in [*base.get("tracks", []), *theirs.get("tracks", []),
                                            *mine.get("tracks", [])]]}
        por_version = [{p["name"]: p for p in v.get("tracks", [])} for v in (base, mine, theirs)]
        orden = list(dict.fromkeys([p["name"] for p in mine.get("tracks", [])]
                                   + [p["name"] for p in theirs.get("tracks", [])]))
        nuevas = []
        for nombre in orden:
            b, m, t = (v.get(nombre, {}) for v in por_version)
            fila = {"name": nombre, "clips": []}
            for campo in TRACK_FIELDS:
                elegido = self.value(b.get(campo), m.get(campo), t.get(campo),
                                     f"{lugar} → pista {nombre} → {campo}")
                if elegido is None:
                    elegido = pistas[nombre].get(campo)
                if elegido is not None:
                    fila[campo] = elegido
            nuevas.append(fila)

        def nombre_item(uid, item):
            return f"{lugar} → {item.get('name') or item.get('text') or item.get('tipo')}"

        items = self.keyed(self._items(base), self._items(mine), self._items(theirs),
                           nombre_item, self.fields)
        por_nombre = {p["name"]: p for p in nuevas}
        for item in items.values():
            pista = por_nombre.get(item.pop("_track", None))
            if pista is None:
                pista = {"name": f"Fusión {len(nuevas) + 1}", "kind": "video", "clips": []}
                nuevas.append(pista)
                por_nombre[pista["name"]] = pista
            pista["clips"].append(item)
        for pista in nuevas:
            pista["clips"].sort(key=lambda c: c.get("start", 0.0))
            self._report_overlaps(pista, lugar)
        salida["tracks"] = nuevas

        salida["markers"] = self._markers(base.get("markers", []), mine.get("markers", []),
                                          theirs.get("markers", []))
        return salida

    def _report_overlaps(self, pista: dict, lugar: str) -> None:
        fin_anterior = None
        for clip in pista["clips"]:
            inicio = clip.get("start", 0.0)
            if fin_anterior is not None and inicio < fin_anterior - 1e-6:
                self.conflicts.append(f"{lugar} → pista {pista['name']}: quedaron clips "
                                      f"encimados en {inicio:.2f} s")
            fin_anterior = max(fin_anterior or 0.0, inicio + clip.get("duration", 0.0))

    @staticmethod
    def _markers(base: list, mine: list, theirs: list) -> list:
        """Marcadores por instante: se juntan los de las dos copias, sin los borrados."""
        def clave(m):
            return round(float(m.get("time", 0.0)), 3)

        b = {clave(m): m for m in base}
        m_ = {clave(m): m for m in mine}
        t = {clave(m): m for m in theirs}
        salida = {}
        for k in {*m_, *t}:
            if k in b and (k not in m_ or k not in t):
                continue                  # uno lo borró
            salida[k] = m_.get(k) or t.get(k)
        return [copy.deepcopy(salida[k]) for k in sorted(salida)]

    # --- el proyecto ------------------------------------------------------------------

    def project(self, base: dict, mine: dict, theirs: dict) -> dict:
        salida = copy.deepcopy(mine)
        salida["name"] = self.value(base.get("name"), mine.get("name"), theirs.get("name"),
                                    "nombre del proyecto")
        secuencias = self.keyed(
            {s["id"]: s for s in base.get("sequences", [])},
            {s["id"]: s for s in mine.get("sequences", [])},
            {s["id"]: s for s in theirs.get("sequences", [])},
            lambda ident, s: f"«{s.get('name', ident)}»",
            self.sequence)
        orden = list(dict.fromkeys([s["id"] for s in mine.get("sequences", [])]
                                   + [s["id"] for s in theirs.get("sequences", [])]))
        salida["sequences"] = [secuencias[i] for i in orden if i in secuencias]
        medios = {m["path"]: m for m in theirs.get("media", [])}
        medios.update({m["path"]: m for m in mine.get("media", [])})
        salida["media"] = list(medios.values())
        return salida


def merge_projects(base: dict, mine: dict, theirs: dict) -> tuple[dict, list[str]]:
    """`(proyecto fusionado, conflictos)`, todo en diccionarios del formato del archivo."""
    fusion = Merger()
    return fusion.project(base, mine, theirs), fusion.conflicts
