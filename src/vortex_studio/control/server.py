"""El socket por el que el editor abierto recibe órdenes.

Una orden por línea, en JSON: `{"id": 1, "op": "cortar", "args": {...}}`. La
respuesta, también una línea: `{"id": 1, "ok": true, "result": ...}` o
`{"id": 1, "ok": false, "error": "..."}`.

Todo corre en el hilo de la interfaz, dentro del ciclo de eventos de Qt: una
orden se aplica igual que un clic, sin carreras con lo que esté haciendo la
persona. El socket vive en `XDG_RUNTIME_DIR`, que solo abre tu usuario.
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from vortex_studio.control import commands, socket_path

MAX_LINE = 4 * 1024 * 1024     # una orden nunca es tan grande; más es basura


def _someone_listening(ruta: str) -> bool:
    prueba = QLocalSocket()
    prueba.connectToServer(ruta)
    vivo = prueba.waitForConnected(300)
    prueba.abort()
    return vivo


class ControlServer(QObject):
    """Escucha órdenes para `window`. `clients_changed` dice cuántos hay conectados."""

    clients_changed = Signal(int)

    def __init__(self, window, parent=None) -> None:
        super().__init__(parent or window)
        self.window = window
        self.path = socket_path()
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        self._server.newConnection.connect(self._accept)
        self._buffers: dict[QLocalSocket, bytes] = {}

    @property
    def listening(self) -> bool:
        return self._server.isListening()

    def start(self) -> bool:
        """Empieza a escuchar. Si ya hay otro editor escuchando, lo deja en paz."""
        ruta = str(self.path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self.path.parent, 0o700)
        except OSError:
            return False
        if self.path.exists():
            if _someone_listening(ruta):
                return False            # otra ventana ya es «el editor» para Claude
            QLocalServer.removeServer(ruta)     # quedó de un cierre de golpe
        return self._server.listen(ruta)

    def stop(self) -> None:
        for sock in list(self._buffers):
            sock.abort()
        self._buffers.clear()
        if self._server.isListening():
            self._server.close()
        self.clients_changed.emit(0)

    # --- conexiones ---------------------------------------------------------

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self._drop(s))
        self.clients_changed.emit(len(self._buffers))

    def _drop(self, sock: QLocalSocket) -> None:
        if self._buffers.pop(sock, None) is not None:
            sock.deleteLater()
            self.clients_changed.emit(len(self._buffers))

    def _read(self, sock: QLocalSocket) -> None:
        if sock not in self._buffers:
            return
        datos = self._buffers[sock] + bytes(sock.readAll())
        *lineas, resto = datos.split(b"\n")
        if len(resto) > MAX_LINE:
            sock.abort()
            return
        self._buffers[sock] = resto
        for linea in lineas:
            if linea.strip():
                respuesta = self.handle(linea)
                if sock.state() != QLocalSocket.ConnectedState:
                    return
                sock.write(json.dumps(respuesta, ensure_ascii=False).encode() + b"\n")
                sock.flush()

    def handle(self, linea: bytes) -> dict:
        """Una orden en bruto → su respuesta. Nunca lanza: un error es una respuesta."""
        try:
            orden = json.loads(linea)
            if not isinstance(orden, dict):
                raise ValueError
        except ValueError:
            return {"id": None, "ok": False, "error": "La orden no es JSON válido."}
        ident = orden.get("id")
        try:
            resultado = commands.run(self.window, str(orden.get("op", "")), orden.get("args") or {})
        except commands.CommandError as error:
            return {"id": ident, "ok": False, "error": str(error)}
        except Exception as error:          # un bug no debe tumbar el editor
            return {"id": ident, "ok": False, "error": f"{type(error).__name__}: {error}"}
        return {"id": ident, "ok": True, "result": resultado}


def attach(window) -> ControlServer:
    """Pone a escuchar al editor y le agrega el aviso «Claude está editando»."""
    from PySide6.QtWidgets import QLabel

    from vortex_studio.ui import theme

    aviso = QLabel("●  Claude está editando")
    aviso.setStyleSheet(f"color: {theme.ACENTO}; background: {theme.PILDORA}; "
                        "border-radius: 9px; padding: 2px 10px; font-size: 11px;")
    aviso.setToolTip("Claude está conectado a este editor. Lo que hace se deshace con Ctrl+Z.")
    aviso.hide()
    window.statusBar().addPermanentWidget(aviso)
    servidor = ControlServer(window)
    servidor.clients_changed.connect(lambda n: aviso.setVisible(n > 0))
    servidor.start()
    window.control_server = servidor
    window.control_badge = aviso
    return servidor
