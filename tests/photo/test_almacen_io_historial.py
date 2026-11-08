"""Almacén de imágenes, guardar/cargar/exportar, historial, plantillas y filtros."""

from __future__ import annotations

import json
import struct
import zipfile

import numpy as np
import pytest
from ayuda_photo import capa_imagen, colorido, degradado, doc_con, lum, ruido, solido
from PySide6.QtGui import QImage

from vortex_studio.photo import io as pio
from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import (Adjustments, Document, Filter, Layer, Transform,
                                          document_to_dict)
from vortex_studio.photo.filters import FILTERS, apply_filter, auto_enhance, scale_adjustments
from vortex_studio.photo.history import PhotoHistory
from vortex_studio.photo.render import Renderer, to_qimage
from vortex_studio.photo.templates import SIZES, text_presets


# --- almacén --------------------------------------------------------------------------

def test_almacen_el_id_es_el_hash_del_contenido_y_es_estable():
    a, b = AssetStore(), AssetStore()
    px = ruido(10, 10)
    assert a.put(px) == b.put(px.copy())
    assert a.put(px) == a.put(px.copy())
    assert len(a) == 1
    assert a.put(ruido(10, 10, 2)) != a.put(px)
    # misma bytes, distinta forma → otro id
    assert AssetStore().put(np.zeros((2, 8, 4), np.uint8)) != AssetStore().put(np.zeros((4, 4, 4), np.uint8))
    # el id no cambia entre ejecuciones (hash fijo, no el `hash()` de Python)
    assert AssetStore().put(np.zeros((1, 1, 4), np.uint8)) == AssetStore.hash_of(np.zeros((1, 1, 4), np.uint8))
    assert len(AssetStore().put(px)) == 32


def test_almacen_guarda_de_solo_lectura_y_copia():
    st = AssetStore()
    px = ruido(6, 6)
    i = st.put(px)
    px[0, 0, 0] ^= 255                                     # cambiar el original no cambia lo guardado
    g = st.get(i)
    assert g[0, 0, 0] != px[0, 0, 0]
    with pytest.raises(ValueError):
        g[0, 0, 0] = 1


def test_almacen_get_ids_size_has_y_collect():
    st = AssetStore()
    a, b = st.put(ruido(7, 5)), st.put(ruido(3, 9))
    assert st.size(a) == (7, 5) and st.size(b) == (3, 9)
    assert st.has(a) and not st.has("nada")
    with pytest.raises(KeyError):
        st.get("nada")
    with pytest.raises(KeyError):
        st.size("nada")
    assert st.ids() == {a, b}
    st.collect({a})
    assert st.ids() == {a} and not st.has(b)
    st.collect(set())
    assert st.ids() == set()


def test_almacen_acepta_mascaras_2d_y_otros_tipos():
    st = AssetStore()
    i = st.put(np.zeros((4, 6), np.uint8))
    assert st.size(i) == (6, 4)
    j = st.put(np.full((2, 2, 4), 300.0))
    assert st.get(j).dtype == np.uint8 and st.get(j).max() == 255


# --- imágenes ----------------------------------------------------------------------------

def _jpeg_con_exif(path, orientacion, ancho=40, alto=20):
    """Un JPG con la etiqueta de orientación EXIF que se pida (Qt no sabe escribirla)."""
    px = np.zeros((alto, ancho, 4), np.uint8)
    px[..., 3] = 255
    px[:, : ancho // 2] = (255, 0, 0, 255)                    # mitad izquierda roja
    to_qimage(px).convertToFormat(QImage.Format.Format_RGB888).save(str(path), "JPG", 100)
    datos = path.read_bytes()
    tiff = b"II*\x00\x08\x00\x00\x00" + struct.pack("<H", 1) + struct.pack("<HHIHH", 0x0112, 3, 1, orientacion, 0) + b"\x00\x00\x00\x00"
    app1 = b"Exif\x00\x00" + tiff
    path.write_bytes(datos[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + datos[2:])


def test_cargar_imagen_aplica_la_orientacion_exif(tmp_path):
    p = tmp_path / "foto.jpg"
    _jpeg_con_exif(p, 1)
    assert pio.load_image(p).shape == (20, 40, 4)
    _jpeg_con_exif(p, 6)                                       # girada 90° a favor del reloj
    girada = pio.load_image(p)
    assert girada.shape == (40, 20, 4)
    assert girada[5, 10, 0] > 200 and girada[35, 10, 0] < 50        # la mitad roja (izquierda) quedó arriba
    _jpeg_con_exif(p, 3)
    assert pio.load_image(p).shape == (20, 40, 4)


def test_cargar_imagen_de_los_formatos_y_errores(tmp_path):
    px = colorido(30, 20)
    for ext in ("png", "jpg", "webp", "bmp", "tiff"):
        p = tmp_path / f"i.{ext}"
        to_qimage(px).save(str(p))
        out = pio.load_image(p)
        assert out.shape == (20, 30, 4) and out.dtype == np.uint8
    (tmp_path / "x.png").write_bytes(b"esto no es una imagen")
    with pytest.raises(pio.PhotoFileError):
        pio.load_image(tmp_path / "x.png")
    with pytest.raises(pio.PhotoFileError):
        pio.load_image(tmp_path / "no_existe.png")
    assert "png" in pio.OPEN_FILTER and "jpg" in pio.OPEN_FILTER


def test_png_conserva_los_pixeles_exactos_con_alfa(tmp_path):
    px = ruido(17, 11)
    px[..., 3] = np.linspace(0, 255, 17).astype(np.uint8)[None, :]
    to_qimage(px).save(str(tmp_path / "a.png"))
    assert np.array_equal(pio.load_image(tmp_path / "a.png")[..., 3], px[..., 3])
    visibles = px[..., 3] > 0
    assert np.array_equal(pio.load_image(tmp_path / "a.png")[visibles], px[visibles])


def test_add_image_centra_y_ajusta(tmp_path):
    st, d = AssetStore(), Document(200, 100)
    capa = pio.add_image(d, st, solido(400, 100))
    assert d.layers[-1] is capa
    t = capa.transform
    assert (t.cx, t.cy) == (100, 50) and t.width == 200 and t.height == 50
    chica = pio.add_image(d, st, solido(20, 10))
    assert (chica.transform.width, chica.transform.height) == (20, 10)       # nunca agranda
    real = pio.add_image(d, st, solido(400, 100), fit=False)
    assert real.transform.width == 400
    assert d.layers[-1] is real and st.has(capa.asset)
    p = tmp_path / "f.png"
    to_qimage(colorido(30, 20)).save(str(p))
    por_ruta = pio.add_image(d, st, p)
    assert por_ruta.name == "f" and st.size(por_ruta.asset) == (30, 20)


def test_add_image_acepta_gris_y_rgb():
    st, d = AssetStore(), Document(50, 50)
    pio.add_image(d, st, np.zeros((4, 4), np.uint8))
    pio.add_image(d, st, np.zeros((4, 4, 3), np.uint8))
    assert all(st.get(c.asset).shape == (4, 4, 4) for c in d.layers)


# --- proyecto .vphoto ----------------------------------------------------------------------

def _doc_completo():
    st = AssetStore()
    m = np.zeros((20, 30), np.uint8)
    m[:, :15] = 255
    foto = capa_imagen(st, colorido(30, 20), 50, 40, 60, 40, mask=st.put(m), name="foto",
                       adjustments=Adjustments(exposure=20, curve=[(0, 0), (0.5, 0.6), (1, 1)], hsl={"red": (10, -20, 5)}),
                       filter=Filter("vivido", 70), opacity=0.8, blend="Multiplicar")
    foto.crop = (2, 2, 20, 10)
    txt = Layer(kind="text", text="Hola ñandú", font_family="Inter", font_size=30, transform=Transform(50, 20, 80, 30))
    forma = Layer(kind="shape", shape="star", fill="#ff00ff", transform=Transform(20, 80, 30, 30, 15))
    aj = Layer(kind="adjust", adjustments=Adjustments(saturation=-30), transform=Transform(50, 50, 100, 100))
    return doc_con(st, 100, 100, foto, txt, forma, aj), st


def test_guardar_y_cargar_ida_y_vuelta(tmp_path):
    doc, st = _doc_completo()
    p = tmp_path / "d.vphoto"
    pio.save_document(doc, st, p)
    assert zipfile.is_zipfile(p) and not list(tmp_path.glob("*.tmp"))
    with zipfile.ZipFile(p) as z:
        nombres = set(z.namelist())
    assert "document.json" in nombres and sum(n.startswith("assets/") for n in nombres) == 2
    doc2, st2 = pio.load_document(p)
    assert document_to_dict(doc2) == document_to_dict(doc)
    for aid in doc.assets():
        assert np.array_equal(st2.get(aid), st.get(aid))
    assert np.array_equal(Renderer(st2).render(doc2), Renderer(st).render(doc))


def test_la_mascara_vuelve_en_2d(tmp_path):
    doc, st = _doc_completo()
    p = tmp_path / "d.vphoto"
    pio.save_document(doc, st, p)
    doc2, st2 = pio.load_document(p)
    assert st2.get(doc2.layers[0].mask).shape == (20, 30)


def test_guardar_encima_no_deja_basura_y_falla_limpio(tmp_path):
    doc, st = _doc_completo()
    p = tmp_path / "d.vphoto"
    pio.save_document(doc, st, p)
    pio.save_document(doc, st, p)
    assert [x.name for x in tmp_path.iterdir()] == ["d.vphoto"]
    with pytest.raises(OSError):
        pio.save_document(doc, st, tmp_path / "no" / "existe" / "d.vphoto")
    assert [x.name for x in tmp_path.iterdir()] == ["d.vphoto"]


def test_documento_vacio_se_guarda_y_carga(tmp_path):
    p = tmp_path / "v.vphoto"
    pio.save_document(Document(10, 10, None), AssetStore(), p)
    d, st = pio.load_document(p)
    assert d.layers == [] and d.background is None and len(st) == 0


def test_cargar_archivos_rotos_da_error_claro(tmp_path):
    casos = {
        "basura.vphoto": b"\x00\x01\x02 esto no es un zip",
        "vacio.vphoto": b"",
    }
    for nombre, datos in casos.items():
        (tmp_path / nombre).write_bytes(datos)
        with pytest.raises(pio.PhotoFileError) as e:
            pio.load_document(tmp_path / nombre)
        assert nombre in str(e.value)
    with pytest.raises(pio.PhotoFileError):
        pio.load_document(tmp_path / "no_hay.vphoto")
    # zip válido pero sin document.json, con JSON roto, o con JSON que no es un objeto
    for nombre, contenido in (("a", None), ("b", b"{no es json"), ("c", b"[1, 2, 3]"), ("d", b"\xff\xfe\x00")):
        p = tmp_path / f"{nombre}.vphoto"
        with zipfile.ZipFile(p, "w") as z:
            if contenido is None:
                z.writestr("otra_cosa.txt", "x")
            else:
                z.writestr("document.json", contenido)
        with pytest.raises(pio.PhotoFileError):
            pio.load_document(p)
    assert issubclass(pio.PhotoFileError, ValueError)


def test_zip_truncado(tmp_path):
    doc, st = _doc_completo()
    p = tmp_path / "d.vphoto"
    pio.save_document(doc, st, p)
    datos = p.read_bytes()
    for corte in (len(datos) // 2, len(datos) - 10, 30):
        (tmp_path / "t.vphoto").write_bytes(datos[:corte])
        try:
            pio.load_document(tmp_path / "t.vphoto")
        except pio.PhotoFileError:
            pass


def test_si_falta_una_imagen_el_diseno_abre_y_la_capa_queda_vacia(tmp_path):
    doc, st = _doc_completo()
    p = tmp_path / "d.vphoto"
    pio.save_document(doc, st, p)
    q = tmp_path / "sin.vphoto"
    with zipfile.ZipFile(p) as z, zipfile.ZipFile(q, "w") as w:
        for n in z.namelist():
            if not n.startswith("assets/"):
                w.writestr(n, z.read(n))
        extra = [n for n in z.namelist() if n.startswith("assets/")][0]
        w.writestr(extra, b"no es un png")              # y una imagen corrupta
    doc2, st2 = pio.load_document(q)
    assert len(doc2.layers) == 4
    assert Renderer(st2).render(doc2).shape == (100, 100, 4)


def test_archivo_de_una_version_mas_nueva_o_con_campos_de_mas(tmp_path):
    p = tmp_path / "n.vphoto"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("document.json", json.dumps({
            "format": 99, "width": 50, "height": 40, "campo_del_futuro": {"x": 1}, "background": "#00ff00",
            "layers": [{"kind": "shape", "shape": "rect", "campo_nuevo": 1, "blend": "ModoDelFuturo",
                        "transform": {"cx": 25, "cy": 20, "width": 10, "height": 10, "skew": 3}},
                       "basura", None],
        }))
    try:
        d, _ = pio.load_document(p)
    except pio.PhotoFileError:
        return                                            # error claro también es válido
    assert (d.width, d.height) == (50, 40)


def test_archivo_con_valores_por_omision_cuando_faltan(tmp_path):
    p = tmp_path / "m.vphoto"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("document.json", json.dumps({"layers": [{"kind": "text", "text": "x"}]}))
    d, st = pio.load_document(p)
    assert (d.width, d.height) == (1080, 1080) and d.layers[0].text == "x"
    assert Renderer(st).render(d, 0.1).shape == (108, 108, 4)


def test_lienzo_gigante_declarado_se_rechaza(tmp_path):
    p = tmp_path / "g.vphoto"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("document.json", json.dumps({"width": 10 ** 9, "height": 10 ** 9}))
    with pytest.raises(pio.PhotoFileError):
        pio.load_document(p)


# --- exportar ------------------------------------------------------------------------------

def _doc_chico():
    st = AssetStore()
    c = capa_imagen(st, colorido(60, 40), 50, 30, 100, 60)
    return doc_con(st, 100, 60, c), st


def test_exportar_los_tres_formatos_y_releer(tmp_path):
    doc, st = _doc_chico()
    esperado = Renderer(st).render(doc)
    for fmt in pio.EXPORT_FORMATS:
        p = tmp_path / f"o.{fmt.lower()}"
        pio.export(doc, st, p, fmt, 95)
        assert p.stat().st_size > 100
        leida = pio.load_image(p)
        assert leida.shape == (60, 100, 4)
        err = np.abs(leida[..., :3].astype(int) - esperado[..., :3]).mean()
        assert err == 0 if fmt == "PNG" else err < 8, fmt


def test_exportar_escala(tmp_path):
    doc, st = _doc_chico()
    pio.export(doc, st, tmp_path / "a.png", "PNG", scale=2.0)
    pio.export(doc, st, tmp_path / "b.png", "PNG", scale=0.5)
    assert pio.load_image(tmp_path / "a.png").shape == (120, 200, 4)
    assert pio.load_image(tmp_path / "b.png").shape == (30, 50, 4)


def test_exportar_calidad_cambia_el_tamano_del_jpg(tmp_path):
    st = AssetStore()
    doc = doc_con(st, 128, 128, capa_imagen(st, ruido(128, 128), 64, 64))
    pio.export(doc, st, tmp_path / "bajo.jpg", "JPG", 10)
    pio.export(doc, st, tmp_path / "alto.jpg", "JPG", 98)
    assert (tmp_path / "bajo.jpg").stat().st_size < (tmp_path / "alto.jpg").stat().st_size


def test_exportar_jpg_aplana_la_transparencia(tmp_path):
    st = AssetStore()
    doc = doc_con(st, 20, 20, capa_imagen(st, solido(10, 20, (255, 0, 0, 255)), 5, 10), fondo=None)
    pio.export(doc, st, tmp_path / "t.jpg", "JPG", 100)
    leida = pio.load_image(tmp_path / "t.jpg")
    assert leida[10, 15, :3].min() > 245                         # lo transparente quedó blanco, no negro
    assert leida[10, 3, 0] > 240 and leida[10, 3, 1] < 20
    assert leida[..., 3].min() == 255
    pio.export(doc, st, tmp_path / "t.png", "PNG")
    assert pio.load_image(tmp_path / "t.png")[10, 15, 3] == 0    # y el PNG sí conserva la transparencia


def test_exportar_formato_malo_o_ruta_mala(tmp_path):
    doc, st = _doc_chico()
    with pytest.raises(ValueError):
        pio.export(doc, st, tmp_path / "x.gif", "GIF")
    with pytest.raises(OSError):
        pio.export(doc, st, tmp_path / "no" / "hay" / "x.png", "PNG")
    pio.export(doc, st, tmp_path / "ok.jpeg", "jpeg")             # sinónimos y minúsculas
    pio.export(doc, st, tmp_path / "ok.png", "png", quality=500)  # calidad fuera de rango se recorta


def test_exportar_lienzo_de_un_pixel_y_escala_minima(tmp_path):
    st = AssetStore()
    pio.export(Document(1, 1, "#ff0000"), st, tmp_path / "u.png", "PNG")
    assert pio.load_image(tmp_path / "u.png").tolist() == [[[255, 0, 0, 255]]]
    pio.export(Document(50, 50), st, tmp_path / "m.png", "PNG", scale=0.0001)
    assert pio.load_image(tmp_path / "m.png").shape[0] >= 1


def test_lote_con_progreso_y_ajustes(tmp_path):
    origen = tmp_path / "in"
    origen.mkdir()
    rutas = []
    for i in range(3):
        p = origen / f"f{i}.png"
        to_qimage(colorido(40, 30)).save(str(p))
        rutas.append(p)
    avances = []
    out = pio.export_batch(rutas, Adjustments(saturation=-100), None, tmp_path / "out", "JPG", 90,
                           progress=lambda h, t: avances.append((h, t)))
    assert avances == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert [p.name for p in out] == ["f0.jpg", "f1.jpg", "f2.jpg"] and all(p.exists() for p in out)
    img = pio.load_image(out[0])
    assert np.abs(img[..., 0].astype(int) - img[..., 1]).max() < 12          # quedó en gris (con la pérdida del JPG)
    # filtro en vez de ajustes
    out2 = pio.export_batch(rutas[:1], None, Filter("bn", 100), tmp_path / "out2", "PNG")
    g = pio.load_image(out2[0])
    assert np.abs(g[..., 0].astype(int) - g[..., 1]).max() <= 2


def test_lote_no_pisa_archivos_y_se_salta_los_rotos(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    to_qimage(colorido(10, 10)).save(str(a / "foto.png"))
    to_qimage(colorido(12, 12)).save(str(b / "foto.png"))
    (a / "rota.png").write_bytes(b"nada")
    salida = tmp_path / "out"
    r1 = pio.export_batch([a / "foto.png", b / "foto.png", a / "rota.png", tmp_path / "no.png"], None, None, salida, "PNG")
    assert [p.name for p in r1] == ["foto.png", "foto_2.png"]
    r2 = pio.export_batch([a / "foto.png"], None, None, salida, "PNG")        # segunda tanda: tampoco pisa
    assert r2[0].name == "foto_3.png"
    assert pio.export_batch([], None, None, salida, "PNG") == []


# --- historial ------------------------------------------------------------------------------

def _d(n):
    d = Document(100, 100)
    d.name = f"v{n}"
    return d


def test_historial_deshacer_y_rehacer():
    h = PhotoHistory()
    h.reset(_d(0))
    assert not h.can_undo and not h.can_redo and h.undo() is None and h.redo() is None
    h.push(_d(1), "Mover")
    h.push(_d(2), "Girar")
    assert h.can_undo and h.undo_label == "Girar" and not h.can_redo
    assert h.undo().name == "v1"
    assert h.can_redo and h.redo_label == "Girar" and h.undo_label == "Mover"
    assert h.undo().name == "v0" and not h.can_undo
    assert h.redo().name == "v1" and h.redo().name == "v2" and h.redo() is None


def test_historial_limite_de_cien_pasos():
    h = PhotoHistory()
    h.reset(_d(0))
    for i in range(1, 151):
        h.push(_d(i), f"p{i}")
    pasos = 0
    ultimo = None
    while h.can_undo:
        ultimo = h.undo()
        pasos += 1
    assert pasos == 100 and ultimo.name == "v50"


def test_historial_una_accion_nueva_borra_la_rama_de_rehacer():
    h = PhotoHistory()
    h.reset(_d(0))
    h.push(_d(1), "a")
    h.push(_d(2), "b")
    h.undo()
    h.undo()
    h.push(_d(9), "otra")
    assert not h.can_redo and h.undo_label == "otra" and h.undo().name == "v0"
    assert h.redo().name == "v9"


def test_historial_no_agrega_pasos_que_no_cambian_nada():
    h = PhotoHistory()
    h.reset(_d(0))
    h.push(_d(0), "nada")
    assert not h.can_undo and len(h) == 1


def test_historial_las_instantaneas_son_independientes_del_documento_vivo():
    h = PhotoHistory()
    doc = Document(100, 100)
    h.reset(doc)
    doc.layers.append(Layer(kind="shape", transform=Transform(5, 5, 10, 10)))
    h.push(doc, "forma")
    doc.layers[0].transform.cx = 99                        # tocar el vivo no debe alterar la historia
    anterior = h.undo()
    assert anterior.layers == []
    otra = h.redo()
    assert otra.layers[0].transform.cx == 5
    otra.layers.clear()
    assert len(h.undo().layers) == 0 and len(h.redo().layers) == 1


def test_historial_sin_reset_empieza_con_el_primer_push():
    h = PhotoHistory()
    h.push(_d(1), "x")
    assert not h.can_undo and len(h) == 1
    h.reset(_d(5))
    assert len(h) == 1 and h.undo_label == "" and h.redo_label == ""


def test_historial_assets_en_uso_incluye_lo_deshecho_y_las_mascaras():
    st = AssetStore()
    a, b, m = st.put(ruido(4, 4, 1)), st.put(ruido(4, 4, 2)), st.put(np.zeros((4, 4), np.uint8))
    h = PhotoHistory()
    doc = Document(10, 10)
    h.reset(doc)
    doc.layers.append(Layer(kind="image", asset=a, mask=m))
    h.push(doc, "agregar")
    doc.layers.append(Layer(kind="image", asset=b))
    h.push(doc, "otra")
    h.undo()
    assert h.assets_in_use() == {a, b, m}
    st.collect(h.assets_in_use() | doc.assets())
    assert st.ids() == {a, b, m}
    h.reset(Document(10, 10))
    assert h.assets_in_use() == set()


# --- plantillas -----------------------------------------------------------------------------

def test_tamanos_comunes():
    por_nombre = {n: (w, h) for _, n, w, h in SIZES}
    assert por_nombre["Instagram publicación"] == (1080, 1080)
    assert por_nombre["Instagram historia"] == (1080, 1920)
    assert por_nombre["TikTok"] == (1080, 1920)
    assert por_nombre["YouTube miniatura"] == (1280, 720)
    assert por_nombre["Presentación 16:9"] == (1920, 1080)
    assert por_nombre["A4 (300 ppp)"] == (2480, 3508) and por_nombre["Carta (300 ppp)"] == (2550, 3300)
    assert por_nombre["Foto 4×6 (300 ppp)"] == (1800, 1200)
    assert any("Facebook" in n for n in por_nombre) and any("Pinterest" in n for n in por_nombre)
    assert any("Banner" in n for n in por_nombre)
    assert len(por_nombre) == len(SIZES) >= 15
    assert all(isinstance(w, int) and isinstance(h, int) and 0 < w <= 8000 and 0 < h <= 8000 for _, _, w, h in SIZES)
    assert all(g and n for g, n, _, _ in SIZES)


def test_textos_prediseñados():
    ps = text_presets()
    assert [n for n, _ in ps] == ["Agregar un título", "Agregar un subtítulo", "Agregar un cuerpo de texto"]
    tamanos = [c.font_size for _, c in ps]
    assert tamanos == sorted(tamanos, reverse=True) and len(set(tamanos)) == 3
    assert all(c.kind == "text" and c.text and c.transform.height > 0 and c.transform.width > 0 for _, c in ps)
    assert ps[0][1].bold
    assert len({c.id for _, c in ps}) == 3


# --- filtros --------------------------------------------------------------------------------

def test_hay_unos_veinte_filtros_con_nombres_en_espanol_y_todos_se_ven_distinto():
    assert len(FILTERS) >= 20
    assert len({p.name for p in FILTERS.values()}) == len(FILTERS)
    assert all(k == p.id for k, p in FILTERS.items())
    assert {"Natural", "Vívido", "Cálido", "Frío", "Blanco y negro", "Noir", "Sepia"} <= {p.name for p in FILTERS.values()}
    px = colorido(48, 36)
    resultados = {}
    for k in FILTERS:
        out = apply_filter(px, Filter(k, 100))
        assert out.shape == px.shape and np.array_equal(out[..., 3], px[..., 3])
        assert not np.array_equal(out, px), k
        resultados[k] = out
    claves = list(resultados)
    iguales = [(a, b) for i, a in enumerate(claves) for b in claves[i + 1:] if np.array_equal(resultados[a], resultados[b])]
    assert not iguales


def test_filtros_blanco_y_negro_y_sepia_y_temperaturas():
    px = colorido(48, 36)
    bn = apply_filter(px, Filter("bn", 100))
    assert np.abs(bn[..., 0].astype(int) - bn[..., 2]).max() <= 2
    sepia = apply_filter(px, Filter("sepia", 100))
    assert (sepia[..., 0].astype(int) > sepia[..., 2]).mean() > 0.9
    g = solido(4, 4, (128, 128, 128, 255))
    assert apply_filter(g, Filter("calido", 100))[0, 0, 0] > apply_filter(g, Filter("frio", 100))[0, 0, 0]


def test_intensidad_del_filtro():
    px = colorido(32, 24)
    assert apply_filter(px, Filter("vivido", 0)) is px
    assert apply_filter(px, Filter("", 100)) is px
    assert apply_filter(px, Filter("no existe", 100)) is px
    pleno = apply_filter(px, Filter("noir", 100)).astype(int)
    medio = apply_filter(px, Filter("noir", 50)).astype(int)
    d0 = np.abs(pleno - px).mean()
    d50 = np.abs(medio - px).mean()
    assert 0 < d50 < d0
    assert np.array_equal(apply_filter(px, Filter("noir", 250)), apply_filter(px, Filter("noir", 100)))


def test_el_filtro_se_encuentra_por_nombre_visible_tambien():
    px = colorido(16, 12)
    assert np.array_equal(apply_filter(px, Filter("Blanco y negro", 100)), apply_filter(px, Filter("bn", 100)))


def test_escalar_ajustes_a_cero_es_neutro_y_a_uno_es_igual():
    for p in FILTERS.values():
        assert scale_adjustments(p.adjustments, 0.0).is_neutral() or all(
            abs(getattr(scale_adjustments(p.adjustments, 0.0), f)) < 1e-9
            for f in ("exposure", "contrast", "saturation", "temperature", "grain", "vignette"))
        assert scale_adjustments(p.adjustments, 1.0) == p.adjustments
    medio = scale_adjustments(FILTERS["vintage"].adjustments, 0.5)
    assert medio.vignette == pytest.approx(FILTERS["vintage"].adjustments.vignette / 2)
    completa = dict(FILTERS["matte"].adjustments.curve)
    mitad = dict((round(x, 6), y) for x, y in scale_adjustments(FILTERS["matte"].adjustments, 0.5).curve)
    assert all(abs(mitad[x] - x) <= abs(completa_y - x) + 0.02 for x, completa_y in
               ((x, float(np.interp(x, *zip(*FILTERS["matte"].adjustments.curve)))) for x in mitad))


def test_filtro_a_cero_de_curva_es_recta():
    adj = scale_adjustments(FILTERS["matte"].adjustments, 0.0)
    out = apply_filter(degradado(64, 2), Filter("matte", 0))
    assert out is not None
    from vortex_studio.photo.adjust import apply_adjustments
    assert np.array_equal(apply_adjustments(degradado(64, 2), adj), degradado(64, 2))


def test_mejorar_con_un_clic_en_fotos_oscuras_claras_y_planas():
    oscura = (degradado(64, 32)).copy()
    oscura[..., :3] = (oscura[..., :3] * 0.25).astype(np.uint8)
    clara = degradado(64, 32).copy()
    clara[..., :3] = (155 + clara[..., :3].astype(int) * 100 // 255).astype(np.uint8)
    a_osc, a_cla = auto_enhance(oscura), auto_enhance(clara)
    assert a_osc.exposure > 10 and a_cla.exposure < -10
    assert a_osc.shadows > 0 and a_cla.highlights < 0
    plana = solido(32, 32, (120, 125, 118, 255))
    assert auto_enhance(plana).contrast >= 0
    # el resultado es moderado: ningún valor extremo y mejora la foto oscura
    for a in (a_osc, a_cla, auto_enhance(colorido(32, 32))):
        assert all(abs(getattr(a, f)) <= 60 for f in ("exposure", "contrast", "highlights", "shadows", "whites", "blacks", "saturation", "vibrance", "clarity"))
    from vortex_studio.photo.adjust import apply_adjustments
    mejor = apply_adjustments(oscura, a_osc)
    assert lum(mejor).mean() > lum(oscura).mean() + 10


def test_mejorar_con_un_clic_casos_raros():
    assert auto_enhance(solido(1, 1)).exposure is not None
    assert auto_enhance(np.zeros((8, 8, 4), np.uint8)).is_neutral()              # todo transparente
    assert isinstance(auto_enhance(solido(8, 8, (0, 0, 0, 255))), Adjustments)   # negro puro
    assert isinstance(auto_enhance(solido(8, 8, (255, 255, 255, 255))), Adjustments)
    assert isinstance(auto_enhance(ruido(300, 200)), Adjustments)
