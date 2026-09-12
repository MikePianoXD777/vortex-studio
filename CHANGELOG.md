# Changelog

**Español** · [English](CHANGELOG.en.md)

Todo lo que cambia en Vortex Studio, de lo más nuevo a lo más viejo.

Las versiones siguen [versionado semántico](https://semver.org/lang/es/):
`MAYOR.MENOR.PARCHE`. Mientras estemos en `0.x`, cualquier versión menor
puede romper compatibilidad.

## [Sin publicar]

Nada todavía.

## [0.1.0a1] — 2026-09-12

**Pre-alfa.** Primera versión con todo funcionando de punta a punta: corta,
anima, suena y exporta. Pasa 167 pruebas automáticas, pero nadie la ha usado
todavía con material propio, así que cuenta con que algo se rompa. El formato
del archivo `.vortex` puede cambiar antes de la 0.1.0 de verdad.

**Sin ejecutables.** No hay `.exe` ni binario de Linux: hay que compilarlo
con `./correr.sh` o `construir.bat`. Habrá binarios cuando esté más estable.

### Reproductor

- Reproducción guiada por reloj real: la posición se calcula contra el
  tiempo transcurrido, así un cuadro lento se salta en vez de acumular
  retraso.
- Velocidades de 0.25× a 4×, repetición, marcas de entrada y salida, saltos
  de 1 y 10 segundos, pantalla completa.
- Sonido durante la edición, con volumen y silencio. El playhead se guía
  por lo que ya salió por la tarjeta, no por el reloj de la interfaz.

### Edición

- Seleccionar, arrastrar y mover clips entre pistas, con imantado a los
  cortes vecinos y al playhead.
- Recorte por los bordes. En un clip de archivo, recortar por el inicio
  avanza el punto de entrada en vez de estirar la imagen.
- Navaja, corte en el playhead, duplicar, eliminar con y sin cerrar hueco.
- Lo que se suelta encima recorta a lo que estaba, sin traslapes en silencio.
- Deshacer y rehacer por instantáneas, con el nombre de la acción.
- Seis pistas: T1 de texto, V2 y V1 de video, A1 a A3 de audio.
- Marcadores con nombre, navegables con `Shift`+flechas.

### Texto e imágenes

- Títulos y subtítulos con posición por preset, tamaño relativo al cuadro,
  color, alineación, contorno y caja.
- Imágenes sobre el video, con posición, tamaño, opacidad y duración.

### Color

- Brillo, contraste, saturación, gamma y temperatura por clip.
- Looks de un clic: Cálido, Frío, Cine, Vívido, Suave, Blanco y negro,
  Noche. Escriben en los mismos controles, así que se puede seguir ajustando.

### Animación

- Posición, tamaño, giro y opacidad por clip, las cuatro animables por
  keyframes, con interpolación suave.
- Los keyframes van en tiempo relativo al clip, así que mover el clip se
  lleva su animación.

### Transiciones

- Fundidos de entrada y salida en clips, imágenes y textos.
- Fundido cruzado entre clips pegados, repartido alrededor del corte.

### Tiempo

- Velocidad del clip de 0.1× a 10×, ajustando la duración para no perder
  material.
- Congelar cuadro.

### Audio

- El audio de un video importado entra como su propio clip en A1.
- Forma de onda en las pistas de audio, calculada por picos.
- Volumen y fundidos por clip.

### Proyecto y exportación

- Guardar y abrir `.vortex`, con rutas relativas: la carpeta se puede mover,
  mandar a otra máquina o pasar de Linux a Windows y sigue abriendo.
- Exportar MP4 H.264 con todo quemado, con audio, con progreso y cancelable.
  Al cancelar se borra el archivo a medias.
- Exportar el cuadro actual a PNG.
- Formatos de secuencia: vertical 9:16, cuadrado, 4:5, cine 21:9.

### Interfaz

- Splash de carga que cubre la carga real, no un retraso falso.
- Launcher para elegir entre Video y Fotos (Fotos todavía no habilitado).
- Panel de propiedades con cinco pestañas, que se cambia sola según la
  selección pero respeta la que elegiste a mano.
- Barra de estado con resolución, fps, duración, conteo y herramienta.

### Arreglado

- Quince atajos de una sola tecla se comían lo que escribías: la `c`
  activaba la navaja y `Supr` borraba el clip seleccionado.
- Ningún atajo usa `Ctrl+Alt`, que es `AltGr` en teclado latinoamericano.
- Los clips se comparaban por valor, así que borrar el audio se llevaba el
  video.
- Un decodificador por archivo se caía a segundos por cuadro durante una
  transición entre dos mitades del mismo video.
- La forma de onda se calculaba dentro del repintado y congelaba la ventana.
- El splash no se veía bajo Wayland.
- `Exportar cuadro` ignoraba el formato de la secuencia.
- Tres avisos salían en diálogos modales que interrumpían sin necesidad.

### Por dentro

- 167 pruebas automáticas que corren en 14 segundos sin abrir ventanas.
- El modelo es Python puro: se prueba sin Qt.
- Un solo compositor para el preview y la exportación, para que el archivo
  final se vea igual que lo que viste al editar.
- Corrección de color y volumen con filtros de FFmpeg, no con bucles en
  Python.
