"""Banco de pruebas de Vortex Studio.

Genera su propio material con ffmpeg la primera vez y lo reutiliza, así que
no depende de que haya videos a la mano ni deja basura en el proyecto.

Todo corre sin mostrar ventanas (`offscreen`), por eso se puede ejecutar en
una terminal, por SSH o en un servidor sin pantalla.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Debe quedar puesto ANTES de que cualquier import cree la QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Las ondas de los videos de prueba van a una caché desechable: sin esto, el
# banco llenaría la carpeta de caché real del usuario.
os.environ.setdefault("VORTEX_CACHE_DIR", tempfile.mkdtemp(prefix="vortex-cache-"))

# Lo mismo con la configuración: sin esto, una prueba de atajos reescribiría
# los atajos reales del usuario.
os.environ.setdefault("VORTEX_CONFIG_DIR", tempfile.mkdtemp(prefix="vortex-config-"))

# Y con los datos: los autoguardados de las pruebas no deben ofrecérsele al
# usuario real la próxima vez que abra el editor.
os.environ.setdefault("VORTEX_DATA_DIR", tempfile.mkdtemp(prefix="vortex-datos-"))


def _ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


# En Windows suele venir como ffmpeg.exe y puede no estar en el PATH.
FFMPEG = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    """Material de prueba: video mudo, video con audio, audio suelto e imagen."""
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg en el PATH para generar el material de prueba")

    base = tmp_path_factory.mktemp("media")

    mudo = base / "mudo.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mudo))

    sonoro = base / "sonoro.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6,volume=12dB",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(sonoro))

    gris = base / "gris.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:size=160x120:rate=30:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "0", str(gris))

    logo = base / "logo.png"
    _ffmpeg("-f", "lavfi",
            "-i", "color=c=black:size=120x120,format=rgba,"
                  "geq=r=40:g=200:b=140:a='if(lt(hypot(X-60,Y-60),55),255,0)'",
            "-frames:v", "1", str(logo))

    tono = base / "tono.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=3,volume=12dB",
            "-ac", "2", str(tono))

    return {"mudo": mudo, "sonoro": sonoro, "gris": gris, "logo": logo,
            "tono": tono}


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from vortex_studio.app import _dark_palette

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    return app


@pytest.fixture
def ventana(qapp):
    """Una ventana limpia por prueba, cerrada al terminar.

    Se marca como guardada antes de cerrar porque `closeEvent` pregunta si
    hay cambios pendientes, y un diálogo modal colgaría la prueba.
    """
    from vortex_studio.ui import MainWindow

    w = MainWindow()
    w.resize(1200, 700)
    w.show()
    qapp.processEvents()
    yield w

    w._dirty = False
    w.close()
    qapp.processEvents()


@pytest.fixture
def secuencia():
    from vortex_studio.model import Sequence
    return Sequence.default()


@pytest.fixture(autouse=True)
def sin_dialogos_modales(monkeypatch, request):
    """Hace que un diálogo modal falle en vez de colgar la prueba.

    Un QMessageBox dentro de una prueba se queda esperando un clic que nunca
    llega: la prueba no falla, se congela, y de paso arrastra a todas las que
    vienen atrás. Ya pasó una vez con el aviso de la transición.

    Las pruebas que sí quieren verificar un diálogo pueden pedir el permiso
    marcándose con @pytest.mark.permite_dialogos.
    """
    if request.node.get_closest_marker("permite_dialogos"):
        return

    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    def prohibido(nombre):
        def _falla(*args, **kwargs):
            raise AssertionError(
                f"{nombre} abrió un diálogo modal durante la prueba. "
                f"Usa la barra de estado, o marca la prueba con "
                f"@pytest.mark.permite_dialogos.")
        return _falla

    for clase, metodos in (
        (QMessageBox, ("information", "warning", "critical", "question", "about")),
        (QInputDialog, ("getText", "getInt", "getDouble", "getItem")),
        (QFileDialog, ("getOpenFileName", "getSaveFileName", "getExistingDirectory")),
    ):
        for metodo in metodos:
            monkeypatch.setattr(clase, metodo,
                                staticmethod(prohibido(f"{clase.__name__}.{metodo}")),
                                raising=False)


def _girar(origen: Path, destino: Path, grados: int) -> bool:
    """Copia el video marcándolo para verse girado. Dice si lo logró.

    Cada ffmpeg lo pide a su manera, y el de la máquina de compilación no es
    el mismo que el de aquí: se intentan las dos y se comprueba que la marca
    haya quedado de verdad.
    """
    intentos = (
        ("-display_rotation", str(grados), "-i", str(origen), "-c", "copy", str(destino)),
        ("-i", str(origen), "-c", "copy", "-metadata:s:v:0", f"rotate={grados}", str(destino)),
    )
    for argumentos in intentos:
        destino.unlink(missing_ok=True)
        try:
            _ffmpeg(*argumentos)
        except subprocess.CalledProcessError:
            continue
        try:
            from vortex_studio.media.decoder import probe_media

            info = probe_media(destino)
            if (info.width, info.height) == (info.height, info.width) or info.width < info.height:
                return True
        except Exception:
            continue
    return False


@pytest.fixture(scope="session")
def dificil(tmp_path_factory) -> dict[str, Path]:
    """Material incómodo, del que sí hay en la calle.

    El banco pasaba con material demasiado cómodo —30 fps exactos, keyframes
    seguidos, 48 kHz— y por eso no vio la reproducción cortada de la beta.
    Aquí va lo que rompe cuentas: NTSC, keyframes lejanos, vertical, HEVC,
    44.1 kHz, resolución impar y un archivo que no empieza en cero.
    """
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg en el PATH para generar el material de prueba")

    base = tmp_path_factory.mktemp("dificil")

    # Como un celular: vertical, 29.97, keyframe cada 3 s, audio a 44.1 kHz.
    celular = base / "celular.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=270x480:rate=30000/1001:duration=5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5,volume=6dB",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "90", "-keyint_min", "90",
            "-sc_threshold", "0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-b:a", "96k", "-shortest", str(celular))

    # HEVC: lo que sale de un celular reciente o de una cámara moderna.
    hevc = base / "hevc.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=3",
            "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=none",
            "-pix_fmt", "yuv420p", "-tag:v", "hvc1", str(hevc))

    # Resolución impar: al exportar hay que emparejarla o H.264 truena.
    impar = base / "impar.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=321x181:rate=30:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(impar))

    # El tiempo del archivo no empieza en cero: pasa con material de cámara.
    corrido = base / "corrido.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-output_ts_offset", "3.5", str(corrido))

    # Audio suelto a 44.1 kHz y mono: el mezclador trabaja a 48 kHz estéreo.
    mono441 = base / "mono441.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=3,volume=6dB",
            "-ac", "1", "-ar", "44100", str(mono441))

    # Celular grabando vertical: la imagen va acostada con una marca de giro.
    # `-display_rotation` existe desde ffmpeg 6; las máquinas de compilación
    # traen la 4.4, así que hay que intentar también la forma vieja.
    rotado = base / "rotado.mp4"
    acostado = base / "acostado.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(acostado))
    if not _girar(acostado, rotado, 90):
        pytest.skip("Este ffmpeg no sabe marcar el giro de un video")

    # Cuadros que no van parejos: pasa con grabaciones de pantalla y celulares.
    vfr = base / "vfr.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=3",
            "-vf", "select='not(mod(n,3))+not(mod(n,7))'", "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(vfr))

    # Foto de celular: guardada acostada, con la marca EXIF que dice girarla.
    foto = base / "foto.jpg"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=1:duration=1",
            "-frames:v", "1", str(foto))
    foto_exif = base / "foto-vertical.jpg"
    foto_exif.write_bytes(_con_orientacion(foto.read_bytes(), 6))

    return {"celular": celular, "hevc": hevc, "impar": impar, "corrido": corrido,
            "mono441": mono441, "rotado": rotado, "acostado": acostado, "vfr": vfr,
            "foto": foto, "foto_exif": foto_exif}


def _con_orientacion(jpeg: bytes, valor: int = 6) -> bytes:
    """Le mete al JPEG una marca EXIF de orientación, como la de un celular."""
    import struct

    tiff = b"II" + struct.pack("<HI", 42, 8)
    tiff += (struct.pack("<H", 1)
             + struct.pack("<HHIHH", 0x0112, 3, 1, valor, 0)
             + struct.pack("<I", 0))
    app1 = b"Exif\x00\x00" + tiff
    segmento = b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    return jpeg[:2] + segmento + jpeg[2:]
