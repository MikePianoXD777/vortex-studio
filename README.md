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
| `Ctrl+Shift+E` | Exportar el cuadro actual a PNG |

| Editar | |
|---|---|
| `Ctrl+Z` / `Ctrl+Shift+Z` | Deshacer / rehacer |
| `V` / `C` | Herramienta selección / navaja |
| `Ctrl+K` | Cortar en el playhead |
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
- `ui/` — ventana, preview, timeline, transporte y paneles.

## Pendiente

- **No hay audio.** Las pistas A1–A3 existen y aceptan clips, pero no suenan.
- La decodificación corre en el hilo de la interfaz: con 4K se va a arrastrar.
  Va junto con el audio, en un rediseño con hilo de decodificación y buffer.
- No hay exportación de video todavía, solo de cuadro suelto.
