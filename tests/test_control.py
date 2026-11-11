"""El control del editor desde fuera: lo que usa el MCP para que Claude edite.

Cada orden se prueba contra una ventana de verdad (sin mostrarla): que haga el
cambio, que entre al historial y se deshaga, y que lo que se pide mal vuelva
como un error con texto y no como una excepción que tumbe el editor.
"""

from __future__ import annotations

import base64
import json
import threading
import time

import pytest

from vortex_studio.control import commands, socket_path
from vortex_studio.control.commands import CommandError, run


def _clips(w):
    return [c for p in w.sequence.tracks for c in p.clips]


def _v(w):
    """Los clips de video, en orden."""
    return sorted((c for p in w.sequence.tracks if p.kind == "video" for c in p.clips),
                  key=lambda c: c.start)


@pytest.fixture
def con_video(ventana, media):
    """Una ventana con el video con sonido puesto al inicio."""
    res = run(ventana, "colocar", {"ruta": str(media["sonoro"]), "en": 0})
    assert res["nuevos"]
    return ventana


def _id_video(w) -> str:
    estado = run(w, "estado", {})
    for pista in estado["pistas"]:
        for clip in pista["clips"]:
            if pista["tipo"] == "video" and clip["tipo"] != "texto":
                return clip["id"]
    raise AssertionError("no hay clip de video")


# --- órdenes sueltas -------------------------------------------------------------

def test_orden_desconocida_dice_cuales_hay(ventana):
    with pytest.raises(CommandError, match="cortar"):
        run(ventana, "volar", {})


def test_argumentos_que_no_son_objeto(ventana):
    with pytest.raises(CommandError):
        run(ventana, "estado", [])


def test_estado_de_un_proyecto_vacio(ventana):
    estado = run(ventana, "estado", {})
    assert estado["secuencia"]["duracion"] == 0
    assert estado["pistas"]
    assert estado["deshacer"] is None
    json.dumps(estado)      # tiene que poder viajar por el socket


def test_colocar_e_importar(ventana, media):
    res = run(ventana, "importar", {"rutas": [str(media["tono"])]})
    assert any("tono.wav" in m for m in res["medios"])
    res = run(ventana, "colocar", {"ruta": str(media["sonoro"]), "en": 0})
    assert len(res["nuevos"]) == 2          # el video y su audio enlazado
    estado = run(ventana, "estado", {})
    assert estado["secuencia"]["duracion"] == pytest.approx(6.0, abs=0.1)
    assert "Claude" in ventana.statusBar().currentMessage()


def test_colocar_un_archivo_que_no_existe(ventana, tmp_path):
    with pytest.raises(CommandError, match="No existe"):
        run(ventana, "colocar", {"ruta": str(tmp_path / "nada.mp4")})
    with pytest.raises(CommandError):
        run(ventana, "colocar", {})


def test_colocar_sin_en_va_al_final(con_video, media):
    run(con_video, "colocar", {"ruta": str(media["mudo"])})
    inicios = [c.start for c in _v(con_video)]
    assert inicios[-1] == pytest.approx(6.0, abs=0.05)


def test_cortar_un_clip_y_deshacer(con_video):
    ident = _id_video(con_video)
    antes = len(_clips(con_video))
    res = run(con_video, "cortar", {"t": 2.0, "id": ident})
    assert res["nuevos"]
    assert len(_clips(con_video)) == antes + 2          # se parte con su audio
    assert con_video.timeline.playhead == pytest.approx(2.0)
    run(con_video, "deshacer", {})
    assert len(_clips(con_video)) == antes
    run(con_video, "rehacer", {})
    assert len(_clips(con_video)) == antes + 2


def test_cortar_fuera_del_clip(con_video):
    with pytest.raises(CommandError, match="no cae dentro"):
        run(con_video, "cortar", {"t": 9.0, "id": _id_video(con_video)})


def test_cortar_sin_id_corta_todo_lo_que_cruza(con_video):
    run(con_video, "cortar", {"t": 3.0})
    assert len(_clips(con_video)) == 4


def test_numeros_que_no_son_numeros(con_video):
    for malo in ("abc", None, float("nan"), float("inf"), [1]):
        with pytest.raises(CommandError):
            run(con_video, "cortar", {"t": malo})
    with pytest.raises(CommandError, match="menor"):
        run(con_video, "cortar", {"t": -1})


def test_borrar_y_cerrar_hueco(con_video, media):
    run(con_video, "colocar", {"ruta": str(media["mudo"])})
    run(con_video, "cortar", {"t": 2.0})
    v = _v(con_video)
    assert len(v) == 3
    run(con_video, "borrar", {"ids": [v[0].uid], "cerrar_hueco": True})
    v = _v(con_video)
    assert len(v) == 2
    assert v[0].start == pytest.approx(0.0, abs=1e-6)


def test_borrar_un_id_que_no_hay(con_video):
    with pytest.raises(CommandError, match="estado"):
        run(con_video, "borrar", {"ids": ["no-existe"]})
    with pytest.raises(CommandError):
        run(con_video, "borrar", {})


def test_mover_lleva_su_audio(con_video):
    ident = _id_video(con_video)
    run(con_video, "mover", {"id": ident, "inicio": 4.0})
    for c in _clips(con_video):
        assert c.start == pytest.approx(4.0)
    run(con_video, "deshacer", {})
    for c in _clips(con_video):
        assert c.start == pytest.approx(0.0)


def test_mover_no_pisa_a_otro(con_video, media):
    run(con_video, "colocar", {"ruta": str(media["mudo"])})
    v = _v(con_video)
    with pytest.raises(CommandError, match="otro clip"):
        run(con_video, "mover", {"id": v[1].uid, "inicio": 3.0})
    assert v[1].start == pytest.approx(6.0, abs=0.05)


def test_mover_a_una_pista_de_otro_tipo(con_video):
    ident = _id_video(con_video)
    audio = next(i for i, p in enumerate(con_video.sequence.tracks) if p.kind == "audio")
    with pytest.raises(CommandError, match="no va"):
        run(con_video, "mover", {"id": ident, "inicio": 0, "pista": audio})
    with pytest.raises(CommandError, match="No hay pista"):
        run(con_video, "mover", {"id": ident, "inicio": 0, "pista": 99})


def test_recortar_orillas(con_video):
    ident = _id_video(con_video)
    res = run(con_video, "recortar", {"id": ident, "inicio": 1.0, "fin": 4.0})
    assert res["inicio"] == pytest.approx(1.0)
    assert res["duracion"] == pytest.approx(3.0)
    assert res["entrada"] == pytest.approx(1.0)
    for c in _clips(con_video):         # el audio enlazado va con él
        assert (c.start, c.duration) == (pytest.approx(1.0), pytest.approx(3.0))


def test_recortar_mas_alla_del_archivo(con_video):
    ident = _id_video(con_video)
    with pytest.raises(CommandError, match="después"):
        run(con_video, "recortar", {"id": ident, "fin": 30.0})
    with pytest.raises(CommandError, match="cuadro"):
        run(con_video, "recortar", {"id": ident, "inicio": 2.0, "fin": 2.0})


def test_pista_bloqueada(con_video):
    ident = _id_video(con_video)
    con_video._track_of(_v(con_video)[0]).locked = True
    with pytest.raises(CommandError, match="bloqueada"):
        run(con_video, "cortar", {"t": 1.0, "id": ident})
    with pytest.raises(CommandError, match="bloqueada"):
        run(con_video, "color", {"id": ident, "brillo": 10})


def test_texto_y_subtitulos(con_video):
    res = run(con_video, "texto", {"texto": "Hola", "inicio": 0.5, "duracion": 2,
                                   "posicion": "Arriba centro", "negrita": True})
    titulo, _ = commands._find(con_video, res["id"])
    assert titulo.text == "Hola" and titulo.bold
    res = run(con_video, "subtitulos", {"lineas": [
        {"texto": "uno", "inicio": 3.0, "duracion": 1.0},
        {"texto": "dos", "inicio": 4.0, "duracion": 1.0}]})
    assert len(res["ids"]) == 2
    etiqueta = con_video.history.undo_label
    run(con_video, "deshacer", {})          # los dos de un solo paso
    textos = [c for c in _clips(con_video) if getattr(c, "text", None) in ("uno", "dos")]
    assert not textos, etiqueta


def test_texto_mal_pedido(con_video):
    with pytest.raises(CommandError, match="texto"):
        run(con_video, "texto", {"texto": "  "})
    with pytest.raises(CommandError, match="posicion"):
        run(con_video, "texto", {"texto": "x", "posicion": "Por allá"})
    with pytest.raises(CommandError, match="encima"):
        run(con_video, "subtitulos", {"lineas": [
            {"texto": "a", "inicio": 0, "duracion": 2},
            {"texto": "b", "inicio": 1, "duracion": 2}]})


def test_texto_en_una_orilla_se_alinea_hacia_ella(con_video):
    """Con «Abajo izquierda» centrado en el 6 % del ancho, medio texto se salía."""
    res = run(con_video, "texto", {"texto": "Hola", "inicio": 0, "duracion": 1,
                                   "posicion": "Abajo izquierda"})
    titulo, _ = commands._find(con_video, res["id"])
    assert titulo.align == "izquierda"
    run(con_video, "editar_texto", {"id": res["id"], "posicion": "Abajo derecha"})
    assert titulo.align == "derecha"
    run(con_video, "editar_texto", {"id": res["id"], "posicion": "Subtítulo"})
    assert titulo.align == "centro"


def test_editar_texto(con_video):
    res = run(con_video, "texto", {"texto": "Hola", "inicio": 0, "duracion": 1})
    res = run(con_video, "editar_texto", {"id": res["id"], "texto": "Adiós", "color": "#ff0000"})
    assert res["texto"] == "Adiós"
    with pytest.raises(CommandError, match="no es un texto"):
        run(con_video, "editar_texto", {"id": _id_video(con_video), "texto": "x"})


def test_color(con_video):
    ident = _id_video(con_video)
    res = run(con_video, "color", {"id": ident, "contraste": 130, "saturacion": 0})
    assert res["contraste"] == 130 and res["saturacion"] == 0
    with pytest.raises(CommandError, match="mayor"):
        run(con_video, "color", {"id": ident, "contraste": 900})
    with pytest.raises(CommandError, match="Di qué"):
        run(con_video, "color", {"id": ident})


def test_volumen_fundido_velocidad(con_video):
    audio = next(c for p in con_video.sequence.tracks if p.kind == "audio" for c in p.clips)
    run(con_video, "volumen", {"id": audio.uid, "db": -6})
    assert audio.gain == pytest.approx(10 ** (-6 / 20))
    ident = _id_video(con_video)
    res = run(con_video, "fundido", {"id": ident, "entrada": 1.0, "salida": 0.5})
    assert res == {"fundido_entrada": 1.0, "fundido_salida": 0.5}
    res = run(con_video, "velocidad", {"id": ident, "factor": 2})
    assert res["duracion"] == pytest.approx(3.0, abs=0.05)


def test_transicion(con_video, media):
    run(con_video, "colocar", {"ruta": str(media["mudo"])})
    v = _v(con_video)
    with pytest.raises(CommandError, match="izquierda"):
        run(con_video, "transicion", {"id": v[0].uid})
    with pytest.raises(CommandError, match="tipo"):
        run(con_video, "transicion", {"id": v[1].uid, "tipo": "Estrella"})
    res = run(con_video, "transicion", {"id": v[1].uid, "segundos": 0.5, "tipo": "A negro"})
    assert res["transicion"] == pytest.approx(0.5)
    assert res["tipo"] == "A negro"


def test_formato_y_ver_cuadro(con_video):
    run(con_video, "formato", {"ancho": 1080, "alto": 1920})
    assert (con_video.sequence.width, con_video.sequence.height) == (1080, 1920)
    res = run(con_video, "ver_cuadro", {"t": 1.0, "ancho": 200})
    png = base64.b64decode(res["imagen_png"])
    assert png.startswith(b"\x89PNG")
    res = run(con_video, "ver_editor", {"ancho": 400})
    assert base64.b64decode(res["imagen_png"]).startswith(b"\x89PNG")


def test_ir_a_reproducir_pausar(con_video):
    assert run(con_video, "ir_a", {"t": 2.5})["playhead"] == pytest.approx(2.5)
    run(con_video, "reproducir", {})
    run(con_video, "pausar", {})
    assert not con_video._playing


def test_deshacer_sin_historia(ventana):
    with pytest.raises(CommandError, match="deshacer"):
        run(ventana, "deshacer", {})
    with pytest.raises(CommandError, match="rehacer"):
        run(ventana, "rehacer", {})


def test_quitar_silencios(ventana, tmp_path, media):
    import shutil
    import subprocess

    def _ffmpeg(*args):
        ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", *args], check=True)

    # 1 s de tono, 1.5 s de silencio y 1 s de tono.
    hablado = tmp_path / "hablado.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=1.5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1", str(hablado))
    res = run(ventana, "colocar", {"ruta": str(hablado), "en": 0})
    res = run(ventana, "quitar_silencios", {"id": res["nuevos"][0]})
    assert res["silencios_quitados"] == 1
    assert res["duracion"] < 3.0


def test_guardar_y_abrir(con_video, tmp_path):
    with pytest.raises(CommandError, match="ruta"):
        run(con_video, "guardar", {})
    with pytest.raises(CommandError, match="carpeta"):
        run(con_video, "guardar", {"ruta": str(tmp_path / "no" / "hay.vortex")})
    res = run(con_video, "guardar", {"ruta": str(tmp_path / "corto")})
    assert res["proyecto"].endswith("corto.vortex")
    assert not con_video._dirty

    run(con_video, "cortar", {"t": 1.0})
    with pytest.raises(CommandError, match="sin guardar"):
        run(con_video, "abrir_proyecto", {"ruta": res["proyecto"]})
    with pytest.raises(CommandError, match="sin guardar"):
        run(con_video, "nuevo_proyecto", {})
    estado = run(con_video, "abrir_proyecto", {"ruta": res["proyecto"], "descartar": True})
    assert sum(len(p["clips"]) for p in estado["pistas"]) == 2

    estado = run(con_video, "nuevo_proyecto", {"ancho": 1080, "alto": 1080})
    assert estado["secuencia"]["ancho"] == 1080
    assert estado["secuencia"]["duracion"] == 0


def test_exportar(con_video, tmp_path):
    from vortex_studio.ui.render_queue import DONE

    with pytest.raises(CommandError, match="calidad"):
        run(con_video, "exportar", {"ruta": str(tmp_path / "x.mp4"), "calidad": "Ultra"})
    with pytest.raises(CommandError, match="fin"):
        run(con_video, "exportar", {"ruta": str(tmp_path / "x.mp4"), "inicio": 3, "fin": 1})
    res = run(con_video, "exportar", {"ruta": str(tmp_path / "corto"), "calidad": "Borrador",
                                      "fin": 1.0})
    assert con_video.render_queue.wait(60)
    estado = run(con_video, "estado_exportacion", {"exportacion": res["exportacion"]})
    assert estado["estado"] == DONE, estado
    assert estado["error"] is None
    assert (tmp_path / "corto.mp4").stat().st_size > 0
    with pytest.raises(CommandError, match="No conozco"):
        run(con_video, "estado_exportacion", {"exportacion": 999999})


def test_todas_las_herramientas_del_mcp_existen_en_el_editor():
    from vortex_studio import mcp

    for tool in mcp.TOOLS:
        if tool["name"] != "abrir_editor":
            assert tool["name"] in commands.OPS, tool["name"]
    assert set(commands.OPS) <= mcp.NOMBRES
    from vortex_studio.model.overlays import ANCHORS
    assert mcp.POSICIONES == list(ANCHORS)


# --- el socket ---------------------------------------------------------------------

@pytest.fixture
def servidor(ventana, tmp_path, monkeypatch):
    from vortex_studio.control.server import attach

    monkeypatch.setenv("VORTEX_CONTROL_SOCKET", str(tmp_path / "s" / "control.sock"))
    srv = attach(ventana)
    assert srv.listening
    yield srv
    srv.stop()


def _en_hilo(qapp, fn, limite=30.0):
    """Corre `fn` (que habla por el socket) en otro hilo mientras Qt atiende."""
    salida = {}

    def correr():
        try:
            salida["ok"] = fn()
        except BaseException as error:     # noqa: BLE001 — se revisa abajo
            salida["error"] = error

    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    fin = time.monotonic() + limite
    while hilo.is_alive() and time.monotonic() < fin:
        qapp.processEvents()
        time.sleep(0.005)
    assert not hilo.is_alive(), "el socket no respondió"
    if "error" in salida:
        raise salida["error"]
    return salida["ok"]


def test_socket_en_la_ruta_pedida(servidor, tmp_path):
    assert socket_path() == tmp_path / "s" / "control.sock"
    assert (tmp_path / "s").stat().st_mode & 0o777 == 0o700


def test_socket_responde_y_prende_el_aviso(servidor, qapp, media):
    from vortex_studio.mcp import Editor

    editor = Editor()
    estado = _en_hilo(qapp, lambda: editor.call("estado", {}))
    assert estado["secuencia"]["duracion"] == 0
    qapp.processEvents()
    assert servidor.window.control_badge.isVisibleTo(servidor.window)

    nuevos = _en_hilo(qapp, lambda: editor.call("colocar", {"ruta": str(media["mudo"]), "en": 0}))
    assert nuevos["nuevos"]
    with pytest.raises(RuntimeError, match="No conozco"):
        _en_hilo(qapp, lambda: editor.call("volar", {}))

    editor.close()
    for _ in range(50):
        qapp.processEvents()
        if not servidor.window.control_badge.isVisibleTo(servidor.window):
            break
        time.sleep(0.01)
    assert not servidor.window.control_badge.isVisibleTo(servidor.window)


def test_socket_aguanta_basura(servidor, qapp):
    import socket as so

    def hablar():
        s = so.socket(so.AF_UNIX, so.SOCK_STREAM)
        s.settimeout(5)
        s.connect(str(socket_path()))
        s.sendall(b"esto no es json\n[1,2]\n" + json.dumps({"id": 7, "op": "estado"}).encode() + b"\n")
        datos = b""
        while datos.count(b"\n") < 3:
            datos += s.recv(65536)
        s.close()
        return [json.loads(x) for x in datos.splitlines()]

    r = _en_hilo(qapp, hablar)
    assert [x["ok"] for x in r] == [False, False, True]
    assert r[2]["id"] == 7


def test_una_excepcion_no_tumba_el_editor(servidor, monkeypatch):
    def truena(window, args):
        raise ZeroDivisionError("ups")

    monkeypatch.setitem(commands.OPS, "truena", truena)
    r = servidor.handle(json.dumps({"id": 1, "op": "truena"}).encode())
    assert r == {"id": 1, "ok": False, "error": "ZeroDivisionError: ups"}


def test_segundo_editor_no_le_quita_el_socket_al_primero(servidor, qapp):
    from vortex_studio.control.server import ControlServer

    otro = ControlServer(servidor.window)
    assert not otro.start()
    assert servidor.listening


def test_socket_viejo_de_un_cierre_de_golpe(ventana, tmp_path, monkeypatch):
    from vortex_studio.control.server import ControlServer

    ruta = tmp_path / "v" / "control.sock"
    ruta.parent.mkdir()
    import socket as so
    viejo = so.socket(so.AF_UNIX, so.SOCK_STREAM)
    viejo.bind(str(ruta))
    viejo.close()           # queda el archivo sin nadie escuchando
    monkeypatch.setenv("VORTEX_CONTROL_SOCKET", str(ruta))
    srv = ControlServer(ventana)
    assert srv.start()
    srv.stop()


# --- el servidor MCP -----------------------------------------------------------------

def _mcp(mensajes, editor=None):
    import io

    from vortex_studio import mcp

    entrada = io.StringIO("".join(json.dumps(m) + "\n" for m in mensajes))
    salida = io.StringIO()
    if editor is None:
        mcp.main(entrada, salida)
    else:
        for m in mensajes:
            mcp.handle(editor, m, salida)
    return [json.loads(x) for x in salida.getvalue().splitlines()]


def test_mcp_initialize_y_lista(monkeypatch, tmp_path):
    monkeypatch.setenv("VORTEX_CONTROL_SOCKET", str(tmp_path / "nadie.sock"))
    r = _mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
    ])
    assert [x["id"] for x in r] == [1, 2, 3, 4]
    assert r[0]["result"]["protocolVersion"] == "2025-06-18"
    assert "instructions" in r[0]["result"]
    nombres = {t["name"] for t in r[1]["result"]["tools"]}
    assert {"estado", "cortar", "ver_cuadro", "abrir_editor"} <= nombres
    for tool in r[1]["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"
        assert set(tool["inputSchema"]["required"]) <= set(tool["inputSchema"]["properties"])
    assert r[3]["error"]["code"] == -32601


def test_mcp_protocolo_desconocido_da_el_mas_nuevo():
    from vortex_studio import mcp

    r = _mcp([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "1999-01-01"}}])
    assert r[0]["result"]["protocolVersion"] == mcp.PROTOCOLOS[0]


def test_mcp_json_invalido():
    import io

    from vortex_studio import mcp

    salida = io.StringIO()
    mcp.main(io.StringIO("{no\n\n"), salida)
    r = json.loads(salida.getvalue())
    assert r["error"]["code"] == -32700


def test_mcp_con_el_editor_cerrado(monkeypatch, tmp_path):
    monkeypatch.setenv("VORTEX_CONTROL_SOCKET", str(tmp_path / "nadie.sock"))
    r = _mcp([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "estado", "arguments": {}}},
              {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "inventada", "arguments": {}}}])
    assert r[0]["result"]["isError"]
    assert "abrir_editor" in r[0]["result"]["content"][0]["text"]
    assert r[1]["result"]["isError"]


def test_mcp_contenido_con_imagen():
    from vortex_studio import mcp

    partes = mcp.contenido({"t": 1.0, "imagen_png": "QUJD"})
    assert partes[0] == {"type": "image", "data": "QUJD", "mimeType": "image/png"}
    assert json.loads(partes[1]["text"]) == {"t": 1.0}
    assert mcp.contenido("hola") == [{"type": "text", "text": "hola"}]


def test_mcp_de_punta_a_punta(servidor, qapp, media):
    """Claude → MCP → socket → editor, y de regreso, con imagen incluida."""
    from vortex_studio import mcp

    editor = mcp.Editor()

    def hablar():
        return _mcp([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "colocar", "arguments": {"ruta": str(media["sonoro"]), "en": 0}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "cortar", "arguments": {"t": 2.0}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "ver_cuadro", "arguments": {"t": 1.0, "ancho": 160}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "cortar", "arguments": {"t": "x"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "abrir_editor", "arguments": {}}},
        ], editor)

    r = _en_hilo(qapp, hablar)
    editor.close()
    assert not r[0]["result"]["isError"]
    assert len(_clips(servidor.window)) == 4
    assert r[2]["result"]["content"][0]["type"] == "image"
    assert r[3]["result"]["isError"]
    assert "número" in r[3]["result"]["content"][0]["text"]
    assert "ya está abierto" in r[4]["result"]["content"][0]["text"]


def test_mcp_reintenta_si_el_editor_se_reinicio(servidor, qapp):
    from vortex_studio import mcp

    editor = mcp.Editor()
    _en_hilo(qapp, lambda: editor.call("estado", {}))
    # El editor se cierra y vuelve a abrir: el socket viejo ya no sirve.
    servidor.stop()
    assert servidor.start()
    assert _en_hilo(qapp, lambda: editor.call("estado", {}))["pistas"]
    editor.close()


def test_mcp_arranca_sin_qt():
    """`--mcp` no debe cargar Qt: Claude lo arranca a cada sesión."""
    import subprocess
    import sys

    codigo = ("import sys, io; sys.argv=['x','--mcp']; sys.stdin=io.StringIO('');"
              "import runpy\n"
              "try: runpy.run_module('vortex_studio', run_name='__main__')\n"
              "except SystemExit: pass\n"
              "print('PySide6' in sys.modules)")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                            timeout=60)
    assert salida.stdout.strip().endswith("False"), salida.stderr
