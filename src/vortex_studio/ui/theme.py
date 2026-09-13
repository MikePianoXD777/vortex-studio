"""Colores y letras del diseño de la beta.

Salen del diseño que Mike hizo en Claude Design: tarjetas casi negras con
borde tenue, acento blanco y números en monoespaciada. Viven aquí para que
cada zona tome los mismos valores y no un gris parecido.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

FONDO = "#0b0b0c"
TARJETA = "#111113"
CAMPO = "#17171a"
BORDE = "#222225"
BORDE_FUERTE = "#2e2e33"
PILDORA = "#26262a"
PILDORA_HOVER = "#1c1c1f"
TEXTO = "#e6e6e6"
TENUE = "#8a8a8f"
MUY_TENUE = "#5c5c62"
APAGADO = "#46464b"
ACENTO = "#ffffff"
SOBRE_ACENTO = "#0b0b0c"
PLAYHEAD = "#e5484d"

RADIO_TARJETA = 12


def _flecha() -> str:
    """La flechita de los combos, como archivo SVG.

    Una hoja de estilo de Qt solo acepta la flecha como imagen de un archivo;
    el truco de dibujarla con bordes salía como una rayita.
    """
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
           f'<path d="M2 3.5 L5 6.5 L8 3.5" fill="none" stroke="{TENUE}" stroke-width="1.4" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    ruta = Path(tempfile.gettempdir()) / "vortex-studio-flecha.svg"
    try:
        if not ruta.exists() or ruta.read_text() != svg:
            ruta.write_text(svg)
    except OSError:
        return ""
    return ruta.as_posix()


FLECHA = _flecha()
ARROW_RULE = (f"image: url({FLECHA}); width: 10px; height: 10px; margin-right: 8px; "
              "border: none;")
MONO = "'JetBrains Mono', 'DejaVu Sans Mono', 'Consolas', monospace"
MONO_FAMILIAS = ["JetBrains Mono", "DejaVu Sans Mono", "Consolas", "monospace"]

PILL_STYLE = f"""
QToolButton {{
    background: transparent; color: {TENUE}; border: none;
    border-radius: 8px; padding: 5px 11px; font-size: 12px;
}}
QToolButton:hover {{ color: {TEXTO}; background: {PILDORA_HOVER}; }}
QToolButton:checked {{ color: {TEXTO}; background: {PILDORA}; }}
QToolButton:disabled {{ color: {APAGADO}; background: transparent; }}
"""

CARD_STYLE = f"""
#tarjeta {{
    background: {TARJETA}; border: 1px solid {BORDE}; border-radius: {RADIO_TARJETA}px;
}}
"""

# El tema de toda la ventana. Los diálogos lo heredan por ser hijos suyos.
WINDOW_STYLE = f"""
QMainWindow, QDialog {{ background: {FONDO}; color: {TEXTO}; }}
QMainWindow::separator {{ background: transparent; width: 8px; height: 8px; }}
QWidget {{ color: {TEXTO}; }}
QToolTip {{
    background: {CAMPO}; color: {TEXTO}; border: 1px solid {BORDE_FUERTE};
    border-radius: 6px; padding: 4px 8px;
}}

QMenuBar {{ background: transparent; color: {TENUE}; font-size: 13px; }}
QMenuBar::item {{ background: transparent; padding: 5px 9px; border-radius: 6px; }}
QMenuBar::item:selected, QMenuBar::item:pressed {{ background: {PILDORA}; color: {TEXTO}; }}
QMenu {{
    background: {CAMPO}; color: {TEXTO}; border: 1px solid {BORDE_FUERTE};
    border-radius: 10px; padding: 5px;
}}
QMenu::item {{ padding: 6px 26px 6px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {PILDORA}; }}
QMenu::item:disabled {{ color: {APAGADO}; }}
QMenu::separator {{ height: 1px; background: {BORDE}; margin: 5px 8px; }}

QPushButton {{
    background: {CAMPO}; color: {TEXTO}; border: 1px solid {BORDE};
    border-radius: 8px; padding: 6px 12px;
}}
QPushButton:hover {{ background: {PILDORA}; }}
QPushButton:pressed {{ background: {PILDORA_HOVER}; }}
QPushButton:checked {{ background: {ACENTO}; color: {SOBRE_ACENTO}; }}
QPushButton:disabled {{ color: {APAGADO}; background: {TARJETA}; }}
QPushButton#primario {{
    background: {ACENTO}; color: {SOBRE_ACENTO}; border: none; font-weight: 600;
    padding: 7px 16px;
}}
QPushButton#primario:hover {{ background: #dcdcdc; }}

QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
QFontComboBox, QListWidget, QTreeWidget, QTableWidget {{
    background: {CAMPO}; color: {TEXTO}; border: 1px solid {BORDE};
    border-radius: 8px; padding: 5px 8px;
    selection-background-color: {PILDORA}; selection-color: {TEXTO};
}}
QComboBox:hover, QLineEdit:hover {{ border-color: {BORDE_FUERTE}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {MUY_TENUE};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ {ARROW_RULE} }}
QComboBox QAbstractItemView {{
    background: {CAMPO}; color: {TEXTO}; border: 1px solid {BORDE_FUERTE};
    selection-background-color: {PILDORA}; outline: none; padding: 4px;
}}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {APAGADO};
}}
QCheckBox, QRadioButton {{ color: {TENUE}; spacing: 7px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid {BORDE_FUERTE}; background: {CAMPO};
}}
QCheckBox::indicator:checked {{ background: {ACENTO}; border-color: {ACENTO}; }}
QLabel {{ background: transparent; }}
QGroupBox {{
    border: 1px solid {BORDE}; border-radius: 10px; margin-top: 14px; padding-top: 6px;
    color: {TENUE};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}

QProgressBar {{
    background: {CAMPO}; border: none; border-radius: 3px; height: 6px;
    color: transparent;
}}
QProgressBar::chunk {{ background: {ACENTO}; border-radius: 3px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {BORDE_FUERTE}; border-radius: 3px; min-height: 24px; min-width: 24px;
}}
QScrollBar::handle:hover {{ background: {MUY_TENUE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: transparent; }}
QStatusBar {{
    background: {FONDO}; color: {MUY_TENUE}; font-family: {MONO}; font-size: 11px;
}}
QStatusBar::item {{ border: none; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {TENUE}; padding: 5px 11px; border-radius: 8px;
}}
QTabBar::tab:selected {{ background: {PILDORA}; color: {TEXTO}; }}
QDockWidget {{ color: {TENUE}; }}
"""

SLIDER_STYLE = f"""
QSlider {{ background: transparent; min-height: 16px; }}
QSlider::groove:horizontal {{ height: 2px; background: {BORDE_FUERTE}; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: {TENUE}; border-radius: 1px; }}
QSlider::handle:horizontal {{
    width: 12px; height: 12px; margin: -5px 0; background: {ACENTO}; border-radius: 6px;
}}
QSlider::sub-page:horizontal:disabled {{ background: {BORDE_FUERTE}; }}
QSlider::handle:horizontal:disabled {{ background: {APAGADO}; }}
"""
