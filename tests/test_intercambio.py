"""Exportar la edición a EDL, XML de Final Cut 7 y AAF."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from vortex_studio.model import Clip, Sequence, Title
from vortex_studio.model import interchange as ix


def _secuencia():
    secuencia = Sequence.default()
    secuencia.name = "Entrevista"
    secuencia.fps = 24.0
    v1 = secuencia.track_named("V1")
    v1.add(Clip(Path("/material/toma uno.mp4"), 0.0, 2.0, in_point=10.0))
    v1.add(Clip(Path("/material/toma_dos.mov"), 3.0, 1.5, in_point=0.5, speed=2.0))
    secuencia.track_named("V2").add(Clip(Path("/material/logo.mp4"), 1.0, 1.0))
    secuencia.track_named("A1").add(Clip(Path("/material/voz.wav"), 0.0, 4.5))
    secuencia.track_named("T1").add(Title(0, 1, text="no viaja"))
    return secuencia


# --- EDL --------------------------------------------------------------------------------------

def test_edl_con_codigos_de_tiempo_de_ida_y_vuelta():
    eventos = ix.parse_edl(ix.to_edl(_secuencia()), 24.0)
    video = [e for e in eventos if e["canal"] == "V"]
    assert [(e["inicio"], e["fin"], e["entrada"], e["salida"]) for e in video] == \
        pytest.approx([(0, 2, 10, 12), (3, 4.5, 0.5, 3.5)])
    assert [e["nombre"] for e in video] == ["toma uno.mp4", "toma_dos.mov"]


def test_edl_lleva_el_audio_y_la_velocidad():
    texto = ix.to_edl(_secuencia())
    eventos = ix.parse_edl(texto, 24.0)
    assert [e["canal"] for e in eventos] == ["V", "V", "A"]
    assert "M2   TOMADOS" in texto and "048.0" in texto
    assert texto.startswith("TITLE: Entrevista\nFCM: NON-DROP FRAME")


def test_edl_de_secuencia_vacia_y_carretes_raros():
    vacia = Sequence.default()
    assert ix.parse_edl(ix.to_edl(vacia), 30) == []
    secuencia = Sequence.default()
    secuencia.track_named("V1").add(Clip(Path("/x/¿ñ?.mp4"), 0, 1))
    evento = ix.parse_edl(ix.to_edl(secuencia), 30)[0]
    assert evento["carrete"] == "AX" and ix.tc(3725.5, 30) == "01:02:05:15"


# --- XML -------------------------------------------------------------------------------------------

def _xml():
    return ET.fromstring(ix.to_fcpxml(_secuencia()).split("\n", 2)[2])


def test_xml_tiene_todas_las_pistas_en_orden_de_premiere():
    raiz = _xml()
    pistas = raiz.findall("./sequence/media/video/track")
    assert [len(p.findall("clipitem")) for p in pistas] == [2, 1]
    assert len(raiz.find("./sequence/media/audio").findall("track")) == 3
    assert raiz.find("./sequence/rate/timebase").text == "24"


def test_xml_clip_con_cuadros_rutas_y_velocidad():
    raiz = _xml()
    primero, segundo = raiz.findall("./sequence/media/video/track")[0].findall("clipitem")
    assert [primero.find(k).text for k in ("start", "end", "in", "out")] == ["0", "48", "240", "288"]
    assert primero.find("file/pathurl").text == "file:///material/toma%20uno.mp4"
    assert segundo.find("filter/effect/parameter/value").text == "200.00"


def test_xml_un_archivo_usado_dos_veces_se_declara_una():
    secuencia = Sequence.default()
    for inicio in (0, 2, 4):
        secuencia.track_named("V1").add(Clip(Path("/m/a.mp4"), inicio, 1))
    raiz = ET.fromstring(ix.to_fcpxml(secuencia).split("\n", 2)[2])
    archivos = raiz.findall(".//file")
    assert len(archivos) == 3 and sum(1 for f in archivos if f.find("pathurl") is not None) == 1
    assert len({f.get("id") for f in archivos}) == 1


def test_escribir_segun_la_extension(tmp_path):
    secuencia = _secuencia()
    assert ix.write_file(tmp_path / "e.edl", secuencia).read_text().startswith("TITLE")
    assert "<xmeml" in ix.write_file(tmp_path / "e.xml", secuencia).read_text()
    with pytest.raises(ValueError, match="edl"):
        ix.write_file(tmp_path / "e.otp", secuencia)


# --- AAF ----------------------------------------------------------------------------------------------

aaf2 = pytest.importorskip("aaf2")


def test_aaf_tiene_la_edicion_por_pista(tmp_path):
    from vortex_studio.media.aaf_export import read_aaf, write_aaf

    pistas = read_aaf(write_aaf(tmp_path / "e.aaf", _secuencia()))
    por_nombre = {p["nombre"]: p for p in pistas}
    assert set(por_nombre) == {"V1", "V2", "A1"}
    assert por_nombre["V1"]["clips"] == [(0, 48, 240, "toma uno.mp4"), (72, 36, 12, "toma_dos.mov")]


def test_aaf_pone_hueco_donde_no_hay_nada(tmp_path):
    from vortex_studio.media.aaf_export import read_aaf, write_aaf

    por_nombre = {p["nombre"]: p for p in read_aaf(write_aaf(tmp_path / "e.aaf", _secuencia()))}
    assert por_nombre["V2"]["clips"] == [(24, 24, 0, "logo.mp4")]
    assert por_nombre["A1"]["clase"].lower() == "sound"
    assert por_nombre["V1"]["clase"].lower() == "picture"


def test_aaf_sin_pyaaf2_explica_que_instalar(tmp_path, monkeypatch):
    import builtins

    from vortex_studio.media import aaf_export

    real = builtins.__import__

    def sin_aaf(nombre, *args, **kwargs):
        if nombre == "aaf2":
            raise ImportError(nombre)
        return real(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_aaf)
    assert not aaf_export.available()
    with pytest.raises(RuntimeError, match="pyaaf2"):
        aaf_export.write_aaf(tmp_path / "e.aaf", _secuencia())
