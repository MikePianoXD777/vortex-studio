"""Efectos como plugins con parámetros declarativos."""

import json

import numpy as np
import pytest

from vortex_studio.model import plugins
from vortex_studio.model.color import ColorAdjust

NITIDEZ = {"id": "nitidez2", "nombre": "Nitidez", "filtro": "unsharp",
           "parametros": [{"id": "cantidad", "nombre": "Cantidad", "opcion": "la",
                           "min": 0, "max": 3, "omision": 1}],
           "fijos": {"lx": 5, "ly": 5}}


@pytest.fixture(autouse=True)
def catalogo_limpio():
    plugins._cache = None
    yield
    plugins._cache = None


# --- validar -------------------------------------------------------------------------------

def test_un_plugin_bien_escrito_se_arma():
    plugin = plugins.from_dict(NITIDEZ)
    assert plugin.filter == "unsharp" and plugin.defaults() == {"cantidad": 1.0}
    assert plugin.arguments({"cantidad": 2.5}) == "la=2.5:lx=5:ly=5"


def test_filtros_que_abren_archivos_o_raros_se_rechazan():
    for filtro in ("movie", "amovie", "drawtext", "", "unsharp;movie"):
        with pytest.raises(plugins.PluginError):
            plugins.from_dict({**NITIDEZ, "filtro": filtro})


def test_nombres_de_opcion_con_trampa_se_rechazan():
    malos = [
        {**NITIDEZ, "parametros": [{**NITIDEZ["parametros"][0], "opcion": "la=1:movie"}]},
        {**NITIDEZ, "fijos": {"lx": "5:filename=/etc/passwd"}},
        {**NITIDEZ, "fijos": {"l x": 5}},
        {**NITIDEZ, "id": "Nitidez Mayúsculas"},
        {**NITIDEZ, "parametros": [{**NITIDEZ["parametros"][0], "min": 3, "max": 1}]},
        {**NITIDEZ, "parametros": [NITIDEZ["parametros"][0], NITIDEZ["parametros"][0]]},
        "no soy objeto",
    ]
    for malo in malos:
        with pytest.raises(plugins.PluginError):
            plugins.from_dict(malo)


def test_los_valores_se_limitan_a_su_rango():
    plugin = plugins.from_dict(plugins.BUILTIN[3])          # pixelado, enteros
    assert plugin.arguments({"ancho": 1000, "alto": 3.6}) == "w=64:h=4"
    assert plugin.arguments({"ancho": "x", "alto": float("nan")}) == "w=16:h=16"
    assert plugins.from_dict(plugins.BUILTIN[7]).arguments({}) == ""     # espejo, sin nada


# --- catálogo -----------------------------------------------------------------------------------

def test_el_catalogo_trae_los_incluidos():
    catalogo, avisos = plugins.catalog()
    assert {"nitidez", "desenfoque", "grano", "espejo", "negativo"} <= set(catalogo)
    assert avisos == []


def test_un_plugin_del_usuario_aparece_y_reemplaza_al_incluido(tmp_path):
    (tmp_path / "mio.json").write_text(json.dumps(NITIDEZ), encoding="utf-8")
    propio = {**NITIDEZ, "id": "nitidez", "nombre": "Nitidez mía"}
    (tmp_path / "otro.json").write_text(json.dumps(propio), encoding="utf-8")
    catalogo, avisos = plugins.catalog(tmp_path)
    assert catalogo["nitidez2"].source.endswith("mio.json")
    assert catalogo["nitidez"].name == "Nitidez mía" and avisos == []


def test_un_plugin_danado_avisa_sin_tumbar_el_catalogo(tmp_path):
    (tmp_path / "roto.json").write_text("{", encoding="utf-8")
    (tmp_path / "prohibido.json").write_text(json.dumps({**NITIDEZ, "filtro": "movie"}),
                                             encoding="utf-8")
    catalogo, avisos = plugins.catalog(tmp_path)
    assert len(avisos) == 2 and "nitidez" in catalogo
    assert any("prohibido.json" in a for a in avisos)


# --- en el color ----------------------------------------------------------------------------------

def test_un_efecto_hace_que_el_color_no_sea_neutro_y_cambia_la_firma():
    ajuste = ColorAdjust()
    firma = ajuste.signature
    ajuste.effects = [{"plugin": "negativo", "values": {}, "enabled": True}]
    assert not ajuste.is_neutral and ajuste.signature != firma
    ajuste.effects[0]["enabled"] = False
    assert ajuste.is_neutral


def test_copiar_el_color_copia_los_efectos_aparte():
    ajuste = ColorAdjust(effects=[{"plugin": "desenfoque", "values": {"radio": 2}, "enabled": True}])
    copia = ajuste.copy()
    copia.effects[0]["values"]["radio"] = 9
    assert ajuste.effects[0]["values"]["radio"] == 2
    ajuste.reset()
    assert ajuste.effects == []


def test_guardar_limpia_los_efectos_danados():
    from vortex_studio.model.serialize import item_from_dict, item_to_dict
    from vortex_studio.model import Clip

    clip = Clip("a.mp4", 0, 1)
    clip.color.effects = [{"plugin": "grano", "values": {"fuerza": 30}, "enabled": True}]
    datos = item_to_dict(clip)
    assert item_from_dict(datos).color.effects == clip.color.effects
    datos["color"]["effects"] = [{"plugin": "grano", "values": {"fuerza": "x", "ok": 2}},
                                 {"plugin": "Mal Nombre"}, "basura"]
    assert item_from_dict(datos).color.effects == [
        {"plugin": "grano", "values": {"ok": 2.0}, "enabled": True}]


def _cuadro(media):
    import av

    with av.open(str(media["gris"])) as contenedor:
        return next(contenedor.decode(video=0))


def _degradado():
    import av

    arreglo = np.tile(np.linspace(0, 255, 64, dtype=np.uint8)[None, :, None], (36, 1, 3))
    return av.VideoFrame.from_ndarray(np.ascontiguousarray(arreglo), format="rgb24")


def test_el_negativo_invierte_el_cuadro(media):
    from vortex_studio.media.color import ColorProcessor

    ajuste = ColorAdjust(effects=[{"plugin": "negativo", "values": {}, "enabled": True}])
    salida = ColorProcessor().apply(_cuadro(media), ajuste).to_ndarray()
    assert float(salida.mean()) == pytest.approx(255 - 128, abs=4)


def test_el_espejo_voltea_y_apagado_no_hace_nada():
    from vortex_studio.media.color import ColorProcessor

    procesador = ColorProcessor()
    espejo = ColorAdjust(effects=[{"plugin": "espejo", "values": {}, "enabled": True}])
    fila = procesador.apply(_degradado(), espejo).to_ndarray()[18, :, 0].astype(int)
    assert fila[0] > 240 and fila[-1] < 15
    espejo.effects[0]["enabled"] = False
    espejo.exposure = 1               # para que haya grafo y se vea que el efecto no está
    fila = procesador.apply(_degradado(), espejo).to_ndarray()[18, :, 0].astype(int)
    assert fila[0] < 15 and fila[-1] > 240


def test_efectos_en_orden_y_un_plugin_que_ya_no_existe_se_salta(media):
    from vortex_studio.media.color import ColorProcessor

    ajuste = ColorAdjust(effects=[{"plugin": "no-instalado", "values": {}, "enabled": True},
                                  {"plugin": "negativo", "values": {}, "enabled": True},
                                  {"plugin": "negativo", "values": {}, "enabled": True}])
    salida = ColorProcessor().apply(_cuadro(media), ajuste).to_ndarray()
    assert float(salida.mean()) == pytest.approx(128, abs=4)


def test_un_plugin_que_ffmpeg_rechaza_no_deja_negro(media):
    from vortex_studio.media.color import ColorProcessor

    plugins._cache = {"malo": plugins.from_dict({
        "id": "malo", "filtro": "unsharp",
        "parametros": [{"id": "x", "opcion": "no_existe", "min": 0, "max": 1}]})}
    ajuste = ColorAdjust(exposure=100, effects=[{"plugin": "malo", "values": {}, "enabled": True}])
    salida = ColorProcessor().apply(_cuadro(media), ajuste)
    sin = ColorProcessor().apply(_cuadro(media), ColorAdjust(exposure=100))
    assert np.array_equal(salida.to_ndarray(), sin.to_ndarray())
