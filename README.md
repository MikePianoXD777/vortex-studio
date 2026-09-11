# Vortex Studio

Editor de video no lineal. Parte de Vortex Suite.

## Arranque

```bash
python -m venv .venv
./.venv/bin/pip install -e .
./.venv/bin/python -m vortex_studio
```

En VS Code: `Ctrl+F5` corre, `F5` corre con depurador, `Ctrl+Shift+B` compila
el ejecutable a `dist/vortex-studio/`.

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

- **No hay audio**, ni en la reproducción ni en la exportación. Las pistas
  A1–A3 existen y aceptan clips, pero no suenan.
- La decodificación corre en el hilo de la interfaz: con 4K se va a arrastrar.
  Va junto con el audio, en un rediseño con hilo de decodificación y buffer.
- Al arrastrar, un clip puede encimarse con otro de la misma pista sin aviso.
