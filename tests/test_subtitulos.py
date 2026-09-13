"""Importar y exportar subtítulos SRT y VTT."""

import pytest

from vortex_studio.model.subtitles import (
    Cue,
    format_time,
    parse,
    parse_time,
    read_file,
    to_srt,
    to_vtt,
    write_file,
)

SRT = """﻿1\r
00:00:01,000 --> 00:00:02,500\r
Hola <i>mundo</i>\r
\r
2\r
00:00:03,200 --> 00:00:05,000\r
{\\an8}Segunda línea\r
y otra\r
"""

VTT = """WEBVTT
Kind: captions

NOTE esto no es un subtítulo

intro
00:01.000 --> 00:02.500 align:start line:90%
Hola mundo

00:00:03.200 --> 00:00:05.000
Segunda
"""


def test_tiempos_de_los_dos_formatos():
    assert parse_time("00:00:01,250") == pytest.approx(1.25)
    assert parse_time("01:02.5") == pytest.approx(62.5)
    assert parse_time("1:00:00.001") == pytest.approx(3600.001)
    assert format_time(62.5) == "00:01:02,500" and format_time(62.5, ".") == "00:01:02.500"


def test_leer_srt_de_windows_con_etiquetas():
    cues = parse(SRT)
    assert [(c.start, c.end) for c in cues] == [(1.0, 2.5), (3.2, 5.0)]
    assert cues[0].text == "Hola mundo"
    assert cues[1].text == "Segunda línea\ny otra"


def test_leer_vtt_con_ajustes_notas_e_identificadores():
    cues = parse(VTT)
    assert len(cues) == 2
    assert cues[0].start == 1.0 and cues[0].text == "Hola mundo"


def test_ida_y_vuelta_en_los_dos_formatos(tmp_path):
    originales = [Cue(0.5, 1.75, "uno"), Cue(2.0, 4.0, "dos\nlíneas")]
    for nombre in ("s.srt", "s.vtt"):
        leidos = read_file(write_file(tmp_path / nombre, originales))
        assert [(c.start, c.end, c.text) for c in leidos] == \
               [(c.start, c.end, c.text) for c in originales]
    assert to_vtt(originales).startswith("WEBVTT")
    assert to_srt(originales).startswith("1\n00:00:00,500")


def test_bloques_rotos_se_saltan():
    assert parse("1\nsin tiempo\nhola\n\n2\n00:00:02,000 --> 00:00:01,000\nal revés\n") == []


def test_importar_pone_textos_en_la_pista(ventana, tmp_path):
    ruta = tmp_path / "subs.srt"
    ruta.write_text(SRT, encoding="utf-8")
    assert ventana.import_subtitles(ruta) == 2
    textos = ventana.sequence.text_tracks()[0].clips
    assert [(t.start, t.duration, t.text) for t in textos] == \
           [(1.0, 1.5, "Hola mundo"), (3.2, pytest.approx(1.8), "Segunda línea\ny otra")]
    assert textos[0].y == pytest.approx(0.88)
    assert ventana.history.undo_label == "Importar subtítulos"


def test_importar_encima_de_textos_usa_otra_pista_libre(ventana, tmp_path):
    ventana.add_title()
    ventana.timeline.selected.start = 1.0
    ruta = tmp_path / "subs.vtt"
    ruta.write_text(VTT, encoding="utf-8")
    ventana.import_subtitles(ruta)
    pistas = {p.name: p for p in ventana.sequence.text_tracks()}
    assert set(pistas) == {"T1", "T2"}                  # la nueva va arriba
    assert len(pistas["T1"].clips) == 1 and len(pistas["T2"].clips) == 2


def test_exportar_los_textos(ventana, tmp_path):
    ventana._seek(0.0)
    ventana.add_title()
    ventana.timeline.selected.text = "Primero"
    ventana.add_title()
    ventana.timeline.selected.text = "Segundo"
    ventana.timeline.selected.start = 4.0     # el playhead no pasa del final
    ruta = ventana.export_subtitles(tmp_path / "salida.vtt")
    cues = read_file(ruta)
    assert [(c.start, c.text) for c in cues] == [(0.0, "Primero"), (4.0, "Segundo")]


def test_exportar_sin_textos_avisa(ventana, tmp_path):
    assert ventana.export_subtitles(tmp_path / "vacio.srt") is None
    assert "texto" in ventana.statusBar().currentMessage()
