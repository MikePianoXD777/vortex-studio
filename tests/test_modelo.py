"""El modelo: pistas, clips, tiempos. Sin Qt ni archivos."""

from vortex_studio.model import ANCHORS, Clip, ImageOverlay, Sequence, Title, timecode


def test_pistas_por_defecto(secuencia):
    assert [t.name for t in secuencia.tracks] == ["T1", "V2", "V1", "A1", "A2", "A3"]
    assert [t.name for t in secuencia.audio_tracks()] == ["A1", "A2", "A3"]
    assert [t.name for t in secuencia.video_tracks()] == ["V2", "V1"]


def test_clips_se_pegan_sin_hueco(secuencia):
    v1 = secuencia.video_tracks()[-1]
    v1.append("/tmp/a.mp4", 5.0)
    b = v1.append("/tmp/b.mp4", 3.0)
    assert b.start == 5.0
    assert secuencia.duration == 8.0


def test_tiempo_del_archivo_fuente():
    clip = Clip(source="/tmp/a.mp4", start=10.0, duration=5.0, in_point=2.0)
    # A los 12 s de la pista van 2 s dentro del clip, o sea 4 s del archivo.
    assert clip.source_time(12.0) == 4.0


def test_el_clip_de_arriba_gana(secuencia):
    v2, v1 = secuencia.video_tracks()
    v1.append("/tmp/abajo.mp4", 10.0)
    v2.add(Clip(source="/tmp/arriba.mp4", start=2.0, duration=3.0))
    assert secuencia.top_clip_at(1.0).name == "abajo"
    assert secuencia.top_clip_at(3.0).name == "arriba"


def test_una_imagen_no_se_confunde_con_video(secuencia):
    v2, v1 = secuencia.video_tracks()
    v1.append("/tmp/video.mp4", 10.0)
    v2.add(ImageOverlay(start=0.0, duration=5.0, source="/tmp/logo.png"))

    assert secuencia.top_clip_at(1.0).name == "video"   # el fondo sigue siendo el video
    assert len(secuencia.overlays_at(1.0)) == 1


def test_textos_activos_solo_en_su_rango(secuencia):
    secuencia.text_tracks()[0].add(Title(start=1.0, duration=2.0, text="hola"))
    assert secuencia.titles_at(0.5) == []
    assert len(secuencia.titles_at(1.5)) == 1
    assert secuencia.titles_at(3.5) == []


def test_timecode():
    assert timecode(0) == "00:00:00:00"
    assert timecode(3661.5, 30) == "01:01:01:15"
    assert timecode(-5) == "00:00:00:00"       # nunca negativo


def test_imantar_al_cuadro(secuencia):
    secuencia.fps = 30.0
    # Redondea al cuadro más cercano, no al anterior.
    assert abs(secuencia.snap_to_frame(1.004) - 1.0) < 1e-9
    assert abs(secuencia.snap_to_frame(1.030) - (31 / 30)) < 1e-9
    assert abs(secuencia.snap_to_frame(2.0) - 2.0) < 1e-9


def test_anclas_dentro_del_cuadro():
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in ANCHORS.values())
