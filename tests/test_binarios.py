"""Lo que hace falta para publicar ejecutables: ícono, prueba de humo e instaladores."""

import importlib.util
import os
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

import vortex_studio
from vortex_studio import app as app_module

RAIZ = Path(__file__).resolve().parents[1]
ASSETS = RAIZ / "src" / "vortex_studio" / "assets"
LINUX = RAIZ / "empaquetado" / "linux"

necesita_bash = pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"),
                                   reason="los scripts de Linux necesitan bash")


def _iconos():
    spec = importlib.util.spec_from_file_location("iconos", RAIZ / "empaquetado" / "iconos.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# --- el ícono ---------------------------------------------------------------

@pytest.mark.parametrize("lado", _iconos().TAMANOS_PNG)
def test_cada_png_tiene_su_tamano(qapp, lado):
    imagen = QImage(str(ASSETS / f"vortex-studio-{lado}.png"))
    assert not imagen.isNull()
    assert (imagen.width(), imagen.height()) == (lado, lado)


def test_el_png_tiene_el_logo_blanco_al_centro(qapp):
    imagen = QImage(str(ASSETS / "vortex-studio-256.png"))
    assert QColor(imagen.pixel(90, 128)).lightness() > 240     # cuadro blanco
    assert QColor(imagen.pixel(128, 128)).lightness() < 40     # el play recortado
    assert QColor.fromRgba(imagen.pixel(0, 0)).alpha() == 0    # esquina transparente


def test_el_ico_trae_varios_tamanos(qapp):
    datos = (ASSETS / "vortex-studio.ico").read_bytes()
    reservado, tipo, cuantos = struct.unpack("<HHH", datos[:6])
    assert (reservado, tipo) == (0, 1)
    assert cuantos == len(_iconos().TAMANOS_ICO)
    assert not QImage(str(ASSETS / "vortex-studio.ico")).isNull()


def test_el_ico_apunta_bien_a_cada_imagen(qapp):
    modulo = _iconos()
    imagenes = {16: b"\x89PNG-a", 256: b"\x89PNG-bbbb"}
    datos = modulo.ico(imagenes)
    for i, (lado, contenido) in enumerate(sorted(imagenes.items())):
        ancho, _, _, _, _, _, tam, desde = struct.unpack("<BBBBHHII", datos[6 + 16 * i:22 + 16 * i])
        assert ancho == (0 if lado == 256 else lado)
        assert datos[desde:desde + tam] == contenido


def test_el_svg_es_valido():
    raiz = ET.parse(ASSETS / "vortex-studio.svg").getroot()
    assert raiz.get("viewBox") == "0 0 512 512"
    assert len(list(raiz)) == 3


def test_la_ventana_usa_el_icono(qapp):
    icono = app_module.app_icon()
    assert not icono.isNull()
    assert any(s.width() >= 256 for s in icono.availableSizes())


def test_el_icono_viaja_en_el_paquete():
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert 'vortex_studio = ["assets/*"]' in texto
    receta = (RAIZ / "vortex-studio.spec").read_text(encoding="utf-8")
    assert '("src/vortex_studio/assets", "vortex_studio/assets")' in receta
    assert 'icon="src/vortex_studio/assets/vortex-studio.ico"' in receta


# --- la prueba de humo ------------------------------------------------------

def test_la_prueba_de_humo_pasa(qapp):
    assert app_module.smoke_test(qapp) == 0


def test_la_prueba_de_humo_avisa_y_escribe_el_error(qapp, monkeypatch, tmp_path):
    import vortex_studio.ui.main_window as mw

    class Rota:
        def __init__(self):
            raise RuntimeError("falta una biblioteca")

    bitacora = tmp_path / "humo.log"
    monkeypatch.setattr(mw, "MainWindow", Rota)
    monkeypatch.setenv("VORTEX_SMOKE_LOG", str(bitacora))
    assert app_module.smoke_test(qapp) == 1
    assert "falta una biblioteca" in bitacora.read_text(encoding="utf-8")


def test_la_prueba_de_humo_sin_bitacora_tambien_falla(qapp, monkeypatch):
    import vortex_studio.media as media

    monkeypatch.delenv("VORTEX_SMOKE_LOG", raising=False)
    monkeypatch.setattr(media, "HAS_PYAV", False)
    assert app_module.smoke_test(qapp) == 1


def test_main_con_la_bandera_no_abre_nada(qapp):
    assert app_module.main(["vortex-studio", app_module.SMOKE_FLAG]) == 0
    assert qapp.desktopFileName() == "vortex-studio"


# --- pantalla de inicio y splash con el diseño nuevo -------------------------

def test_el_splash_usa_los_colores_nuevos(qapp):
    from vortex_studio.ui import splash, theme

    assert splash.ACCENT.name() == theme.ACENTO
    pantalla = splash.SplashScreen("0.1.0b1")
    imagen = pantalla.pixmap().toImage()
    medio = QColor(imagen.pixel(imagen.width() // 2, imagen.height() - 20))
    assert medio.lightness() < 30
    pantalla.close()


def test_el_launcher_usa_los_colores_nuevos(qapp):
    from vortex_studio.ui import launcher, theme

    assert launcher.BG.name() == theme.FONDO
    assert launcher.ACCENT.name() == theme.ACENTO
    ventana = launcher.Launcher("0.1.0b1")
    assert theme.FONDO in ventana.styleSheet()
    ventana.close()


def test_la_tarjeta_del_launcher_se_pinta(qapp):
    from vortex_studio.ui import launcher, theme

    tarjeta = launcher.ModeCard(launcher.VIDEO, "Video", "Editor")
    imagen = tarjeta.grab().toImage()
    assert QColor(imagen.pixel(20, launcher.CARD_H // 2)).name() == theme.TARJETA


def test_el_tema_no_carga_el_editor():
    """El splash tiene que salir antes de la carga pesada, no después."""
    codigo = ("import sys, vortex_studio.ui.theme, vortex_studio.ui.splash, "
              "vortex_studio.ui.launcher; print('vortex_studio.ui.main_window' in sys.modules)")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, check=True)
    assert salida.stdout.strip() == "False"


def test_la_ventana_se_sigue_importando_igual():
    from vortex_studio.ui import MainWindow
    from vortex_studio.ui.main_window import MainWindow as directa

    assert MainWindow is directa


def test_un_nombre_que_no_existe_sigue_fallando():
    import vortex_studio.ui as ui

    with pytest.raises(AttributeError):
        ui.NoExiste  # noqa: B018


# --- la versión ---------------------------------------------------------------

def test_es_la_beta():
    assert vortex_studio.__version__.startswith("0.1.0b")
    assert "Development Status :: 4 - Beta" in (RAIZ / "pyproject.toml").read_text(
        encoding="utf-8")


def test_la_documentacion_no_tiene_huecos():
    for nombre in ("README.md", "README.en.md", "CHANGELOG.md", "CHANGELOG.en.md"):
        assert "@PRUEBAS@" not in (RAIZ / nombre).read_text(encoding="utf-8"), nombre


def test_el_readme_nombra_los_archivos_que_se_publican():
    version = vortex_studio.__version__
    for nombre in ("README.md", "README.en.md"):
        texto = (RAIZ / nombre).read_text(encoding="utf-8")
        for archivo in (f"VortexStudio-{version}-windows-x64-instalador.exe",
                        f"VortexStudio-{version}-windows-x64-portable.zip",
                        f"VortexStudio-{version}-linux-x86_64.tar.gz"):
            assert archivo in texto, (nombre, archivo)


# --- la entrada del menú de Linux ------------------------------------------

def _entrada():
    claves = {}
    for linea in (LINUX / "vortex-studio.desktop").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.startswith("["):
            clave, valor = linea.split("=", 1)
            claves[clave] = valor
    return claves


def test_la_entrada_es_una_aplicacion():
    claves = _entrada()
    assert claves["Type"] == "Application" and claves["Terminal"] == "false"
    assert claves["Name"] == "Vortex Studio"


def test_la_entrada_usa_el_icono_y_la_clase_de_ventana():
    claves = _entrada()
    assert claves["Icon"] == "vortex-studio"
    assert claves["StartupWMClass"] == "vortex-studio"


def test_la_entrada_va_en_la_categoria_de_video():
    categorias = _entrada()["Categories"].split(";")
    assert "AudioVideo" in categorias and "Video" in categorias
    assert "@EXEC@" in _entrada()["Exec"]


# --- instalar y desinstalar en Linux -----------------------------------------

def _paquete(carpeta: Path) -> Path:
    """Un paquete de mentiras con la misma forma que el .tar.gz."""
    paquete = carpeta / "paquete"
    (paquete / "vortex-studio" / "_internal").mkdir(parents=True)
    programa = paquete / "vortex-studio" / "vortex-studio"
    programa.write_text("#!/bin/sh\necho hola\n")
    programa.chmod(0o755)
    (paquete / "vortex-studio" / "_internal" / "lib.so").write_text("nueva")
    (paquete / "iconos").mkdir()
    for lado in (48, 256):
        shutil.copy(ASSETS / f"vortex-studio-{lado}.png", paquete / "iconos")
    for archivo in ("instalar.sh", "desinstalar.sh", "vortex-studio.desktop"):
        shutil.copy(LINUX / archivo, paquete / archivo)
    return paquete


def _correr(script: Path, casa: Path):
    entorno = {k: v for k, v in os.environ.items() if k != "XDG_DATA_HOME"}
    entorno["HOME"] = str(casa)
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, env=entorno)


@necesita_bash
def test_instalar_pone_programa_menu_icono_y_comando(tmp_path):
    casa = tmp_path / "casa de prueba"          # con espacio, a propósito
    casa.mkdir()
    paquete = _paquete(tmp_path)
    salida = _correr(paquete / "instalar.sh", casa)
    assert salida.returncode == 0, salida.stderr

    programa = casa / ".local/opt/vortex-studio/vortex-studio"
    assert os.access(programa, os.X_OK)
    enlace = casa / ".local/bin/vortex-studio"
    assert enlace.is_symlink() and enlace.resolve() == programa.resolve()
    assert (casa / ".local/share/icons/hicolor/256x256/apps/vortex-studio.png").exists()
    assert (casa / ".local/share/icons/hicolor/48x48/apps/vortex-studio.png").exists()

    entrada = (casa / ".local/share/applications/vortex-studio.desktop").read_text()
    assert f'Exec="{programa}"' in entrada and "@EXEC@" not in entrada


@necesita_bash
def test_reinstalar_no_deja_archivos_viejos(tmp_path):
    casa = tmp_path / "casa"
    casa.mkdir()
    paquete = _paquete(tmp_path)
    assert _correr(paquete / "instalar.sh", casa).returncode == 0
    vieja = casa / ".local/opt/vortex-studio/_internal/vieja.so"
    vieja.write_text("de la versión pasada")
    assert _correr(paquete / "instalar.sh", casa).returncode == 0
    assert not vieja.exists()
    assert (casa / ".local/opt/vortex-studio/_internal/lib.so").read_text() == "nueva"


@necesita_bash
def test_desinstalar_quita_todo_menos_los_proyectos(tmp_path):
    casa = tmp_path / "casa"
    casa.mkdir()
    paquete = _paquete(tmp_path)
    assert _correr(paquete / "instalar.sh", casa).returncode == 0
    datos = casa / ".local/share/vortex-studio/autoguardado.vortex"
    datos.parent.mkdir(parents=True)
    datos.write_text("{}")

    salida = _correr(casa / ".local/opt/vortex-studio/desinstalar.sh", casa)
    assert salida.returncode == 0, salida.stderr
    assert not (casa / ".local/opt/vortex-studio").exists()
    assert not (casa / ".local/bin/vortex-studio").exists()
    assert not (casa / ".local/share/applications/vortex-studio.desktop").exists()
    assert not list((casa / ".local/share/icons").rglob("vortex-studio.png"))
    assert datos.exists()


@necesita_bash
def test_instalar_sin_programa_avisa(tmp_path):
    casa = tmp_path / "casa"
    casa.mkdir()
    paquete = _paquete(tmp_path)
    shutil.rmtree(paquete / "vortex-studio")
    salida = _correr(paquete / "instalar.sh", casa)
    assert salida.returncode == 1 and "No encuentro el programa" in salida.stderr


@necesita_bash
def test_desinstalar_no_borra_un_comando_ajeno(tmp_path):
    casa = tmp_path / "casa"
    (casa / ".local/bin").mkdir(parents=True)
    ajeno = casa / ".local/bin/vortex-studio"
    ajeno.write_text("otro programa con el mismo nombre")
    assert _correr(LINUX / "desinstalar.sh", casa).returncode == 0
    assert ajeno.exists()


# --- el .tar.gz -------------------------------------------------------------------

def _repo_de_mentiras(carpeta: Path, con_dist: bool = True) -> Path:
    repo = carpeta / "repo"
    shutil.copytree(RAIZ / "empaquetado", repo / "empaquetado")
    (repo / "src/vortex_studio").mkdir(parents=True)
    shutil.copy(RAIZ / "src/vortex_studio/__init__.py", repo / "src/vortex_studio")
    shutil.copytree(ASSETS, repo / "src/vortex_studio/assets")
    shutil.copy(RAIZ / "LICENSE", repo)
    if con_dist:
        programa = repo / "dist/vortex-studio/vortex-studio"
        programa.parent.mkdir(parents=True)
        programa.write_text("#!/bin/sh\n")
        programa.chmod(0o755)
    return repo


@necesita_bash
def test_empaquetar_arma_el_tar_con_instalador_e_iconos(tmp_path):
    repo = _repo_de_mentiras(tmp_path)
    salida = subprocess.run(["bash", str(repo / "empaquetado/linux/empaquetar.sh"), "9.9.9"],
                            capture_output=True, text=True)
    assert salida.returncode == 0, salida.stderr
    tar = repo / "dist/VortexStudio-9.9.9-linux-x86_64.tar.gz"
    with tarfile.open(tar) as archivo:
        nombres = archivo.getnames()
        instalador = archivo.getmember("VortexStudio-9.9.9-linux-x86_64/instalar.sh")
        assert instalador.mode & stat.S_IXUSR
    base = "VortexStudio-9.9.9-linux-x86_64"
    for esperado in ("vortex-studio/vortex-studio", "desinstalar.sh", "vortex-studio.desktop",
                     "LEEME.txt", "LICENSE", "iconos/vortex-studio-512.png"):
        assert f"{base}/{esperado}" in nombres


@necesita_bash
def test_empaquetar_sin_version_usa_la_del_codigo(tmp_path):
    repo = _repo_de_mentiras(tmp_path)
    salida = subprocess.run(["bash", str(repo / "empaquetado/linux/empaquetar.sh")],
                            capture_output=True, text=True)
    assert salida.returncode == 0, salida.stderr
    assert (repo / f"dist/VortexStudio-{vortex_studio.__version__}-linux-x86_64.tar.gz").exists()


@necesita_bash
def test_empaquetar_sin_compilar_avisa(tmp_path):
    repo = _repo_de_mentiras(tmp_path, con_dist=False)
    salida = subprocess.run(["bash", str(repo / "empaquetado/linux/empaquetar.sh")],
                            capture_output=True, text=True)
    assert salida.returncode == 1 and "construir.sh" in salida.stderr


# --- Windows y la compilación automática ---------------------------------------

def test_el_instalador_de_windows_va_al_menu_inicio():
    texto = (RAIZ / "empaquetado/windows/vortex-studio.iss").read_text(encoding="utf-8")
    assert '{group}\\Vortex Studio"; Filename: "{app}\\vortex-studio.exe"' in texto
    assert "PrivilegesRequired=lowest" in texto


def test_el_instalador_de_windows_esta_en_espanol_y_con_version():
    texto = (RAIZ / "empaquetado/windows/vortex-studio.iss").read_text(encoding="utf-8")
    assert "Languages\\Spanish.isl" in texto
    assert "OutputBaseFilename=VortexStudio-{#AppVersion}-windows-x64-instalador" in texto


def test_el_instalador_de_windows_usa_el_icono():
    texto = (RAIZ / "empaquetado/windows/vortex-studio.iss").read_text(encoding="utf-8")
    ruta = texto.split("SetupIconFile=")[1].splitlines()[0]
    assert (RAIZ / "empaquetado/windows" / ruta.replace("\\", "/")).resolve() == \
        (ASSETS / "vortex-studio.ico").resolve()


def _flujo() -> str:
    return (RAIZ / ".github/workflows/binarios.yml").read_text(encoding="utf-8")


def test_la_compilacion_corre_en_los_dos_sistemas():
    texto = _flujo()
    assert "runs-on: ubuntu-22.04" in texto and "runs-on: windows-latest" in texto


def test_la_compilacion_prueba_antes_de_subir():
    texto = _flujo()
    for trabajo in texto.split("\n  windows:")[0], texto.split("\n  windows:")[1]:
        assert trabajo.index("--smoke-test") < trabajo.index("gh release upload")


def test_la_maquina_de_linux_tiene_la_biblioteca_de_sonido():
    """Sin libpulse la prueba de humo truena al importar el reproductor de audio."""
    linux = _flujo().split("\n  windows:")[0]
    instalacion = next(l for l in linux.splitlines() if "apt-get install" in l)
    assert "libpulse0" in instalacion
    # El paso de la prueba, no la mención en el comentario de arriba del archivo.
    assert linux.index("libpulse0") < linux.index("run: ./dist/vortex-studio/vortex-studio --smoke-test")


def test_la_compilacion_corre_al_publicar():
    texto = _flujo()
    assert "release:\n    types: [published]" in texto
    assert "contents: write" in texto


# --- las bibliotecas de X11 que viajan en el paquete de Linux ---------------------

def _bibliotecas():
    spec = importlib.util.spec_from_file_location(
        "bibliotecas_linux", RAIZ / "empaquetado" / "bibliotecas_linux.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _carpeta_con(tmp_path, nombres):
    carpeta = tmp_path / "lib"
    carpeta.mkdir()
    for nombre in nombres:
        (carpeta / nombre).write_bytes(b"\x7fELF")
    return carpeta


def test_encuentra_las_bibliotecas_y_las_manda_junto_a_qt(tmp_path):
    modulo = _bibliotecas()
    carpeta = _carpeta_con(tmp_path, modulo.X11)
    binarios = modulo.binarios_x11(estricto=True, carpetas=[carpeta], plataforma="linux")
    assert [Path(ruta).name for ruta, _ in binarios] == list(modulo.X11)
    assert {destino for _, destino in binarios} == {"PySide6/Qt/lib"}


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="solo el paquete de Linux")
def test_el_destino_es_donde_vive_la_biblioteca_de_qt_que_las_pide():
    """Si PySide6 mueve sus bibliotecas, las copias quedarían donde nadie las busca."""
    import PySide6

    qt = Path(PySide6.__file__).parent
    pide = qt / Path(_bibliotecas().DESTINO).relative_to("PySide6") / "libQt6XcbQpa.so.6"
    assert pide.exists(), pide


@pytest.mark.skipif(not shutil.which("readelf") or not sys.platform.startswith("linux"),
                    reason="hace falta readelf")
def test_la_biblioteca_de_qt_solo_busca_en_su_carpeta():
    """Por eso las copias van ahí: RUNPATH `$ORIGIN` y ninguna otra ruta."""
    import PySide6

    qpa = Path(PySide6.__file__).parent / "Qt" / "lib" / "libQt6XcbQpa.so.6"
    salida = subprocess.run(["readelf", "-d", str(qpa)], capture_output=True, text=True,
                            env={**os.environ, "LC_ALL": "C"}, check=True).stdout
    assert "[$ORIGIN]" in salida
    assert "libxcb-cursor.so.0" in salida


def test_la_cursor_de_xcb_esta_en_la_lista():
    """La que Ubuntu 22.04 no instala sola y hace que Qt 6 no abra en X11."""
    assert "libxcb-cursor.so.0" in _bibliotecas().X11


def test_en_modo_estricto_una_que_falta_truena(tmp_path):
    modulo = _bibliotecas()
    carpeta = _carpeta_con(tmp_path, modulo.X11[1:])
    with pytest.raises(modulo.Falta, match="libxcb-cursor"):
        modulo.binarios_x11(estricto=True, carpetas=[carpeta], plataforma="linux")


def test_sin_modo_estricto_solo_avisa(tmp_path, capsys):
    modulo = _bibliotecas()
    carpeta = _carpeta_con(tmp_path, modulo.X11[1:])
    binarios = modulo.binarios_x11(estricto=False, carpetas=[carpeta], plataforma="linux")
    assert len(binarios) == len(modulo.X11) - 1
    assert "libxcb-cursor" in capsys.readouterr().out


def test_el_modo_estricto_sale_de_la_variable(tmp_path, monkeypatch):
    modulo = _bibliotecas()
    carpeta = _carpeta_con(tmp_path, [])
    monkeypatch.setenv("VORTEX_STRICT_BUNDLE", "1")
    with pytest.raises(modulo.Falta):
        modulo.binarios_x11(carpetas=[carpeta], plataforma="linux")


def test_en_windows_no_agrega_nada(tmp_path):
    assert _bibliotecas().binarios_x11(estricto=True, carpetas=[tmp_path], plataforma="win32") == []


def test_la_receta_usa_las_bibliotecas():
    receta = (RAIZ / "vortex-studio.spec").read_text(encoding="utf-8")
    assert "binaries=binarios_x11()," in receta


def _linux() -> str:
    return _flujo().split("\n  windows:")[0]


def test_la_compilacion_instala_y_exige_las_bibliotecas():
    linux = _linux()
    instalacion = linux[linux.index("libxcb-cursor0"):linux.index("pip install")]
    for paquete in ("libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1",
                    "libxcb-render-util0", "libxcb-util1", "libxkbcommon-x11-0", "xvfb"):
        assert paquete in instalacion
    compilar = linux[linux.index("- name: Compilar"):linux.index("- name: Prueba de humo")]
    assert 'VORTEX_STRICT_BUNDLE: "1"' in compilar


def test_la_compilacion_abre_en_x11_sin_las_del_sistema_antes_de_subir():
    linux = _linux()
    quitar = linux.index("dpkg -r --force-depends libxcb-cursor0")
    abrir = linux.index("QT_QPA_PLATFORM=xcb ./dist/vortex-studio/vortex-studio --smoke-test")
    assert quitar < abrir < linux.index("gh release upload")


def test_sin_tag_la_compilacion_no_toca_ninguna_release():
    texto = _flujo()
    assert "REF: ${{ github.event.release.tag_name || inputs.tag || github.sha }}" in texto
    assert texto.count("ref: ${{ env.REF }}") == 2
    for trabajo in texto.split("\n  windows:"):
        subir = trabajo[trabajo.index("- name: Subir a la release"):]
        assert subir.splitlines()[1].strip() == "if: env.TAG != ''"
        assert "if: env.TAG == ''" in subir and "actions/upload-artifact" in subir
