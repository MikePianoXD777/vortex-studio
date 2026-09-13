"""Secuencias anidadas: una secuencia usada como clip dentro de otra.

La regla dura es que no haya ciclos. Si A contiene a B y B contiene a A,
pintar un cuadro de A pide un cuadro de B que pide uno de A… para siempre, y
el editor se cuelga. Antes de meter una secuencia en otra se revisa, y el
menú ni ofrece las que harían ciclo.

Python puro: aquí solo se sabe quién contiene a quién.
"""

from __future__ import annotations


def children_of(sequence) -> set[str]:
    """Los ids de las secuencias que usa directamente."""
    return {getattr(c, "sequence_id", "") for t in sequence.tracks for c in t.clips
            if getattr(c, "sequence_id", "")}


def reaches(project, desde: str, hasta: str) -> bool:
    """¿La secuencia `desde` contiene, directa o indirectamente, a `hasta`?"""
    por_id = {s.id: s for s in project.sequences}
    pendientes, vistos = [desde], set()
    while pendientes:
        actual = pendientes.pop()
        if actual == hasta:
            return True
        if actual in vistos or actual not in por_id:
            continue
        vistos.add(actual)
        pendientes.extend(children_of(por_id[actual]))
    return False


def would_cycle(project, outer_id: str, inner_id: str) -> bool:
    """Meter `inner` dentro de `outer` haría un ciclo."""
    return outer_id == inner_id or reaches(project, inner_id, outer_id)


def insertable(project, outer_id: str) -> list:
    """Las secuencias que se pueden meter en `outer` sin hacer ciclo."""
    return [s for s in project.sequences if not would_cycle(project, outer_id, s.id)]
