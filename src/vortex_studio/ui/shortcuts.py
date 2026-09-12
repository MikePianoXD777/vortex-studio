"""Mapa de atajos de teclado, guardado en un archivo que el usuario cambia.

Antes cada atajo estaba escrito a mano junto a su acción. Cambiar uno era
editar código, y las flechas ni siquiera eran acciones: vivían dentro de
`keyPressEvent`.

Ahora cada acción tiene una **clave** estable (`editar.cortar`) y la tecla
sale de este mapa. Los valores de fábrica viven aquí; lo que el usuario
cambie se guarda en `atajos.json`, en la carpeta de configuración del
sistema, y se valida al cargarlo:

- una tecla que no existe se ignora y se queda la de fábrica;
- nada con `Ctrl+Alt`, que en teclado latinoamericano es AltGr: escribir
  una `@` dispararía el atajo;
- nunca dos acciones con la misma tecla.

Un archivo mal escrito nunca impide abrir el editor: se avisa en la barra de
estado y se usan los atajos de fábrica.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

FILE_VERSION = 1
PORTABLE = QKeySequence.PortableText

GROUPS = {
    "archivo": "Archivo",
    "editar": "Editar",
    "herramienta": "Herramientas",
    "clip": "Clip",
    "capa": "Capa",
    "insertar": "Insertar",
    "reproducir": "Reproducción",
    "navegar": "Navegación",
    "marcar": "Marcar",
    "ver": "Ver",
}

# clave -> (nombre que ve el usuario, tecla de fábrica). El orden es el de
# los menús, y es el orden en que aparecen en el editor de atajos.
DEFAULTS: dict[str, tuple[str, str]] = {
    "archivo.nuevo": ("Nuevo proyecto", "Ctrl+N"),
    "archivo.abrir": ("Abrir proyecto", "Ctrl+O"),
    "archivo.guardar": ("Guardar", "Ctrl+S"),
    "archivo.guardar_como": ("Guardar como", "Ctrl+Shift+S"),
    "archivo.importar": ("Importar", "Ctrl+I"),
    "archivo.exportar_video": ("Exportar video", "Ctrl+E"),
    "archivo.exportar_cuadro": ("Exportar cuadro", "Ctrl+Shift+E"),
    "archivo.salir": ("Salir", "Ctrl+Q"),

    "editar.deshacer": ("Deshacer", "Ctrl+Z"),
    "editar.rehacer": ("Rehacer", "Ctrl+Shift+Z"),
    "editar.cortar": ("Cortar en el playhead", "Ctrl+K"),
    "editar.duplicar": ("Duplicar", "Ctrl+D"),
    "editar.eliminar": ("Eliminar", "Del"),
    "editar.eliminar_hueco": ("Eliminar y cerrar hueco", "Shift+Del"),
    "editar.atajos": ("Atajos de teclado", "Ctrl+/"),

    "herramienta.seleccion": ("Herramienta de selección", "V"),
    "herramienta.navaja": ("Herramienta navaja", "C"),

    "clip.fundir": ("Fundir entrada y salida", "Ctrl+Shift+D"),
    "clip.transicion": ("Transición cruzada", "Ctrl+Shift+A"),
    "clip.congelar": ("Congelar cuadro", "Ctrl+Shift+F"),
    "clip.keyframe": ("Poner keyframe de todo", "Ctrl+Shift+K"),

    "capa.pip": ("Cuadro dentro de cuadro", "Ctrl+Shift+P"),

    "insertar.texto": ("Insertar texto", "Ctrl+T"),
    "insertar.subtitulo": ("Insertar subtítulo", "Ctrl+Shift+T"),
    "insertar.imagen": ("Insertar imagen", "Ctrl+Shift+I"),

    "reproducir.play": ("Reproducir / pausar", "Space"),
    "reproducir.lento": ("Más lento", "J"),
    "reproducir.normal": ("Velocidad normal", "K"),
    "reproducir.rapido": ("Más rápido", "Shift+L"),
    "reproducir.repetir": ("Repetir", "L"),

    "navegar.cuadro_atras": ("Cuadro anterior", "Left"),
    "navegar.cuadro_adelante": ("Cuadro siguiente", "Right"),
    "navegar.segundo_atras": ("Un segundo atrás", "Shift+Left"),
    "navegar.segundo_adelante": ("Un segundo adelante", "Shift+Right"),
    "navegar.diez_atras": ("Diez segundos atrás", "Ctrl+Left"),
    "navegar.diez_adelante": ("Diez segundos adelante", "Ctrl+Right"),
    "navegar.inicio": ("Ir al inicio", "Home"),
    "navegar.final": ("Ir al final", "End"),

    "marcar.entrada": ("Marcar entrada", "I"),
    "marcar.salida": ("Marcar salida", "O"),
    "marcar.quitar": ("Quitar marcas", "Ctrl+Shift+X"),
    "marcar.marcador": ("Poner marcador", "M"),
    "marcar.marcador_nombre": ("Marcador con nombre", "Shift+M"),
    "marcar.siguiente": ("Marcador siguiente", "Shift+Down"),
    "marcar.anterior": ("Marcador anterior", "Shift+Up"),
    "marcar.borrar": ("Borrar marcadores", "Ctrl+Shift+M"),
    "marcar.ir_entrada": ("Ir a la entrada", "Shift+I"),
    "marcar.ir_salida": ("Ir a la salida", "Shift+O"),

    "ver.pantalla_completa": ("Pantalla completa", "F"),
    "ver.ajustar": ("Ajustar timeline", "Shift+Z"),
}


# --- dónde se guarda ------------------------------------------------------

def config_dir() -> Path:
    """La carpeta de configuración del sistema, o `VORTEX_CONFIG_DIR`.

    La variable existe para las pruebas: sin ella, el banco reescribiría los
    atajos reales del usuario.
    """
    propia = os.environ.get("VORTEX_CONFIG_DIR")
    if propia:
        return Path(propia)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "VortexStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "VortexStudio"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vortex-studio"


def shortcuts_path() -> Path:
    return config_dir() / "atajos.json"


# --- teclas ---------------------------------------------------------------

def label(clave: str) -> str:
    return DEFAULTS[clave][0] if clave in DEFAULTS else clave


def group(clave: str) -> str:
    return GROUPS.get(clave.split(".", 1)[0], "")


def normalize(texto) -> str | None:
    """La tecla en texto portable ("Ctrl+K"), "" si va vacía, None si no se entiende.

    Se guarda en texto portable y no como la muestra el sistema: en Mac
    "Ctrl" se ve como ⌘, y un archivo de atajos tiene que servir igual en
    las tres plataformas.
    """
    if not isinstance(texto, str):
        return None
    texto = texto.strip()
    if not texto:
        return ""
    secuencia = QKeySequence(texto, PORTABLE)
    if secuencia.isEmpty() or secuencia.count() != 1:
        return None
    if secuencia[0].key() in (Qt.Key_unknown, 0):
        return None
    return secuencia.toString(PORTABLE)


def uses_altgr(tecla: str) -> bool:
    """¿Lleva Ctrl y Alt juntos? En teclado latinoamericano eso es AltGr."""
    secuencia = QKeySequence(tecla, PORTABLE)
    if secuencia.isEmpty():
        return False
    mods = secuencia[0].keyboardModifiers()
    return bool(mods & Qt.ControlModifier) and bool(mods & Qt.AltModifier)


def defaults() -> dict[str, str]:
    return {clave: normalize(tecla) or "" for clave, (_, tecla) in DEFAULTS.items()}


def validate(pedidos: dict) -> tuple[dict[str, str], list[str]]:
    """Mezcla lo que pidió el usuario con los de fábrica, sin dejar basura.

    Devuelve el mapa completo —todas las claves, en el orden de los menús— y
    la lista de lo que no se pudo aplicar, redactada para el usuario.

    Lo pedido por el usuario va primero: si pone `C` en otra acción, la
    navaja se queda sin tecla, porque fue una decisión explícita. Si dos
    acciones pedidas chocan, gana la primera y se avisa.
    """
    problemas: list[str] = []
    elegidos: dict[str, str] = {}

    for clave, texto in (pedidos or {}).items():
        if clave not in DEFAULTS:
            problemas.append(f"«{clave}» no es ninguna acción: se ignoró.")
            continue
        tecla = normalize(texto)
        if tecla is None:
            problemas.append(f"«{label(clave)}»: no entiendo la tecla «{texto}». "
                             f"Se quedó la de siempre.")
            continue
        if tecla and uses_altgr(tecla):
            problemas.append(f"«{label(clave)}»: {tecla} lleva Ctrl+Alt, que en teclado "
                             f"latinoamericano es AltGr — escribir una @ lo dispararía. "
                             f"Se quedó la de siempre.")
            continue
        elegidos[clave] = tecla

    final: dict[str, str] = {}
    ocupadas: dict[str, str] = {}
    rechazados: set[str] = set()

    for clave, tecla in elegidos.items():
        if tecla and tecla in ocupadas:
            problemas.append(f"«{label(clave)}» y «{label(ocupadas[tecla])}» piden "
                             f"{tecla}. Se quedó «{label(ocupadas[tecla])}».")
            rechazados.add(clave)
            continue
        final[clave] = tecla
        if tecla:
            ocupadas[tecla] = clave

    fabrica = defaults()
    for clave in DEFAULTS:
        if clave in final:
            continue
        tecla = fabrica[clave]
        if tecla and tecla in ocupadas:
            if clave not in rechazados:
                problemas.append(f"«{label(clave)}» quedó sin atajo: {tecla} ahora "
                                 f"es de «{label(ocupadas[tecla])}».")
            tecla = ""
        final[clave] = tecla
        if tecla:
            ocupadas[tecla] = clave

    return {clave: final[clave] for clave in DEFAULTS}, problemas


# --- archivo --------------------------------------------------------------

def load_shortcuts(path: str | Path | None = None) -> tuple[dict[str, str], list[str]]:
    ruta = Path(path) if path else shortcuts_path()
    if not ruta.exists():
        return defaults(), []

    dañado = [f"El archivo de atajos ({ruta}) está dañado: se usaron los de siempre."]
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults(), dañado

    pedidos = datos.get("atajos") if isinstance(datos, dict) else None
    if not isinstance(pedidos, dict):
        return defaults(), dañado
    return validate(pedidos)


def save_shortcuts(mapping: dict[str, str], path: str | Path | None = None) -> Path:
    """Guarda el mapa completo, no solo lo que cambió.

    Completo porque así el archivo sirve también de referencia: quien lo
    abra a mano ve todas las acciones y sus teclas, no un par de líneas
    sueltas. Se escribe a un temporal y se renombra.
    """
    ruta = Path(path) if path else shortcuts_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fabrica = defaults()
    contenido = {
        "version": FILE_VERSION,
        "atajos": {clave: mapping.get(clave, fabrica[clave]) for clave in DEFAULTS},
    }
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, ruta)
    return ruta


# --- el editor ------------------------------------------------------------

class ShortcutsDialog(QDialog):
    """Tabla de acciones con su tecla, un buscador, y nada más.

    Se guarda solo si todo el mapa es válido. Si dos acciones quedan con la
    misma tecla no se "arregla" solo: se dice cuáles chocan y se deja que el
    usuario decida cuál se la queda.
    """

    def __init__(self, parent, actuales: dict[str, str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Atajos de teclado")
        self.resize(580, 640)
        self.mapping = dict(actuales)

        self._buscar = QLineEdit()
        self._buscar.setPlaceholderText("Buscar acción o tecla…")
        self._buscar.textChanged.connect(self._filtrar)

        self._tabla = QTableWidget(len(DEFAULTS), 3)
        self._tabla.setHorizontalHeaderLabels(["Grupo", "Acción", "Atajo"])
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setSelectionMode(QTableWidget.NoSelection)
        self._tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self._edits: dict[str, QKeySequenceEdit] = {}
        for fila, clave in enumerate(DEFAULTS):
            for columna, texto in ((0, group(clave)), (1, label(clave))):
                item = QTableWidgetItem(texto)
                item.setFlags(Qt.ItemIsEnabled)
                self._tabla.setItem(fila, columna, item)
            edit = QKeySequenceEdit(QKeySequence(actuales.get(clave, ""), PORTABLE))
            if hasattr(edit, "setMaximumSequenceLength"):
                edit.setMaximumSequenceLength(1)
            if hasattr(edit, "setClearButtonEnabled"):
                edit.setClearButtonEnabled(True)
            self._tabla.setCellWidget(fila, 2, edit)
            self._edits[clave] = edit

        self._problemas = QLabel()
        self._problemas.setWordWrap(True)
        self._problemas.setStyleSheet("color:#e0574a;")

        nota = QLabel("Clic en un atajo y presiona la tecla nueva. Nada con Ctrl+Alt: "
                      "en teclado latinoamericano es AltGr.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#7d838c; font-size:11px;")

        restablecer = QPushButton("Restablecer todo")
        restablecer.clicked.connect(self.reset_defaults)

        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)

        abajo = QHBoxLayout()
        abajo.addWidget(restablecer)
        abajo.addStretch(1)
        abajo.addWidget(botones)

        layout = QVBoxLayout(self)
        layout.addWidget(self._buscar)
        layout.addWidget(self._tabla, 1)
        layout.addWidget(nota)
        layout.addWidget(self._problemas)
        layout.addLayout(abajo)

    def values(self) -> dict[str, str]:
        return {clave: edit.keySequence().toString(PORTABLE)
                for clave, edit in self._edits.items()}

    def set_value(self, clave: str, tecla: str) -> None:
        self._edits[clave].setKeySequence(QKeySequence(tecla, PORTABLE))

    def reset_defaults(self) -> None:
        for clave, tecla in defaults().items():
            self.set_value(clave, tecla)
        self._problemas.clear()

    def apply(self) -> bool:
        """Valida, y si todo está en orden guarda. Devuelve si guardó."""
        mapping, problemas = validate(self.values())
        if problemas:
            self._problemas.setText("\n".join(problemas))
            return False
        save_shortcuts(mapping)
        self.mapping = mapping
        self._problemas.clear()
        return True

    def visible_keys(self) -> list[str]:
        return [clave for fila, clave in enumerate(DEFAULTS)
                if not self._tabla.isRowHidden(fila)]

    def _aceptar(self) -> None:
        if self.apply():
            self.accept()

    def _filtrar(self, texto: str) -> None:
        buscado = texto.strip().lower()
        for fila, clave in enumerate(DEFAULTS):
            tecla = self._edits[clave].keySequence().toString(PORTABLE).lower()
            coincide = (not buscado or buscado in label(clave).lower()
                        or buscado in group(clave).lower() or buscado in tecla)
            self._tabla.setRowHidden(fila, not coincide)
