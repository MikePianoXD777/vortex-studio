# Changelog

**Español** · [English](CHANGELOG.en.md)

Todo lo que cambia en Vortex Studio, de lo más nuevo a lo más viejo.

Las versiones siguen [versionado semántico](https://semver.org/lang/es/):
`MAYOR.MENOR.PARCHE`. Mientras estemos en `0.x`, cualquier versión menor
puede romper compatibilidad.

## [Sin publicar]

Nada todavía.

## [0.3.0a1] — 2026-09-12

**El nivel 1 del roadmap, completo.** Todo lo que un editor necesita para
ser un editor: decodificación fuera de la interfaz, sondeo de medios, slip,
atajos configurables, onda de audio en caché, exportar con presets y
autoguardado. Sigue en pre-alfa: pasa 493 pruebas automáticas —205 más que
la 0.2.0a1—, pero nadie la ha usado con material propio de verdad.

**El formato del archivo subió a la versión 3.** Los proyectos de la 0.1 y
la 0.2 abren sin problema, porque ahora cada cambio de formato tiene su
migración. Al revés no: la 0.2.0a1 se niega a abrir un proyecto de esta.

**Sigue sin ejecutables.** Los binarios llegan al terminar la pre-alfa.

### Decodificación fuera del hilo de la interfaz

- Antes, cada movimiento del playhead decodificaba en la ventana misma, y la
  interfaz se quedaba trabada mientras tanto. Medido saltando a 25
  posiciones al azar, con el decodificador ya abierto:

  | Material | Antes | Ahora |
  |---|---|---|
  | 1080p | 26 ms por salto (peor: 41) | 0.45 ms (peor: 0.8) |
  | 4K | 111 ms por salto (peor: 176) | 0.57 ms (peor: 1.1) |

- Un servidor de cuadros decodifica en su propio hilo. Gana el pedido más
  nuevo: arrastrar el playhead no decodifica las posiciones por las que
  pasó, solo donde se soltó.
- Mientras llega el cuadro nuevo se ve el anterior de ese clip, no un negro.
  Al reproducir se adelantan 8 cuadros, y si el hilo se atrasa se sueltan
  cuadros: el reloj manda.
- Un cuadro que falla se recuerda, para no volverlo a pedir en cada
  repintado.
- La exportación todavía decodifica en orden en el hilo de la interfaz.
  Sacarla de ahí es la cola de render, del nivel 2.

### Importar y sondeo de medios

- El sondeo lee duración, resolución, fps, códecs, canales y frecuencia, y
  distingue video, audio e imagen por el contenido y no por la extensión.
  Un MP3 con carátula se reconoce como audio.
- Se guarda en el proyecto con el tamaño y la fecha del archivo: mientras no
  cambien, no se vuelve a abrir el contenedor.
- Se pueden importar MP3, WAV, FLAC, M4A, AAC, OGG y Opus. Caen en la
  primera pista de audio libre en ese tramo.

### Onda y audio con NumPy

- La onda guarda mínimo y máximo por cubo, así se dibuja con su forma real.
  Se calcula al importar y se guarda como .npy en la caché del sistema:
  al volver a abrir el proyecto no se decodifica otra vez, y el zoom nunca
  la recalcula.
- Los fundidos y el volumen se aplican muestra por muestra. Antes el nivel
  se calculaba una vez por segundo, y un fundido de tres segundos eran tres
  escalones.

### Atajos configurables

- Cada acción tiene una clave y la tecla sale de un mapa, guardado en
  atajos.json en la carpeta de configuración. Editar → Atajos de teclado
  abre un editor con buscador.
- Se valida al cargar: nada con Ctrl+Alt, que es AltGr en teclado
  latinoamericano; nunca dos acciones con la misma tecla; un archivo dañado
  no impide abrir el editor.
- Las flechas, Inicio y Fin pasaron de estar escritas en el código a ser
  acciones configurables. Se apagan al escribir aunque lleven Ctrl, porque
  Ctrl+← salta una palabra dentro de un subtítulo.

### Dividir, slip y capa de comandos

- S divide en el playhead.
- Herramienta slip (Y): cambia qué pedazo del archivo se ve sin mover ni
  estirar el clip. Alt+, y Alt+. deslizan de a un cuadro.
- Cada edición es un comando con nombre encima del historial de
  instantáneas, que se queda como estaba. Es lo que después va a usar la
  consola de scripts y el agente con IA.
- El imán también pega a los marcadores.

### Exportar con presets

- Tamaño de la secuencia, H.264 1080p, H.264 4K y solo audio en AAC.
  "1080p" es el lado corto: un vertical sale de 1080 × 1920.
- Se compone directo al tamaño de salida, así el texto sale nítido.
- "Exportado" pasó de diálogo modal a la barra de estado.

### Autoguardado

- Cada 30 segundos, si hay cambios, una copia en la carpeta de datos del
  sistema, nunca encima del proyecto. Se borra al guardar o al cerrar
  normalmente; si el programa truena, se queda y se ofrece al arrancar.
- Una copia más vieja que su proyecto guardado no se ofrece.

### Arreglado

- **El último segundo de audio se perdía.** Un clip que llegaba al final de
  su archivo perdía hasta un segundo del cierre, en el play y en la
  exportación: el FIFO solo soltaba bloques completos.
- **Volumen o fundido en el play sonaban a ruido.** El filtro volume
  devolvía flotantes aunque el play pide enteros de 16 bits.
- **Recolorear en pausa avanzaba un cuadro.** El decodificador comparaba
  solo cuatro ajustes de color; mover la temperatura, la viñeta o la curva
  decodificaba el cuadro siguiente.
- **Cortar sin selección solo cortaba una pista**: el video quedaba partido
  y su audio no.
- **Dividir un clip** ignoraba la velocidad, rompía la animación por
  keyframes, duplicaba los fundidos y heredaba la transición cruzada.
- El diálogo de exportar decía que el audio no suena al editar, y hace dos
  versiones que sí suena.
- El .spec de PyInstaller excluía NumPy: el ejecutable habría tronado.

### Por dentro

- **Stack híbrido.** Del stack base del roadmap se adoptó lo que mejora de
  verdad y funciona en la máquina: decodificación en hilo con PyAV y NumPy
  para el audio. Se quedaron el timeline dibujado con QPainter, el
  compositor y el audio con Qt, porque ya funcionan y reescribirlos no
  agrega funciones. moderngl no tiene versión para Python 3.14, y
  QOpenGLWidget no pinta sin pantalla, así que dejaría el preview sin
  pruebas; la GPU queda para cuando haya cómo probarla.
- **Deshacer sigue con instantáneas**, con la capa de comandos encima.
- NumPy entra como dependencia.
- 493 pruebas en 43 segundos. Cada pieza nueva corrió sus pruebas tres veces
  seguidas; las del hilo, trece.
- El banco aísla la caché, la configuración y los datos en carpetas
  desechables, para no tocar nunca los del usuario.

## [0.2.0a1] — 2026-09-12

**Sigue en pre-alfa.** Pasa 288 pruebas automáticas —121 más que la entrega
anterior— pero nadie la ha usado con material propio de verdad.

**El formato del archivo subió a la versión 2.** Los proyectos de la
`0.1.0a1` abren sin problema y sus campos nuevos se llenan con su valor
neutro. Al revés no: la `0.1.0a1` se niega a abrir un proyecto de esta, con
un aviso claro en vez de abrirlo a medias y perder los ajustes al guardar.

**Sigue sin ejecutables.** No hay `.exe` ni binario de Linux.

### Mezcla de audio — el bug más caro de esta entrega

- **Dos clips de audio encimados ahora se oyen los dos.** Antes no. El
  renderizador iba hacia adelante y nunca regresaba, así que cuando llegaba
  el segundo clip el cursor ya iba pasado y ese clip se perdía completo, sin
  ningún aviso: música y voz encimadas sonaban a música sola.
- Los clips se reparten en **carriles** sin traslape, cada carril se
  renderiza aparte y los carriles se suman con `amix` de FFmpeg. Los
  carriles no son las pistas del timeline a propósito: así también se
  resuelve el caso de dos clips encimados dentro de la misma pista, que con
  una mezcla pista por pista se seguiría perdiendo.
- Con un solo carril no se monta ningún filtro. El caso común —una voz, una
  música, sin encimar— no paga nada por que exista la mezcla.
- `amix` lleva `normalize=0`. Por omisión divide entre el número de
  entradas, así que agregar una pista muda habría bajado a la mitad el
  volumen de las demás.
- La suma puede pasarse de 1.0 y recortar, igual que en Premiere. Se deja
  recortar en vez de meter un limitador: un limitador necesita mirar hacia
  adelante, y ese adelanto desfasaría el sonido de la imagen.

### Pistas de video apiladas

- **V1 y V2 se ven las dos.** Antes solo se pintaba la pista más alta con
  material, así que poner algo en V2 hacía desaparecer V1 por completo: no
  había manera de armar un cuadro dentro de cuadro, y un modo de fusión no
  habría tenido con qué fusionarse.
- `Ctrl+Shift+P` deja armado un cuadro dentro de cuadro de un clic, y
  "Llenar el cuadro" lo deshace.
- Las pistas de abajo se dejan de mirar en cuanto una de arriba las tapa del
  todo —opaca, sin máscara, sin fusión, sin fundido a medias y sin
  encogerse—. Sin esa cuenta, tener dos pistas costaría el doble de
  decodificación aunque la de abajo quedara invisible.

### Máscaras

- Cuatro formas: rectángulo, círculo, corte recto y ninguna. Con posición,
  tamaño, giro, suavizado del borde e invertir.
- La máscara se mide sobre el **cuadro de salida**, como en CapCut, no sobre
  la capa como en After Effects: uno la coloca mirando el preview, y si el
  clip se anima la máscara se queda donde la pusiste.
- El suavizado del borde se hace encogiendo y volviendo a estirar el mapa de
  opacidad. Suena a truco pero es exactamente un desenfoque de caja, lo hace
  Qt en C++ y sale gratis. El filtro `boxblur` de FFmpeg, que sería la otra
  opción, no viene en las ruedas de PyAV.
- La forma se dibuja sobre un lienzo más grande y luego se recorta. Sin ese
  margen el desenfoque también difuminaba las orillas del cuadro, y una
  máscara lineal que tapa media pantalla salía con los cuatro bordes
  lavados en vez de solo la línea del corte.
- Invertir no voltea pixeles: es el otro modo de composición
  (`DestinationOut` en vez de `DestinationIn`). Voltear una imagen
  premultiplicada da basura.
- Los mapas de opacidad se guardan en caché por tamaño y valores. Sin eso
  sería un desenfoque por cuadro.

### Modos de fusión

- Trece: multiplicar, oscurecer, subexponer, trama, aclarar, sobreexponer,
  sumar, superponer, luz fuerte, luz suave, diferencia, exclusión y normal.
- Se traducen a modos de composición de Qt, que los trae de fábrica: un modo
  de fusión no cuesta más que un dibujo normal.
- Un modo que esta versión no conozca se pinta normal. Más vale que la capa
  se vea de más que que desaparezca.

### Curva de color y viñeta

- Curva de cinco puntos —negros, sombras, medios, luces, blancos— con su
  gráfica al lado. La misma capacidad que una curva de DaVinci, sin puntos
  que arrastrar.
- Curvas listas: Contraste en S, Negros lavados, Abrir sombras, Bajar luces
  y Plano de cine.
- La gráfica dibuja exactamente lo que se le manda a FFmpeg. Se logra
  mandando la curva ya muestreada en diecisiete puntos: con los cinco
  anclajes pelones, el filtro `curves` interpolaría distinto y la gráfica
  mentiría un poco.
- La interpolación es Hermite monótona (Fritsch–Carlson) y no una spline
  natural: la natural se pasa del anclaje entre dos puntos separados, y eso
  aparece como un rebote de brillo donde el usuario no puso nada.
- Viñeta de 0 a 100, con el filtro `vignette`.
- Los looks de Cine, Noche, Vívido, Suave y Blanco y negro ahora traen curva
  —y los dos primeros también viñeta—. Con puros brillo y contraste el look
  se quedaba a medias.
- **La viñeta cuesta:** unos 12 ms por cuadro en 1080p, contra medio
  milisegundo de la curva. Es matemática por pixel, no una tabla. Con ella
  puesta el preview baja de unos 270 cuadros por segundo a unos 47: sigue
  reproduciendo de sobra a 30, pero es el ajuste más caro que hay.

### Animaciones de texto

- Diez de entrada y nueve de salida: aparecer, subir, escribiéndose,
  acercarse, alejarse, y deslizar desde los cuatro lados. Se escogen de una
  lista y se les pone cuánto duran.
- "Acercarse" se pasa un poco de tamaño y regresa. Ese sobretiro es lo que
  lo hace ver hecho a mano; sin él el texto solo crece y se ve barato.
- La máquina de escribir mide el ancho sobre el texto completo, no sobre el
  que ya se escribió: si se midiera sobre el visible, un texto centrado se
  iría acomodando letra por letra y se vería como un temblor.
- La salida no ofrece la máquina de escribir. Des-escribirse se ve como un
  error, no como un efecto.
- Si la entrada y la salida juntas no caben en el elemento, se reparten a
  prorrata. Encimadas, el texto nunca llegaría a estar quieto en su lugar.
- En el proyecto se guarda el nombre de la animación y su duración, no los
  keyframes que genera. Así, afinar una curva mejora los proyectos que ya
  existen en vez de romperlos.
- Las imágenes encima del video también las aceptan.

### Interfaz

- Pestaña nueva de **Máscara**, con la fusión arriba y la máscara abajo: se
  usan juntas, y en CapCut viven en el mismo lugar por la misma razón.
- La curva de color va en un grupo que arranca cerrado. Con ella a la vista,
  el panel de Color eran once deslizadores y ahí se acababa el "fácil de
  usar". El grupo se abre solo si el clip ya traía curva, para que un look de
  cine no deje escondido lo que le está haciendo a la imagen.
- Los controles que no aplican a la forma de máscara escogida se apagan. Un
  control encendido que no hace nada parece un programa roto.
- El campo de duración del texto se llama ahora "Duración del texto": en el
  mismo panel hay otra duración, la de la animación, y dos campos con el
  mismo nombre a la vista no se distinguen.

### Arreglado

- `amix` devolvía el formato que a él le acomodaba para sumar: se le pedía
  `s16` y salía `flt` empaquetado. Leído como enteros de 16 bits eso se oye
  como ruido blanco a todo volumen, y solo al darle play — la exportación se
  veía perfecta. Lo atrapó una prueba antes de salir.
- La serialización no reconstruía los dataclasses anidados: `clip.color`
  volvía siendo un `dict` y todo lo que le pedía un atributo tronaba, pero
  varios pasos después.
- Seleccionar un clip de audio dejaba encendida la pestaña de Máscara con el
  panel vacío.

### Por dentro

- 288 pruebas automáticas que corren en 27 segundos sin abrir ventanas.
- El modelo sigue siendo Python puro: las animaciones de texto, la curva y
  la máscara se prueban sin Qt. La traducción a Qt —modos de composición y
  mapas de opacidad— vive toda en el compositor.
- Un solo compositor para el preview y la exportación, ahora también para
  las máscaras y la fusión. Hay pruebas que comprueban que la máscara sale
  quemada en el archivo final.

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
