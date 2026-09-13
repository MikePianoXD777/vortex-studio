"""Versiones guardadas, candado de quién tiene abierto el proyecto, y fusión a tres vías."""

import copy
import json
import os
import time

import pytest

from vortex_studio.model import Clip, Project, Title
from vortex_studio.model import versions as ver
from vortex_studio.model.merge import merge_projects
from vortex_studio.model.serialize import load_project, project_from_dict, project_to_dict, save_project


def _proyecto():
    proyecto = Project(name="Plática")
    secuencia = proyecto.active
    secuencia.track_named("V1").add(Clip("a.mp4", 0.0, 4.0, name="Toma A"))
    secuencia.track_named("V1").add(Clip("b.mp4", 4.0, 3.0, name="Toma B"))
    secuencia.track_named("T1").add(Title(start=1.0, duration=2.0, text="Hola"))
    return proyecto


def _datos(proyecto):
    return project_to_dict(proyecto)


def _v1(datos):
    secuencia = datos["sequences"][0]
    return next(t for t in secuencia["tracks"] if t["name"] == "V1")["clips"]


# --- identidad de los elementos -------------------------------------------------------------

def test_cada_elemento_tiene_uid_y_se_guarda():
    proyecto = _proyecto()
    uids = [c["uid"] for t in _datos(proyecto)["sequences"][0]["tracks"] for c in t["clips"]]
    assert len(uids) == 3 and len(set(uids)) == 3
    otro = project_from_dict(_datos(proyecto))
    assert [c.uid for c in otro.active.track_named("V1").clips] == \
        [c.uid for c in proyecto.active.track_named("V1").clips]


def test_dividir_le_da_uid_nuevo_a_la_segunda_mitad():
    from vortex_studio.model.commands import Split

    proyecto = _proyecto()
    toma = proyecto.active.track_named("V1").clips[0]
    comando = Split(items=[toma], time=2.0)
    comando.apply(proyecto.active)
    _datos(proyecto)
    assert comando.created[0].uid != toma.uid


def test_pegar_le_da_uid_nuevo_a_lo_pegado():
    from vortex_studio.model.commands import Paste, copy_items

    proyecto = _proyecto()
    secuencia = proyecto.active
    toma = secuencia.track_named("V1").clips[0]
    comando = Paste(entries=copy_items(secuencia, [toma]), time=10.0)
    comando.apply(secuencia)
    assert comando.created[0].uid != toma.uid


# --- fusión -----------------------------------------------------------------------------------------

def test_cambios_en_campos_distintos_se_juntan():
    base = _datos(_proyecto())
    mio, suyo = copy.deepcopy(base), copy.deepcopy(base)
    _v1(mio)[0]["in_point"] = 0.5
    _v1(suyo)[0]["color"]["exposure"] = 80
    fusion, conflictos = merge_projects(base, mio, suyo)
    toma = _v1(fusion)[0]
    assert toma["in_point"] == 0.5 and toma["color"]["exposure"] == 80
    assert conflictos == []


def test_lo_agregado_en_las_dos_copias_queda():
    base = _datos(_proyecto())
    mio = _datos(project_from_dict(base))
    suyo = _datos(project_from_dict(base))
    proyecto_mio, proyecto_suyo = project_from_dict(mio), project_from_dict(suyo)
    proyecto_mio.active.track_named("V2").add(Clip("c.mp4", 1.0, 1.0, name="Mía"))
    proyecto_suyo.active.track_named("A1").add(Clip("d.wav", 0.0, 5.0, name="Suya"))
    fusion, conflictos = merge_projects(base, _datos(proyecto_mio), _datos(proyecto_suyo))
    nombres = {c.get("name") for t in fusion["sequences"][0]["tracks"] for c in t["clips"]}
    assert {"Mía", "Suya", "Toma A", "Toma B"} <= nombres and conflictos == []


def test_borrado_de_un_lado_sin_cambios_del_otro_se_borra():
    base = _datos(_proyecto())
    mio, suyo = copy.deepcopy(base), copy.deepcopy(base)
    del _v1(mio)[1]
    fusion, conflictos = merge_projects(base, mio, suyo)
    assert [c["name"] for c in _v1(fusion)] == ["Toma A"] and conflictos == []


def test_el_mismo_campo_cambiado_distinto_es_conflicto_y_gana_el_tuyo():
    base = _datos(_proyecto())
    mio, suyo = copy.deepcopy(base), copy.deepcopy(base)
    _v1(mio)[0]["duration"] = 3.0
    _v1(suyo)[0]["duration"] = 2.0
    fusion, conflictos = merge_projects(base, mio, suyo)
    assert _v1(fusion)[0]["duration"] == 3.0
    assert len(conflictos) == 1 and "duration" in conflictos[0]


def test_borrado_contra_cambiado_conserva_el_elemento_y_avisa():
    base = _datos(_proyecto())
    mio, suyo = copy.deepcopy(base), copy.deepcopy(base)
    del _v1(mio)[1]
    _v1(suyo)[1]["speed"] = 2.0
    fusion, conflictos = merge_projects(base, mio, suyo)
    assert [c["speed"] for c in _v1(fusion)] == [1.0, 2.0]
    assert "borraste" in conflictos[0]


def test_cambio_de_pista_de_un_lado_y_color_del_otro():
    base = _datos(_proyecto())
    mio = copy.deepcopy(base)
    suyo = copy.deepcopy(base)
    pistas = mio["sequences"][0]["tracks"]
    toma = _v1(mio).pop(0)
    next(t for t in pistas if t["name"] == "V2")["clips"].append(toma)
    _v1(suyo)[0]["color"]["saturation"] = 150
    fusion, conflictos = merge_projects(base, mio, suyo)
    v2 = next(t for t in fusion["sequences"][0]["tracks"] if t["name"] == "V2")["clips"]
    assert v2[0]["name"] == "Toma A" and v2[0]["color"]["saturation"] == 150
    assert conflictos == []


def test_lo_fusionado_abre_como_proyecto():
    base = _datos(_proyecto())
    mio, suyo = copy.deepcopy(base), copy.deepcopy(base)
    _v1(mio)[0]["start"] = 0.25
    suyo["sequences"][0]["markers"].append({"time": 2.0, "name": "Suyo", "color": "#fff",
                                            "note": ""})
    fusion, _ = merge_projects(base, mio, suyo)
    proyecto = project_from_dict(fusion)
    assert proyecto.active.track_named("V1").clips[0].start == 0.25
    assert [m.name for m in proyecto.active.markers] == ["Suyo"]


def test_clips_encimados_por_la_fusion_se_reportan():
    base = _datos(_proyecto())
    mio, suyo = copy.deepcopy(base), copy.deepcopy(base)
    _v1(mio)[0]["duration"] = 5.0             # A se estira sobre B…
    _v1(suyo)[1]["start"] = 4.0               # …y B no se movió
    fusion, conflictos = merge_projects(base, mio, suyo)
    assert any("encimados" in c for c in conflictos)


# --- versiones -----------------------------------------------------------------------------------

def test_guardar_version_deja_copia_con_nombre(tmp_path):
    proyecto = _proyecto()
    ruta = save_project(proyecto, tmp_path / "platica")
    version = ver.save_version(proyecto, ruta, "Antes del color")
    assert version.path.parent == tmp_path / "platica.versiones"
    assert proyecto.version_base == version.id
    [listada] = ver.list_versions(ruta)
    assert listada.label == "Antes del color" and listada.id == version.id


def test_las_versiones_salen_de_la_mas_nueva_a_la_mas_vieja_y_se_abren(tmp_path):
    proyecto = _proyecto()
    ruta = save_project(proyecto, tmp_path / "platica")
    primera = ver.save_version(proyecto, ruta, "uno")
    proyecto.active.track_named("V1").clips[0].start = 9.0
    time.sleep(0.01)
    segunda = ver.save_version(proyecto, ruta, "dos")
    assert [v.label for v in ver.list_versions(ruta)] == ["dos", "uno"]
    vieja = ver.load_version(primera, ruta)
    assert vieja.active.track_named("V1").clips[0].start == 0.0
    assert ver.find_version(ruta, segunda.id).label == "dos"


def test_una_version_danada_no_sale_en_la_lista(tmp_path):
    proyecto = _proyecto()
    ruta = save_project(proyecto, tmp_path / "platica")
    ver.save_version(proyecto, ruta, "buena")
    (ver.versions_dir(ruta) / "rota.vortex").write_text("{", encoding="utf-8")
    assert [v.label for v in ver.list_versions(ruta)] == ["buena"]
    assert ver.find_version(ruta, "") is None
    assert ver.list_versions(tmp_path / "otro.vortex") == []


def test_la_base_de_version_se_guarda_en_el_proyecto(tmp_path):
    proyecto = _proyecto()
    ruta = save_project(proyecto, tmp_path / "platica")
    version = ver.save_version(proyecto, ruta)
    save_project(proyecto, ruta)
    assert load_project(ruta).version_base == version.id


# --- candado ----------------------------------------------------------------------------------------

def test_el_candado_de_otra_sesion_viva_avisa(tmp_path):
    ruta = tmp_path / "p.vortex"
    assert ver.acquire(ruta, "sesion-1") is None
    otro = ver.acquire(ruta, "sesion-2")
    assert otro is not None and otro.session == "sesion-1"
    assert ver.user_name() in otro.description


def test_la_misma_sesion_recupera_y_suelta_su_candado(tmp_path):
    ruta = tmp_path / "p.vortex"
    assert ver.acquire(ruta, "s") is None and ver.acquire(ruta, "s") is None
    assert not ver.release(ruta, "otra")
    assert ver.release(ruta, "s")
    assert ver.read_lock(ruta) is None and not ver.release(None, "s")


def test_un_candado_abandonado_no_estorba(tmp_path):
    ruta = tmp_path / "p.vortex"
    datos = {"usuario": "ana", "equipo": ver.host_name(), "pid": 2 ** 22 + 12345,
             "sesion": "vieja", "desde": time.time()}
    ver.lock_path(ruta).write_text(json.dumps(datos), encoding="utf-8")
    assert ver.acquire(ruta, "nueva") is None           # su proceso ya no existe
    datos.update(equipo="otro-equipo", sesion="vieja2", desde=time.time() - 2 * 24 * 3600)
    ver.lock_path(ruta).write_text(json.dumps(datos), encoding="utf-8")
    assert ver.acquire(ruta, "nueva") is None           # de hace dos días
    ver.lock_path(ruta).write_text("basura", encoding="utf-8")
    assert ver.acquire(ruta, "otra") is None
