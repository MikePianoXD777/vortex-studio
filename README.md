# Vortex Studio

Editor de video no lineal. Parte de Vortex Suite.

## Arranque

Linux y macOS:

```bash
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m vortex_studio
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m vortex_studio
```

En VS Code da igual el sistema: `Ctrl+F5` corre, `F5` corre con depurador,
`Ctrl+Shift+B` compila el ejecutable y `Ctrl+Shift+P → Run Test Task` corre
las pruebas. Las tareas traen su variante de Windows.

Hace falta **ffmpeg en el PATH** solo para correr las pruebas; la aplicación
no lo necesita porque PyAV trae su propio FFmpeg.

## Pruebas

```bash
./.venv/bin/python -m pytest -q
```

El banco genera su propio material con ffmpeg la primera vez y corre sin
abrir ventanas, así que funciona por SSH o en una máquina sin pantalla.

| Archivo | Qué cubre |
|---|---|
| `test_modelo.py` | Pistas, clips, tiempos, timecode |
| `test_guardado.py` | Ida y vuelta del archivo .vortex |
| `test_historial.py` | Deshacer, rehacer, ramificar |
| `test_edicion.py` | Cortar, arrastrar, recortar, eliminar, duplicar |
| `test_color.py` | Brillo, contraste, saturación, gamma |
| `test_audio.py` | Onda y mezcla con huecos |
| `test_exportar.py` | Que el archivo salga como se ve al editar |
| `test_atajos.py` | Atajos, paneles y barra de estado |

## Atajos

| Archivo | |
|---|---|
| `Ctrl+N` / `Ctrl+O` | Nuevo / abrir proyecto |
| `Ctrl+S` / `Ctrl+Shift+S` | Guardar / guardar como |
| `Ctrl+I` | Importar video o imagen |
| `Ctrl+E` | Exportar video a MP4 |
| `Ctrl+Shift+E` | Exportar el cuadro actual a PNG |

| Editar | |
|---|---|
| `Ctrl+Z` / `Ctrl+Shift+Z` | Deshacer / rehacer |
| `V` / `C` | Herramienta selección / navaja |
| `Ctrl+K` / `Ctrl+D` | Cortar en el playhead / duplicar |
| `Supr` / `Shift+Supr` | Eliminar / eliminar cerrando el hueco |
| `Ctrl+T` / `Ctrl+Shift+T` | Insertar texto / subtítulo |

| Reproducción | |
|---|---|
| `Espacio` | Reproducir / pausar |
| `←` `→` | Cuadro a cuadro |
| `Shift`+flechas / `Ctrl`+flechas | Saltar 1 s / 10 s |
| `J` `K` `Shift+L` | Más lento / normal / más rápido |
| `L` | Repetir |
| `I` `O` / `Ctrl+Shift+X` | Marcar entrada, salida / quitar marcas |
| `F` | Pantalla completa |

En el timeline: `Ctrl`+rueda hace zoom, arrastrar un clip lo mueve, arrastrar
sus bordes lo recorta, y todo se imanta a los cortes vecinos y al playhead.

## Estructura

- `model/` — proyecto, secuencia, pistas, clips, textos, imágenes, color,
  historial y guardado. Python puro, sin Qt: se puede probar sin ventana.
- `media/` — decodificación y corrección de color con PyAV/FFmpeg.
- `ui/` — ventana, preview, timeline, transporte y paneles. El compositor
  vive aparte y lo comparten el preview y la exportación: es lo que garantiza
  que el archivo final se vea igual que lo que viste al editar.

## Exportar

`Ctrl+E` escribe un MP4 (H.264) con todo quemado: cortes, textos, imágenes y
corrección de color. Si hay marcas de entrada y salida, exporta solo ese tramo.
Se puede cancelar a media exportación; el archivo incompleto se borra.

## Pendiente

- **No hay audio durante la edición.** Se exporta al archivo final y se ve
  su onda en el timeline, pero no suena mientras editas: falta el motor de
  reproducción de sonido.
- La mezcla de exportación no suma pistas: toma los clips de audio en orden
  y rellena los huecos con silencio. Dos clips encimados no se mezclan.
- La decodificación corre en el hilo de la interfaz: con 4K se va a arrastrar.
  Va junto con el audio, en un rediseño con hilo de decodificación y buffer.
- No hay transiciones ni fundidos.
