"""Servidor MCP de Vortex Studio: Claude edita video en el editor abierto.

Claude Code lo arranca solo con `vortex-studio --mcp` (se registra con
`claude mcp add --scope user vortex-studio -- vortex-studio --mcp`). Habla
JSON-RPC por stdin/stdout y le pasa cada herramienta al editor por su socket
de control (`vortex_studio.control`): los cambios se ven en vivo en la
ventana y se deshacen con Ctrl+Z.

Solo biblioteca estándar, sin Qt: arranca al instante y no abre ventanas. Si
el editor no está abierto, `abrir_editor` lo abre.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

from vortex_studio import __version__
from vortex_studio.control import socket_path

PROTOCOLOS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LENTAS = {"quitar_silencios", "detectar_escenas", "normalizar_volumen", "importar", "colocar",
          "abrir_proyecto"}

INSTRUCCIONES = (
    "Vortex Studio es el editor de video de la persona (y de Vortexine's OS). Con estas "
    "herramientas editas en su editor abierto y ella ve cada cambio en vivo; todo se deshace "
    "con Ctrl+Z o con «deshacer». Empieza con «estado» (si dice que el editor no está abierto, "
    "usa «abrir_editor»). Los clips se nombran por el «id» que da «estado»; tras cortar o "
    "borrar, vuelve a pedir «estado». Después de cambios visibles, revisa con «ver_cuadro». "
    "Tiempos en segundos de la secuencia. No guardes ni exportes encima de un archivo sin que "
    "la persona lo pida, y no abras otro proyecto si hay cambios sin guardar sin preguntarle."
)

ID = {"type": "string", "description": "id del clip, tal como lo da «estado»"}
T = {"type": "number", "description": "segundo de la secuencia"}
POSICIONES = ["Arriba izquierda", "Arriba centro", "Arriba derecha", "Centro izquierda", "Centro",
              "Centro derecha", "Abajo izquierda", "Subtítulo", "Abajo derecha"]
ESTILO_TEXTO = {
    "posicion": {"type": "string", "enum": POSICIONES},
    "tamano": {"type": "number", "description": "alto de la letra como fracción del cuadro (0.075 por omisión)"},
    "color": {"type": "string", "description": "como #ffffff"},
    "negrita": {"type": "boolean"}, "fondo": {"type": "boolean", "description": "caja detrás del texto"},
    "sombra": {"type": "boolean"},
}


def _tool(nombre: str, descripcion: str, props: dict | None = None, requeridos=()) -> dict:
    return {"name": nombre, "description": descripcion,
            "inputSchema": {"type": "object", "properties": props or {},
                            "required": list(requeridos)}}


TOOLS = [
    _tool("abrir_editor", "Abre Vortex Studio en el editor de video si no está abierto, y espera a que esté listo."),
    _tool("estado", "El proyecto abierto: formato, duración, playhead, pistas con sus clips (id, inicio, fin, archivo…) y medios importados."),
    _tool("ver_cuadro", "Imagen del cuadro de la secuencia en un segundo (como se exportaría). Úsala para revisar lo que hiciste.",
          {"t": T, "ancho": {"type": "integer", "description": "ancho de la imagen, 640 por omisión"}}),
    _tool("ver_editor", "Captura de la ventana del editor tal como la ve la persona.",
          {"ancho": {"type": "integer"}}),
    _tool("nuevo_proyecto", "Empieza un proyecto vacío, opcionalmente con su formato.",
          {"ancho": {"type": "integer"}, "alto": {"type": "integer"},
           "descartar": {"type": "boolean", "description": "tira los cambios sin guardar (solo si la persona lo autoriza)"}}),
    _tool("abrir_proyecto", "Abre un proyecto .vortex.",
          {"ruta": {"type": "string"}, "descartar": {"type": "boolean"}}, ["ruta"]),
    _tool("importar", "Agrega archivos (video, audio, imágenes) al panel de medios.",
          {"rutas": {"type": "array", "items": {"type": "string"}}}, ["rutas"]),
    _tool("colocar", "Pone un archivo en el timeline. Sin «en», al final; sin «pista», en la de siempre según el tipo.",
          {"ruta": {"type": "string"}, "en": T, "pista": {"type": "integer"}}, ["ruta"]),
    _tool("cortar", "Corta en un segundo. Con «id», solo ese clip (y su audio enlazado); sin id, todo lo que cruce ese segundo.",
          {"t": T, "id": ID}, ["t"]),
    _tool("borrar", "Borra clips. Con «cerrar_hueco», lo de después se recorre para no dejar hueco.",
          {"ids": {"type": "array", "items": {"type": "string"}}, "cerrar_hueco": {"type": "boolean"}}, ["ids"]),
    _tool("mover", "Mueve un clip (con su enlazado) a otro segundo y opcionalmente a otra pista del mismo tipo. No pisa otros clips.",
          {"id": ID, "inicio": T, "pista": {"type": "integer"}}, ["id", "inicio"]),
    _tool("recortar", "Mueve las orillas de un clip: nuevo «inicio» y/o «fin» en el timeline.",
          {"id": ID, "inicio": T, "fin": T}, ["id"]),
    _tool("quitar_silencios", "Corta los silencios de un clip y cierra los huecos (cortes rápidos estilo TikTok/YouTube).",
          {"id": ID, "umbral_db": {"type": "number", "description": "-40 por omisión"},
           "minimo": {"type": "number", "description": "silencio mínimo en segundos, 0.5 por omisión"}}, ["id"]),
    _tool("detectar_escenas", "Corta un clip en cada cambio de escena (o solo marca, con cortar=false).",
          {"id": ID, "cortar": {"type": "boolean"}, "sensibilidad": {"type": "number"}}, ["id"]),
    _tool("texto", "Pone un texto en pantalla (título, rótulo, subtítulo).",
          {"texto": {"type": "string"}, "inicio": T, "duracion": {"type": "number"}, **ESTILO_TEXTO}, ["texto"]),
    _tool("subtitulos", "Pone varias líneas de texto de un jalón, cada una con su inicio y duración. Un solo paso de deshacer.",
          {"lineas": {"type": "array", "items": {"type": "object", "properties": {
              "texto": {"type": "string"}, "inicio": T, "duracion": {"type": "number"}},
              "required": ["texto", "inicio", "duracion"]}}, **ESTILO_TEXTO}, ["lineas"]),
    _tool("editar_texto", "Cambia el texto, posición o estilo de un texto existente.",
          {"id": ID, "texto": {"type": "string"}, **ESTILO_TEXTO}, ["id"]),
    _tool("color", "Corrección de color de un clip. Contraste y saturación: 100 = sin cambio (0 a 200); exposición en centésimas de paso (-300 a 300); brillo, temperatura y matiz de -100 a 100; viñeta 0 a 100.",
          {"id": ID, **{k: {"type": "number"} for k in
                        ("exposicion", "brillo", "contraste", "saturacion", "temperatura", "matiz", "vineta")}}, ["id"]),
    _tool("volumen", "Volumen de un clip en dB (0 = como viene).", {"id": ID, "db": {"type": "number"}}, ["id", "db"]),
    _tool("fundido", "Fundido de entrada y/o salida de un clip, en segundos.",
          {"id": ID, "entrada": {"type": "number"}, "salida": {"type": "number"}}, ["id"]),
    _tool("transicion", "Transición entre un clip y el de su izquierda.",
          {"id": ID, "segundos": {"type": "number", "description": "0.5 por omisión; 0 la quita"},
           "tipo": {"type": "string", "enum": ["Cruzada", "A negro", "A blanco"]}}, ["id"]),
    _tool("velocidad", "Cámara lenta o rápida: 0.5 = la mitad, 2 = el doble.",
          {"id": ID, "factor": {"type": "number"}}, ["id", "factor"]),
    _tool("normalizar_volumen", "Iguala el volumen de todo a un nivel (‑14 LUFS, el de las redes).",
          {"lufs": {"type": "number"}}),
    _tool("formato", "Tamaño del cuadro: 1080×1920 vertical (TikTok, Reels), 1920×1080, 1080×1080…",
          {"ancho": {"type": "integer"}, "alto": {"type": "integer"}}, ["ancho", "alto"]),
    _tool("ir_a", "Lleva el playhead a un segundo.", {"t": T}, ["t"]),
    _tool("reproducir", "Reproduce en el editor, opcionalmente desde un segundo.", {"desde": T}),
    _tool("pausar", "Pausa la reproducción."),
    _tool("deshacer", "Deshace el último cambio."),
    _tool("rehacer", "Rehace lo último deshecho."),
    _tool("guardar", "Guarda el proyecto (la primera vez, con «ruta» de un .vortex).", {"ruta": {"type": "string"}}),
    _tool("exportar", "Exporta la secuencia a un .mp4 en segundo plano. Revisa con «estado_exportacion».",
          {"ruta": {"type": "string"}, "calidad": {"type": "string", "enum": ["Borrador", "Normal", "Alta"]},
           "inicio": T, "fin": T}, ["ruta"]),
    _tool("estado_exportacion", "Cómo va una exportación.", {"exportacion": {"type": "integer"}}, ["exportacion"]),
]
NOMBRES = {t["name"] for t in TOOLS}


class EditorClosed(Exception):
    pass


class Editor:
    """La conexión con el editor abierto."""

    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.buf = b""
        self.next_id = 0

    def connect(self) -> None:
        if self.sock is not None:
            return
        ruta = str(socket_path())
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(ruta)
        except OSError:
            s.close()
            raise EditorClosed from None
        self.sock, self.buf = s, b""

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = None

    def call(self, op: str, args: dict, timeout: float = 30.0):
        for intento in (0, 1):
            self.connect()
            self.next_id += 1
            try:
                self.sock.settimeout(timeout)
                self.sock.sendall(json.dumps({"id": self.next_id, "op": op, "args": args}).encode() + b"\n")
                while b"\n" not in self.buf:
                    trozo = self.sock.recv(1 << 20)
                    if not trozo:
                        raise ConnectionError
                    self.buf += trozo
            except socket.timeout:
                self.close()
                raise RuntimeError(f"El editor no respondió en {timeout:g} s.") from None
            except OSError:
                self.close()        # el editor se cerró o se reinició: un reintento
                if intento:
                    raise EditorClosed from None
                continue
            linea, self.buf = self.buf.split(b"\n", 1)
            respuesta = json.loads(linea)
            if not respuesta.get("ok"):
                raise RuntimeError(respuesta.get("error") or "El editor no pudo hacerlo.")
            return respuesta.get("result")
        raise EditorClosed


def launch_command() -> list[str]:
    if getattr(sys, "frozen", False):           # el ejecutable de PyInstaller
        return [sys.executable, "--video"]
    return [sys.executable, "-m", "vortex_studio", "--video"]


def abrir_editor(editor: Editor, espera: float = 40.0) -> str:
    try:
        editor.call("estado", {})
        return "El editor ya está abierto."
    except EditorClosed:
        pass
    subprocess.Popen(launch_command(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        time.sleep(0.5)
        try:
            editor.call("estado", {})
            return "Listo: Vortex Studio está abierto en el editor de video."
        except EditorClosed:
            continue
    raise RuntimeError("Abrí Vortex Studio pero no respondió a tiempo. Pídele a la persona que lo revise.")


def contenido(resultado) -> list[dict]:
    """El resultado como contenido MCP: las imágenes van como imagen, lo demás como JSON."""
    partes = []
    if isinstance(resultado, dict) and "imagen_png" in resultado:
        resultado = dict(resultado)
        partes.append({"type": "image", "data": resultado.pop("imagen_png"), "mimeType": "image/png"})
    partes.append({"type": "text", "text": json.dumps(resultado, ensure_ascii=False, indent=1)
                   if not isinstance(resultado, str) else resultado})
    return partes


def call_tool(editor: Editor, nombre: str, args: dict) -> tuple[list[dict], bool]:
    if nombre not in NOMBRES:
        return [{"type": "text", "text": f"No conozco la herramienta «{nombre}»."}], True
    try:
        if nombre == "abrir_editor":
            return contenido(abrir_editor(editor)), False
        return contenido(editor.call(nombre, args, timeout=600.0 if nombre in LENTAS else 30.0)), False
    except EditorClosed:
        return [{"type": "text", "text": "Vortex Studio no está abierto. Usa «abrir_editor» "
                 "(o pídele a la persona que lo abra en el editor de video)."}], True
    except RuntimeError as error:
        return [{"type": "text", "text": str(error)}], True


def respond(salida, id_, resultado=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = resultado
    salida.write(json.dumps(msg, ensure_ascii=False) + "\n")
    salida.flush()


def handle(editor: Editor, msg: dict, salida) -> None:
    metodo = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}
    if id_ is None:
        return      # notificación (p. ej. notifications/initialized): no lleva respuesta
    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        respond(salida, id_, {
            "protocolVersion": pedida if pedida in PROTOCOLOS else PROTOCOLOS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "vortex-studio", "version": __version__},
            "instructions": INSTRUCCIONES,
        })
    elif metodo == "ping":
        respond(salida, id_, {})
    elif metodo == "tools/list":
        respond(salida, id_, {"tools": TOOLS})
    elif metodo == "tools/call":
        partes, fallo = call_tool(editor, str(params.get("name", "")), params.get("arguments") or {})
        respond(salida, id_, {"content": partes, "isError": fallo})
    else:
        respond(salida, id_, error={"code": -32601, "message": f"Método desconocido: {metodo}"})


def main(entrada=None, salida=None) -> int:
    entrada = entrada or sys.stdin
    salida = salida or sys.stdout
    editor = Editor()
    for linea in entrada:
        linea = linea.strip()
        if not linea:
            continue
        try:
            msg = json.loads(linea)
        except ValueError:
            respond(salida, None, error={"code": -32700, "message": "JSON inválido"})
            continue
        if isinstance(msg, dict):
            handle(editor, msg, salida)
    editor.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
