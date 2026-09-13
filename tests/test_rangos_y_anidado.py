"""Tramos por marcadores y ciclos de secuencias anidadas (modelo)."""

import pytest

from vortex_studio.model import Clip, Project, Sequence
from vortex_studio.model.nesting import children_of, insertable, reaches, would_cycle
from vortex_studio.model.ranges import marker_ranges, numbered_names, safe_filename


def secuencia_de(duracion=12.0):
    seq = Sequence.default()
    seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, duracion))
    return seq


# --- tramos ---------------------------------------------------------------

def test_cada_marcador_empieza_un_tramo_hasta_el_siguiente():
    seq = secuencia_de()
    seq.add_marker(0.0, "Intro")
    seq.add_marker(4.0, "Nudo")
    seq.add_marker(9.0, "")
    tramos = marker_ranges(seq)
    assert [(t.name, t.start, t.end) for t in tramos] == \
           [("Intro", 0.0, 4.0), ("Nudo", 4.0, 9.0), ("Marcador 3", 9.0, 12.0)]


def test_lo_de_antes_del_primer_marcador_sale_como_inicio():
    seq = secuencia_de()
    seq.add_marker(3.0, "Parte")
    assert [(t.name, t.start, t.end) for t in marker_ranges(seq)] == \
           [("Inicio", 0.0, 3.0), ("Parte", 3.0, 12.0)]


def test_respeta_las_marcas_de_entrada_y_salida():
    seq = secuencia_de()
    for t in (1.0, 5.0, 10.0):
        seq.add_marker(t, f"m{t:g}")
    tramos = marker_ranges(seq, 2.0, 8.0)
    assert [(t.name, t.start, t.end) for t in tramos] == [("m5", 5.0, 8.0)] or \
           [(t.name, t.start, t.end) for t in tramos] == [("Inicio", 2.0, 5.0), ("m5", 5.0, 8.0)]
    assert marker_ranges(secuencia_de()) == []


def test_nombres_de_archivo_seguros_y_numerados():
    assert safe_filename('Parte 1: "¿qué?" / fin') == "Parte 1 ¿qué  fin"
    assert safe_filename("...") == "tramo"
    seq = secuencia_de()
    seq.add_marker(0.0, "A/B")
    seq.add_marker(6.0, "C")
    assert numbered_names(marker_ranges(seq)) == ["01 - AB", "02 - C"]


# --- ciclos ---------------------------------------------------------------

class _Anidada:
    def __init__(self, sequence_id):
        self.sequence_id = sequence_id
        self.start, self.duration = 0.0, 1.0

    @property
    def end(self):
        return 1.0


def proyecto_abc():
    p = Project()
    a = p.sequences[0]
    b, c = Sequence.default(), Sequence.default()
    b.name, c.name = "B", "C"
    p.sequences += [b, c]
    a.video_tracks()[-1].clips.append(_Anidada(b.id))       # A contiene a B
    b.video_tracks()[-1].clips.append(_Anidada(c.id))       # B contiene a C
    return p, a, b, c


def test_cada_secuencia_tiene_id_distinto():
    assert Sequence().id and Sequence().id != Sequence().id


def test_contiene_directa_e_indirectamente():
    p, a, b, c = proyecto_abc()
    assert children_of(a) == {b.id}
    assert reaches(p, a.id, c.id) and not reaches(p, c.id, a.id)


def test_meter_una_secuencia_en_si_misma_o_en_quien_la_contiene_es_ciclo():
    p, a, b, c = proyecto_abc()
    assert would_cycle(p, a.id, a.id)
    assert would_cycle(p, c.id, a.id)          # C dentro de... A dentro de C: A→B→C→A
    assert would_cycle(p, b.id, a.id)
    assert not would_cycle(p, a.id, c.id)      # A ya llega a C por B, pero no es ciclo


def test_el_menu_solo_ofrece_las_que_no_hacen_ciclo():
    p, a, b, c = proyecto_abc()
    assert {s.name for s in insertable(p, c.id)} == set()
    assert {s.id for s in insertable(p, a.id)} == {b.id, c.id}
