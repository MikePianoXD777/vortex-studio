"""Guardar y abrir proyectos."""

import json

import pytest

from vortex_studio.model import ColorAdjust, ImageOverlay, Sequence, Title
from vortex_studio.model.serialize import (
    FORMAT_VERSION,
    load_project,
    project_from_dict,
    save_project,
    sequence_from_dict,
    sequence_to_dict,
)
from vortex_studio.model.project import Project


@pytest.fixture
def poblada():
    s = Sequence.default()
    clip = s.video_tracks()[-1].append("/tmp/a.mp4", 5.0)
    clip.color = ColorAdjust(brightness=20, saturation=140)
    s.video_tracks()[0].add(ImageOverlay(start=1.0, duration=3.0,
                                         source="/tmp/l.png", scale=0.2, opacity=0.5))
    s.text_tracks()[0].add(Title(start=0.5, duration=2.0, text="Hola\nmundo",
                                 color="#ffcc00", background=True))
    s.audio_tracks()[0].append("/tmp/a.mp4", 5.0)
    return s


def test_ida_y_vuelta_identica(poblada):
    ida = sequence_to_dict(poblada)
    assert sequence_to_dict(sequence_from_dict(ida)) == ida


def test_conserva_los_detalles(poblada):
    r = sequence_from_dict(sequence_to_dict(poblada))

    assert r.video_tracks()[-1].clips[0].color.brightness == 20
    assert r.titles_at(1.0)[0].text == "Hola\nmundo"
    assert r.titles_at(1.0)[0].background is True
    assert r.overlays_at(2.0)[0].opacity == 0.5
    assert len(r.audio_tracks()[0].clips) == 1


def test_archivo_en_disco(tmp_path, poblada):
    proyecto = Project(name="prueba", sequences=[poblada])
    destino = save_project(proyecto, tmp_path / "p")

    assert destino.suffix == ".vortex"
    assert json.loads(destino.read_text(encoding="utf-8"))["formato"] \
        == FORMAT_VERSION

    vuelto = load_project(destino)
    assert vuelto.name == "prueba"
    assert sequence_to_dict(vuelto.active) == sequence_to_dict(poblada)


def test_rechaza_formato_mas_nuevo():
    with pytest.raises(ValueError, match="más nueva"):
        project_from_dict({"formato": 999, "sequences": []})


def test_proyecto_vacio_trae_secuencia():
    assert len(project_from_dict({"formato": 1}).active.tracks) == 6


def test_abre_proyectos_del_formato_viejo():
    """Un .vortex del formato 1 no traía máscara, fusión ni curva.

    Tiene que abrir igual y llenar esos campos con su valor neutro, no
    tronar ni dejarlos en `None`.
    """
    viejo = {
        "formato": 1,
        "name": "de antes",
        "sequences": [{
            "name": "S", "fps": 30.0, "width": 1920, "height": 1080,
            "tracks": [{"name": "V1", "kind": "video", "clips": [{
                "tipo": "clip", "source": "video.mp4", "start": 0.0,
                "duration": 2.0, "in_point": 0.0, "name": "v", "speed": 1.0,
                "fade_in": 0.0, "fade_out": 0.0, "gain": 1.0, "dissolve": 0.0,
                "color": {"brightness": 10, "contrast": 100,
                          "saturation": 100, "gamma": 100, "temperature": 0},
            }]}],
            "markers": [],
        }],
    }

    clip = project_from_dict(viejo).active.tracks[0].clips[0]
    assert clip.color.brightness == 10          # lo que sí traía se conserva
    assert clip.blend == "Normal"
    assert clip.mask.is_off
    assert clip.color.curves.is_neutral
    assert clip.color.vignette == 0
