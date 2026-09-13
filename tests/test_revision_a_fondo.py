"""La revisión a fondo que corre dentro del ejecutable (`--self-check`)."""

import os
from pathlib import Path

import av
import pytest

from vortex_studio import app as app_module
from vortex_studio import selfcheck

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def revision(qapp, tmp_path_factory):
    """Una sola corrida completa para todo el archivo: tarda unos segundos."""
    return selfcheck.run(qapp, tmp_path_factory.mktemp("revision"))


# --- el material que se hace sola ------------------------------------------------

def test_el_video_trae_imagen_y_sonido(tmp_path):
    ruta = selfcheck.crear_video(tmp_path / "v.mp4", segundos=1.0)
    with av.open(str(ruta)) as contenedor:
        assert sorted(s.type for s in contenedor.streams) == ["audio", "video"]
        assert float(contenedor.duration / av.time_base) == pytest.approx(1.0, abs=0.1)


def test_el_video_cambia_de_rojo_a_azul(tmp_path):
    ruta = selfcheck.crear_video(tmp_path / "v.mp4", segundos=1.0)
    with av.open(str(ruta)) as contenedor:
        cuadros = [f.to_ndarray(format="rgb24") for f in contenedor.decode(video=0)]
    primero, ultimo = cuadros[0][90, 280], cuadros[-1][90, 280]
    assert primero[0] > 150 and primero[2] < 100
    assert ultimo[2] > 150 and ultimo[0] < 100


def test_el_video_tiene_silencio_en_la_segunda_mitad(tmp_path):
    import numpy as np

    ruta = selfcheck.crear_video(tmp_path / "v.mp4", segundos=2.0)
    with av.open(str(ruta)) as contenedor:
        muestras = np.concatenate([f.to_ndarray().ravel() for f in contenedor.decode(audio=0)])
    mitad = len(muestras) // 2
    assert np.abs(muestras[: mitad - 4800]).max() > 0.2
    assert np.abs(muestras[mitad + 4800:]).max() < 0.01


# --- la corrida -------------------------------------------------------------------

def test_todos_los_pasos_pasan(revision):
    fallas = [f"{r.nombre}: {r.detalle}" for r in revision if not r.ok]
    assert not fallas, "\n".join(fallas)


def test_corren_todos_los_pasos_en_orden(revision):
    assert [r.nombre for r in revision] == [nombre for nombre, _ in selfcheck.PASOS]


def test_el_reporte_dice_cuantos_pasaron(revision):
    texto = selfcheck.report(revision)
    assert texto.splitlines()[-1] == f"{len(selfcheck.PASOS)} de {len(selfcheck.PASOS)} pasos bien"
    assert texto.count("OK   ") == len(selfcheck.PASOS)


# --- cuando algo falla ------------------------------------------------------------

def _con_pasos(monkeypatch, pasos):
    monkeypatch.setattr(selfcheck, "PASOS", pasos)


def test_un_paso_que_falla_no_detiene_a_los_demas(qapp, monkeypatch, tmp_path):
    def rompe(ctx):
        raise RuntimeError("códec que no vino")

    _con_pasos(monkeypatch, [("uno", lambda ctx: "bien"), ("dos", rompe), ("tres", lambda ctx: "")])
    resultados = selfcheck.run(qapp, tmp_path)
    assert [r.ok for r in resultados] == [True, False, True]
    assert "códec que no vino" in resultados[1].detalle


def test_si_no_hay_ventana_se_detiene(qapp, monkeypatch, tmp_path):
    def sin_ventana(ctx):
        raise selfcheck.Falla("no armó")

    _con_pasos(monkeypatch, [("ventana", sin_ventana), ("después", lambda ctx: "")])
    resultados = selfcheck.run(qapp, tmp_path)
    assert len(resultados) == 1
    assert "1 sin correr" in selfcheck.report(resultados)


def test_una_falla_esperada_se_reporta_sin_traceback(qapp, monkeypatch, tmp_path):
    def falla(ctx):
        raise selfcheck.Falla("el cuadro no se ve rojo")

    _con_pasos(monkeypatch, [("monitor", falla)])
    texto = selfcheck.report(selfcheck.run(qapp, tmp_path))
    assert "FALLA monitor" in texto and "el cuadro no se ve rojo" in texto
    assert "Traceback" not in texto


def test_main_escribe_la_bitacora_y_sale_con_1(qapp, monkeypatch, tmp_path):
    bitacora = tmp_path / "revision.log"
    monkeypatch.setenv("VORTEX_SELFCHECK_LOG", str(bitacora))
    _con_pasos(monkeypatch, [("uno", lambda ctx: ""), ("dos", lambda ctx: 1 / 0)])
    assert selfcheck.main(qapp) == 1
    texto = bitacora.read_text(encoding="utf-8")
    assert "FALLA dos" in texto and "ZeroDivisionError" in texto


def test_main_sale_con_0_si_todo_pasa(qapp, monkeypatch):
    monkeypatch.delenv("VORTEX_SELFCHECK_LOG", raising=False)
    _con_pasos(monkeypatch, [("uno", lambda ctx: "")])
    assert selfcheck.main(qapp) == 0


# --- aislamiento y la bandera ------------------------------------------------------

def test_aislar_no_pisa_lo_que_ya_estaba(monkeypatch, tmp_path):
    monkeypatch.setenv("VORTEX_CACHE_DIR", "/ya/estaba")
    monkeypatch.delenv("VORTEX_DATA_DIR", raising=False)
    selfcheck.aislar(tmp_path)
    assert os.environ["VORTEX_CACHE_DIR"] == "/ya/estaba"
    assert os.environ["VORTEX_DATA_DIR"] == str(tmp_path / "datos")


def test_la_bandera_lanza_la_revision(qapp, monkeypatch):
    monkeypatch.setattr(selfcheck, "main", lambda app: 7)
    assert app_module.main(["vortex-studio", app_module.SELF_CHECK_FLAG]) == 7


def test_la_compilacion_corre_la_revision_antes_de_subir():
    texto = (RAIZ / ".github/workflows/binarios.yml").read_text(encoding="utf-8")
    linux, windows = texto.split("\n  windows:")
    for trabajo in (linux, windows):
        assert "--self-check" in trabajo
        assert trabajo.rindex("--self-check") < trabajo.index("gh release upload")
