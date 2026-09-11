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

En Windows también hay atajos: `construir.bat` compila el ejecutable a
`dist\vortex-studio\vortex-studio.exe` y `probar.bat` corre las pruebas.
Los dos crean el entorno virtual si hace falta.

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
| `test_clip.py` | Fundidos, velocidad, congelar cuadro |
| `test_marcadores.py` | Marcadores y su navegación |
| `test_atajos.py` | Atajos, paneles y barra de estado |
| `test_transicion.py` | Fundido cruzado entre clips |
| `test_reproduccion.py` | Sonido y sincronía con la imagen |
| `test_portabilidad.py` | Que funcione igual en Linux y Windows |

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
| `Ctrl+Shift+D` | Fundir entrada y salida del clip |
| `Ctrl+Shift+F` | Congelar el cuadro actual |
| `Supr` / `Shift+Supr` | Eliminar / eliminar cerrando el hueco |
| `Ctrl+T` / `Ctrl+Shift+T` | Insertar texto / subtítulo |

| Reproducción | |
|---|---|
| `Espacio` | Reproducir / pausar |
| `←` `→` | Cuadro a cuadro |
| `Shift`+flechas / `Ctrl`+flechas | Saltar 1 s / 10 s |
| `J` `K` `Shift+L` | Más lento / normal / más rápido |
| `L` | Repetir |
| `Ctrl+Shift+A` | Transición cruzada con el clip anterior |
| `I` `O` / `Ctrl+Shift+X` | Marcar entrada, salida / quitar marcas |
| `M` / `Shift+M` | Poner marcador / marcador con nombre |
| `Shift+↓` `Shift+↑` | Marcador siguiente / anterior |
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

## Sonido

Se oye mientras editas, con volumen y silencio en la barra de transporte. El
playhead se guía por lo que ya salió por la tarjeta, no por el reloj de la
interfaz: el audio no se puede acelerar ni saltar sin que se note, así que
manda él y la imagen lo sigue.

## Exportar

`Ctrl+E` escribe un MP4 (H.264) con todo quemado: cortes, textos, imágenes y
corrección de color. Si hay marcas de entrada y salida, exporta solo ese tramo.
Se puede cancelar a media exportación; el archivo incompleto se borra.

## Portabilidad

El proyecto `.vortex` guarda las rutas **relativas** cuando el material está
junto al proyecto o debajo de él, y siempre con barras normales. Así la
carpeta se puede mover, mandar a otra máquina o pasar de Linux a Windows y
sigue abriendo. Solo se guarda absoluta la ruta de material que vive fuera.

No hay ningún atajo con `Ctrl+Alt`: en Windows con teclado latinoamericano
`AltGr` manda exactamente eso, y escribir `@` o `\` dispararía comandos del
editor. Hay una prueba que lo vigila.

## Pendiente

- La mezcla no suma pistas: toma los clips de audio en orden y rellena los
  huecos con silencio. Dos clips encimados no se mezclan entre sí.
- El sonido solo acompaña a velocidad normal. A 2× saldría con el tono
  cambiado, que es peor que no oírlo.
- La decodificación de imagen sigue en el hilo de la interfaz: con 4K se va
  a arrastrar.
- La decodificación corre en el hilo de la interfaz: con 4K se va a arrastrar.
  Va junto con el audio, en un rediseño con hilo de decodificación y buffer.
- La única transición es el fundido cruzado; no hay cortinillas ni efectos.
- No hay escalado ni reposicionamiento del video dentro del cuadro.
