"""Zonas de render: qué tan pesada es cada parte y su firma."""

import pytest

from vortex_studio.model import Clip, Sequence, Title
from vortex_studio.model.render_zones import HEAVY, LIGHT, NONE, cut_points, zone_at, zones


def base():
    seq = Sequence.default()
    v1 = seq.video_tracks()[-1]
    a = v1.add(Clip("/tmp/a.mp4", 0.0, 4.0))
    b = v1.add(Clip("/tmp/b.mp4", 4.0, 4.0))
    return seq, a, b


def test_los_cortes_parten_las_zonas():
    seq, a, b = base()
    seq.text_tracks()[0].add(Title(start=1.0, duration=2.0))
    assert cut_points(seq) == [0.0, 1.0, 3.0, 4.0, 8.0]
    assert [(z.start, z.end) for z in zones(seq)] == [(0, 1), (1, 3), (3, 4), (4, 8)]


def test_niveles_limpio_ligero_y_pesado():
    seq, a, b = base()
    seq.text_tracks()[0].add(Title(start=1.0, duration=2.0))
    b.color.exposure = 50
    niveles = [z.level for z in zones(seq)]
    assert niveles == [NONE, LIGHT, NONE, HEAVY]


def test_dos_capas_encimadas_son_pesadas():
    seq, a, b = base()
    seq.video_tracks()[0].add(Clip("/tmp/c.mp4", 0.5, 1.0))
    assert zone_at(zones(seq), 1.0).level == HEAVY


def test_la_firma_cambia_con_cualquier_ajuste_y_solo_en_su_zona():
    seq, a, b = base()
    antes = [z.signature for z in zones(seq)]
    b.color.saturation = 150
    despues = [z.signature for z in zones(seq)]
    assert antes[0] == despues[0] and antes[1] != despues[1]


def test_la_firma_es_estable_y_cuenta_el_archivo(tmp_path):
    archivo = tmp_path / "x.mp4"
    archivo.write_bytes(b"123")
    seq = Sequence.default()
    seq.video_tracks()[-1].add(Clip(archivo, 0.0, 2.0))
    primera = zones(seq)[0].signature
    assert zones(seq)[0].signature == primera
    archivo.write_bytes(b"12345")
    assert zones(seq)[0].signature != primera
