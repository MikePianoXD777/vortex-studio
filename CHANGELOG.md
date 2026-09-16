# Changelog

**Español** · [English](CHANGELOG.en.md)

Todo lo que cambia en Vortex Studio, de lo más nuevo a lo más viejo.

Las versiones siguen [versionado semántico](https://semver.org/lang/es/):
`MAYOR.MENOR.PARCHE`. Mientras estemos en `0.x`, cualquier versión menor
puede romper compatibilidad.

## [Sin publicar]

Nada todavía.

## [0.1.0] — 2026-09-15

**Sale de la beta.** Antes de decirle estable se revisó el editor completo
—modelo, medios, ventana, paneles y empaquetado— y se le metió al banco de
pruebas material del mundo real, del que no se porta bien: video vertical de
celular, 29.97 fps con keyframes cada varios segundos, HEVC, 44.1 kHz, fps
variable, resolución impar y archivos cuyo tiempo no empieza en cero. De ahí
salió todo lo de abajo. Pasa 1305 pruebas automáticas y el banco completo
corrió tres veces seguidas antes de publicar.

### Ya no se pierde trabajo

- **Cancelar una exportación borraba el archivo que ya estaba en el destino.**
  Si exportabas encima de la entrega anterior y te arrepentías, se iba la
  vieja también. Ahora se escribe aparte y se mueve al final: lo que había
  solo se reemplaza cuando el archivo nuevo está completo.
- **Exportar encima del material del proyecto** destruía el original y sacaba
  la exportación dañada. Ahora avisa y no deja.
- **Volver a una versión guardada, o fusionar con otra copia**, reemplazaba el
  proyecto sin preguntar y sin dejar deshacer. Ahora pregunta, como Abrir.
- **Duplicar (Ctrl+D)** se llevaba el clip de junto. Ahora lo recorre.
- **Congelar cuadro** se comía el resto del clip; ya lo conserva.
- **Archivo › Importar** metía el audio del video encima de lo que hubiera en
  la primera pista; ahora busca una libre o agrega otra.
- **Soltar material sobre una pista bloqueada** lo metía en otra pista y
  partía lo que hubiera ahí. Ahora avisa y no toca nada.
- **Un «Guardar como» que falla** dejaba el proyecto apuntando a la ruta
  imposible.
- **Un nombre con puntos** («Entrevista v1.2») se guardaba en otro archivo, y
  dos nombres distintos podían terminar en el mismo.
- **Decir que no a recuperar** borraba la copia automática para siempre; ahora
  se queda hasta que guardes.
- **El candado de la pista** no protegía contra los paneles de la derecha ni
  contra el botón de borrar texto.

### Se ve y suena como debe

- **Video vertical de celular**: se veía acostado. Ahora se lee la marca de
  giro del archivo —también en los proxies— y el cuadro sale derecho.
- **Fotos de celular**: entraban acostadas; ahora se aplica su orientación.
- **Archivos cuyo tiempo no empieza en cero** (material de cámara, `.ts`,
  capturadoras) se veían congelados en su primer cuadro.
- **En cámara lenta el audio se adelantaba a la imagen** hasta 101 ms; ahora
  queda dentro de 7 ms.
- **Exportar a 29.97** ya salía bien desde la 0.1.0b3; ahora la caché de
  render también, que se corría un cuadro cada 33 segundos.
- **Recortar un clip enlazado** dejaba su audio encimado con el clip de junto
  y desfasado.
- **El imán** se pegaba al propio audio enlazado y el recorte iba a trinquete.
- **El audio de una secuencia anidada** ignoraba la velocidad de la anidada.

### Controles que hacen lo que dicen

- **Escribir la velocidad o la duración de la transición** en su casilla no se
  aplicaba: solo servía arrastrar la manija.
- **El editor de keyframes** se disparaba al arrastrar un punto: la escala se
  recalculaba sola y el valor se escapaba del cursor.
- **El combo de Look** conservaba el del clip anterior, y volver a elegir ese
  mismo look no hacía nada.
- **El botón Agregar del panel de medios** estaba prendido sin selección.
- **Borrar la selección** dejaba los paneles editando un clip que ya no
  existía.
- **Las marcas de entrada y salida** se quedaban al cambiar de secuencia o de
  proyecto, y exportar sacaba negro.
- **Cada secuencia conserva su deshacer**: antes cambiar de secuencia lo
  borraba.
- **Quitar un keyframe** se llevaba a los vecinos a 60 fps.
- **Pegar atributos › Velocidad** sobre un clip con remapeo lo acortaba sin
  cambiarle la velocidad.
- **Quitar remapeo, congelar y cambiar de velocidad** ya no dejan clips de
  duración cero.
- **Estirar la cabeza de un clip** más allá del primer cuadro del material
  corría todo su contenido.
- **El código de tiempo del EDL** no cuadraba con el del editor en 29.97.
- **Normalizar, la multicámara y los proxies** ya se comportan como dicen
  (viene de la 0.1.0b3).

### Arranque, instalación y compilación

- **Si algo truena antes de que salga la ventana**, queda apuntado en
  `~/.cache/vortex-studio/error.log` y sale un aviso. En Windows era doble
  clic y nada.
- **El instalador de Windows** ahora borra la instalación anterior antes de
  copiar: mezclar bibliotecas de dos versiones dejaba el editor sin abrir.
- **El instalador de Linux** ya no se borra a sí mismo si lo corres desde la
  carpeta de destino, y la entrada del menú aguanta un `%` en la ruta.
- **La compilación automática** no publica nada sin antes comprobar que el tag
  y la versión del código coinciden y que el banco completo pasa.
- **La revisión a fondo del binario** marca falla si el paquete salió sin OCIO
  o sin AAF, en vez de decir que todo bien.
- Un proyecto editado a mano con datos imposibles ahora se rechaza con un
  aviso claro en vez de un error crudo.


## [0.1.0b3] — 2026-09-13

**El parche del QA a mano.** La `0.1.0b2` se probó en Linux con una hoja de
359 pruebas, una por cada función del editor: a mano las primeras áreas y
de forma automática, contra el mismo código, todas las demás. Salieron 23
fallas, y aquí van arregladas las que estorbaban al editar. Pasa 1225
pruebas automáticas y el banco completo corrió tres veces seguidas antes de
publicar.

### Arreglado

- **La reproducción daba tirones**, sobre todo con clips de celular o de
  sitios como Pexels, que traen keyframes cada varios segundos. Se sumaban
  tres cosas: el decodificador volvía a buscar el keyframe casi en cada
  revisión del reloj, a 29.97 fps repetía unos cuadros y brincaba otros, y
  el reloj revisaba al mismo ritmo que los cuadros. Con un 1080p vertical a
  29.97 se pasó de 82 búsquedas en 6 segundos a ninguna, y los cuadros ya
  llegan parejos.
- **Entre dos cuadros se veía el siguiente.** En cámara lenta con «Cuadro
  más cercano» la imagen iba un cuadro adelantada; la mezcla de cuadros y el
  flujo óptico mezclaban los vecinos equivocados, también en la zona
  renderizada; y en el monitor la estabilización corregía con un cuadro de
  retraso.
- **Exportar a 29.97** sacaba el video a 30 fps, y la imagen se iba
  adelantando al audio 67 ms por minuto. Ahora sale a 30000/1001, y lo mismo
  con 23.976 y 59.94.
- **Marcadores**: los puestos con `M` o `Alt+Shift+M` se guardaban con
  nombre `False`, y su diálogo tronaba al editarlos o al darles doble clic.
  Los proyectos que ya los traen abren bien.
- **Guardar versión…** tronaba siempre, antes de pedir el nombre.
- **Congelar cuadro** se comía el resto del clip y dejaba su audio sonando
  sin imagen. Ahora mete 2 segundos congelados y recorre lo que sigue, con su
  audio.
- **Quitar remapeo** dejaba el clip a la velocidad promedio de la curva —por
  ejemplo 1.67×— en vez de regresarlo a 1×.
- **Mantener tono y Silenciar**, en la pestaña Clip, no llegaban al audio
  enlazado cuando estaba seleccionado el video.
- **Una secuencia anidada se podía pegar dentro de sí misma** con copiar y
  pegar.
- **Ajustar al primer clip** tomaba el tamaño pero no los fps.
- **Ajustar timeline** dejaba el final de la secuencia fuera de la vista.
- **El volumen** arrancaba al 100 % aunque el deslizador dijera 80.
- **Texto en las orillas**: las posiciones de izquierda y derecha cortaban
  el texto. Ahora se alinea hacia su orilla.
- **Llenar el cuadro** con una imagen horizontal en una secuencia vertical
  cubría un tercio. Ahora la cubre completa.
- **Proxies**: un video importado con los proxies prendidos no usaba el
  suyo hasta apagarlos y volver a prenderlos.
- **La multicámara** se pintaba en el timeline como video normal; ahora
  lleva el color de las anidadas.
- **Normalizar** decía que había llegado a la sonoridad aunque el material
  fuera tan bajo que no alcanzaba.

### Agregado

- **Soltar archivos desde el gestor de archivos** —Dolphin, Nautilus, el
  explorador de Windows— directo al timeline.
- **Archivos faltantes**: al abrir un proyecto cuyo material se movió, sale
  un aviso con la lista y la opción de buscarlo por nombre en otra carpeta.
  Sus clips quedan rayados en rojo en el timeline, con «Falta».
- **Efectos propios mal escritos** se avisan en la pestaña Efectos, en vez
  de desaparecer sin explicación.
- **Archivos incompletos**: un video cuya descarga se cortó avisa que parece
  incompleto, en vez de «moov atom not found».

## [0.1.0b2] — 2026-09-13

**Parche de los ejecutables.** Se buscaron bugs en los binarios de la
`0.1.0b1` usándolos ya empacados, y apareció uno que impedía abrir el editor
en Linux con X11. Pasa 1152 pruebas automáticas y el banco completo
corrió tres veces seguidas antes de publicar.

### Arreglado

- **Linux: el editor no abría en sesiones X11** —Ubuntu 22.04 con tarjeta
  NVIDIA, Linux Mint, XFCE o cualquier escritorio sin Wayland— cuando al
  sistema le faltaban `libxcb-cursor0` y otras bibliotecas de X11 que pide
  Qt 6. Tronaba con "could not load the Qt platform plugin xcb" antes de
  mostrar nada. Ahora esas bibliotecas vienen dentro del paquete. En Wayland
  no pasaba.

### Agregado

- **`vortex-studio --self-check`**, una revisión a fondo del editor empacado.
  Crea su propio material y lo usa como lo haría alguien: importa, reproduce,
  busca escenas y silencios, pone subtítulos, exporta, renderiza en paralelo,
  escribe EDL, XML y AAF, convierte HDR y OCIO, estabiliza, guarda y abre.
  Dice cómo le fue en cada paso. Todo lo que escribe va a una carpeta
  temporal.
- La compilación de cada versión corre esa revisión en Windows y en Linux
  antes de publicar. En Linux, además, quita del sistema las bibliotecas de
  X11 y abre el editor en un X virtual, para comprobar que de verdad viajan
  en el paquete.
- Los binarios se pueden compilar de prueba en GitHub Actions sin tocar
  ninguna release.

## [0.1.0b1] — 2026-09-13

**La beta: diseño nuevo y ejecutables.** Vortex Studio sale de la pre-alfa.
La ventana se rediseñó completa para que se vea como editor y no como
reproductor, y por primera vez hay descarga lista para usar: instalador para
Windows y paquete para Linux que se agrega al menú de aplicaciones. Pasa
1121 pruebas automáticas y el banco completo corrió tres veces seguidas
antes de publicar.

### La numeración vuelve a empezar

La beta reinicia la cuenta en `0.1`. Las pre-alfas fueron de la `0.1.0a1` a
la `0.6.0a1`; esta `0.1.0b1` trae todo lo de ellas. Si instalaste desde el
código con `pip install .` (sin `-e`), pip cree que la `0.6.0a1` es más
nueva: reinstala con `pip install --force-reinstall .`.

El formato del archivo `.vortex` sigue en la versión 6: todos los proyectos
de las pre-alfas abren igual.

### Diseño nuevo

- **Fondo casi negro y cada zona en su tarjeta** redondeada: medios, monitor,
  timeline y propiedades. El acento es blanco; el rojo queda solo para el
  playhead.
- **Barra superior** con los menús, el nombre del proyecto, tamaño y cuadros
  por segundo, y **Exportar** a la vista.
- **Transporte mínimo** bajo el monitor: código de tiempo, inicio, play,
  final, cuadro a cuadro, repetir, velocidad y volumen en una sola línea. El
  cuadro del monitor lleva esquinas redondeadas.
- **Herramientas sobre el timeline**: Selección, Cortar, Dividir y Deslizar,
  más **Imán** y **Enlace**, que ahora se pueden apagar. Junto a ellas, cuántos
  elementos tiene la secuencia.
- **Timeline** con regla en `00:04`, cabeceras de pista mínimas, clips de
  color por tipo —texto ámbar, video azul, audio verde— y la onda en barras.
- **Medios** con pestañas Medios, Audio y Texto, tarjetas con la duración y
  una tarjeta para importar. La pestaña Texto agrega un texto abajo, al
  centro o arriba, o importa subtítulos.
- **Propiedades** con las ocho pestañas en píldora. Los valores se leen como
  lo que son (`1.2` segundos, `1.50×`) y se pueden escribir. "Mantener tono"
  y "Silenciar audio" son interruptores.
- **Paneles despegables** con barra delgada para arrastrarlos, despegarlos o
  cerrarlos.
- **Íconos dibujados**, iguales en Windows y Linux, en vez de caracteres que
  dependían de las fuentes del sistema.
- La pantalla de inicio y la de carga, con los mismos colores.
- **Ícono de la aplicación** para la ventana, la barra de tareas y el menú.

### Ejecutables

- **Windows**: instalador (`…-windows-x64-instalador.exe`), que agrega Vortex
  Studio al menú Inicio sin pedir permisos de administrador, o versión
  portátil en `.zip`.
- **Linux**: `…-linux-x86_64.tar.gz` con `instalar.sh`, que lo pone en tu
  carpeta personal, lo agrega al menú de aplicaciones y deja el comando
  `vortex-studio`. `desinstalar.sh` lo quita sin tocar tus proyectos. Hace
  falta una distribución con glibc 2.35 o más nueva (Ubuntu 22.04 en
  adelante).
- Los ejecutables **no están firmados**. Windows puede avisar con SmartScreen:
  "Más información → Ejecutar de todas formas".
- Se compilan solos en GitHub Actions al publicar cada versión. Antes de
  subirlos, cada uno se abre con `--smoke-test`, que arma el editor completo
  sin pantalla; un ejecutable al que le falte una biblioteca no se publica.

## [0.6.0a1] — 2026-09-13

**El nivel 4 del roadmap: lo de editor profesional.** Remapeo de tiempo,
cuadros intermedios con flujo óptico, perspectiva 3D y corner pin,
seguimiento de movimiento, quitar silencios y cortar por escenas,
multicámara, efectos como plugins, versiones con fusión a tres vías, render
en paralelo, material HDR y OCIO, y exportar a EDL, XML y AAF. Antes de todo
eso se buscaron casos raros a propósito y salieron bugs reales, que también
quedaron arreglados. Sigue en pre-alfa: pasa 1000 pruebas automáticas
—258 más que la 0.5.0a1—, cada función con al menos tres pruebas
propias, y el banco completo corrió tres veces seguidas antes de publicar.

Lo del nivel 4 que necesita inteligencia artificial —transcripción, edición
por texto y subtítulos por voz— se queda para cuando se integre un LLM.

**El formato del archivo subió a la versión 6.** Los proyectos de la 0.1 a
la 0.5 abren sin problema. Al revés no.

**Sigue sin ejecutables.** Los binarios llegan al terminar la pre-alfa.

### Casos raros arreglados

- Un proyecto con un campo de más, un fps en cero o nulo, keyframes mal
  formados o números imposibles ya abre: lo que no se entiende se ignora o
  se corrige, y lo que de plano no es un proyecto se rechaza con un mensaje
  que dice qué pasa (y en qué línea se corta el JSON).
- **Guardar es atómico**: se escribe a un temporal y se reemplaza de un
  jalón. Antes un disco lleno a media escritura dejaba el proyecto cortado.
  Un proyecto de solo lectura ya no se sobrescribe.
- Un LUT dañado o un color de llave mal escrito ya no dejan el clip en
  negro.
- Un clip más largo que su archivo sostiene el último cuadro en vez de irse
  a negro, y los archivos cortos ya no truenan por fin de archivo al leerlos
  hacia adelante.
- Los SRT en Windows-1252 conservan sus acentos.
- Insertar video, audio, imagen o texto, y los menús de fundido, transición,
  congelar y keyframes, **respetan las pistas bloqueadas**.
- Al abrir un proyecto se avisa qué archivos faltan.
- Recortar la cabeza de un clip **recorre sus keyframes**: la animación sigue
  pegada a la imagen, como en Premiere.

### Tiempo

- **Remapeo de tiempo** (Clip → Remapeo de tiempo): desde el playhead, el clip
  va a 0.25×, 0.5×, normal, 2× o 4×, en reversa o congelado. Son keyframes de
  tiempo, así que se ven y se ajustan en el editor de keyframes. El audio
  enlazado queda mudo mientras tenga remapeo.
- **Cuadros intermedios en cámara lenta**: repetir el cuadro, mezclar los dos
  vecinos, o **flujo óptico** con `minterpolate`, que inventa el de en medio
  siguiendo el movimiento. El flujo óptico tarda más de un segundo por cuadro
  de 720p, así que su zona se marca en rojo para renderizarla.

### Imagen

- **Perspectiva 3D**: inclinar la capa hacia atrás o de lado, animable.
- **Corner pin**: mover cada esquina por separado para pegar un video en una
  pantalla. Los dos van en Transformar → 3D y esquinas.
- **Seguimiento de movimiento** (Clip → Detectar y seguir): se pone una
  máscara sobre el objeto y la máscara, o un texto, lo sigue. El resultado son
  keyframes: el cuadro donde se perdió se corrige a mano.
- **Efectos como plugins**: nitidez, desenfoque, grano, pixelado, aberración
  cromática, vibrancia, distorsión de lente, espejo, negativo y bordes, en la
  pestaña Efectos. Cualquiera puede agregar uno dejando un `.json` en la
  carpeta `plugins` de la configuración; solo se permiten filtros que
  trabajan cuadro por cuadro y sin archivos, con opciones validadas.
- **Material HDR y OCIO**: un video Rec.2020 PQ o HLG se detecta al importar y
  se convierte a Rec.709 con tonemapping. Con `opencolorio` instalado, cualquier
  espacio de color de OCIO sirve de entrada. La conversión se hornea a un LUT
  3D, porque `zscale` no viene en PyAV.

### Edición

- **Quitar silencios** del clip de un clic, con el audio y el video
  enlazados, cerrando los huecos.
- **Cambios de escena**: dividir el clip en cada corte, o poner un marcador.
  Un paneo rápido no cuenta como corte.
- **Multicámara** (Secuencia → Crear multicámara): varias cámaras
  sincronizadas por su audio o por su código de tiempo, y se corta entre
  ellas en vivo con `1` a `4`. Los cortes son keyframes sostenidos.

### Trabajar con otros

- **Versiones guardadas** junto al proyecto, para volver a como estaba.
- **Fusionar con otra copia**: si dos personas editaron copias de la misma
  versión, se juntan a tres vías por elemento. Si los dos cambiaron lo mismo,
  se queda lo tuyo y se reporta.
- **Candado**: si alguien más tiene abierto el proyecto en una carpeta
  compartida, se avisa al abrirlo.
- **Exportar la edición** a XML de Final Cut 7 (lo importan Premiere y
  Resolve), EDL CMX 3600 y AAF para Avid, este último con `pyaaf2`.

### Exportación

- **Render en paralelo**: el video se parte en segmentos que se exportan a la
  vez en varios núcleos y se unen sin volver a codificar.

### Dependencias opcionales

- `opencolorio` y `pyaaf2`: `pip install -e ".[pro]"`. Sin ellas el editor
  arranca igual; OCIO y AAF simplemente no aparecen.

## [0.5.0a1] — 2026-09-12

**El nivel 3 del roadmap, completo: producción seria.** Keyframes en
cualquier parámetro con editor de curvas, color con lift/gamma/gain y LUTs,
scopes, llave de croma, estabilización, capa de ajuste, efectos de audio con
normalización LUFS y ducking, secuencias anidadas, subtítulos SRT/VTT,
presets propios, exportar por marcadores y caché de render por zonas. Sigue
en pre-alfa: pasa 742 pruebas automáticas —134 más que la 0.4.0a1—, cada
función con al menos tres pruebas propias, pero nadie la ha usado con
material propio de verdad.

**El formato del archivo subió a la versión 5.** Los proyectos de la 0.1 a
la 0.4 abren sin problema, y sus keyframes se mueven igual. Al revés no.

**Sigue sin ejecutables.** Los binarios llegan al terminar la pre-alfa.

### Keyframes

- Interpolación **lineal, suave, sostenida y bezier** por tramo, con las
  manijas de la bezier arrastrables. Los keyframes viejos, sin
  interpolación escrita, usan la de antes.
- **Cualquier número se anima**: color, máscara, volumen, llave de croma,
  imágenes y textos. Si un valor ya está animado, mover su deslizador pone
  un keyframe en el playhead; los paneles no tuvieron que aprender nada de
  keyframes para eso.
- **Editor de keyframes** (`Shift+K`) con la curva del parámetro, arrastre
  en tiempo y valor, y doble clic para poner uno.
- Las máscaras animadas salen de aquí: sus seis valores se animan.

### Color

- **Exposición** y **tinte**, y **lift, gamma y gain** por canal. Van en la
  misma tabla de `lutrgb` de siempre, así que no le cuestan nada más a cada
  cuadro.
- **LUTs `.cube`** con intensidad: `lut3d` y, por debajo del 100 %, `split`
  + `mix`. Un LUT roto avisa al cargarlo; uno que ya no está no deja el clip
  en negro. Se guarda relativo al proyecto, igual que el material.
- **Scopes**: histograma, forma de onda y vectorscopio con NumPy sobre el
  cuadro compuesto reducido, sin esperar al decodificador.

### Efectos

- **Llave de croma** con `colorkey` y `despill`. La transparencia se separa
  antes de corregir color y se vuelve a juntar al final: varios filtros de
  color no saben de alfa y se la comían.
- **Estabilización** por correlación de fase: se analiza una vez, se guarda
  la trayectoria y se corrige cuadro por cuadro con un poco de zoom. No se
  usó `deshake` porque depende de los cuadros anteriores: el preview después
  de un salto y la exportación en orden no coincidirían.
- **Capa de ajuste**: corrige lo que tiene debajo con el mismo procesador de
  color de los clips, con opacidad, fusión y máscara.

### Audio

- **Ecualizador de tres bandas** y **compresor** por clip.
- **Normalización a LUFS** según BS.1770-4: ponderación K con `biquad` y los
  coeficientes de la norma, bloques de 400 ms y las dos compuertas. Un tono
  de referencia mide exacto.
- **Ducking**: una pista de Voz baja sola a la de Música, muestra por
  muestra y sin escalones entre bloques.

### Secuencias, subtítulos y exportación

- **Secuencias anidadas**: anidar la selección, insertar una secuencia,
  entrar con doble clic. Se detectan los ciclos y el menú ni los ofrece. Se
  ven en el preview —se componen en el hilo del decodificador—, suenan y se
  exportan.
- **Subtítulos SRT y VTT**, de ida y de vuelta, con los detalles que rompen
  un importador ingenuo: coma contra punto, horas omitidas, ajustes de VTT,
  etiquetas, BOM y fines de línea de Windows.
- **Presets propios** con tamaño, calidad y cuadros por segundo, guardados
  en `presets.json`. Los de fábrica no se pisan.
- **Exportar por marcadores**: un archivo por tramo, todos a la cola.

### Caché de render por zonas

- La línea de tiempo se parte en zonas y cada una tiene nivel y **firma**:
  un hash de todo lo que vive en ella y de los archivos que usa. La barra
  bajo la regla va en rojo, amarillo o verde. `Enter` renderiza las rojas y
  el preview las reproduce desde el archivo. Si cambia la firma, la zona
  vuelve a rojo sola.

### Arreglado

- El ecualizador subía la mitad de lo que decía: una repisa da la mitad de
  su ganancia en su frecuencia de esquina, y las esquinas estaban donde
  debía ir la banda completa.

## [0.4.0a1] — 2026-09-12

**El nivel 2 del roadmap, completo: usable a diario.** Lo que se usa todos
los días al editar y que faltaba: encuadre para pasar de horizontal a
vertical, fundidos a color, audio que respeta la velocidad, enlace de video
y audio, portapapeles, interruptores de pista, panel de medios, proxies y
exportar sin detener la edición. Sigue en pre-alfa: pasa 608 pruebas
automáticas —115 más que la 0.3.0a1—, pero nadie la ha usado con material
propio de verdad.

**El formato del archivo subió a la versión 4.** Los proyectos de la 0.1 a
la 0.3 abren sin problema. Al revés no.

**Un cambio que se nota en proyectos viejos:** el material de otra
proporción que la secuencia se **estiraba** para llenar el cuadro. Era un
error y ya no pasa: los clips entran en modo Ajustar, con franjas. Si
querías el cuadro lleno, Secuencia → Rellenar el cuadro con todos los clips.

**Sigue sin ejecutables.** Los binarios llegan al terminar la pre-alfa.

### Audio a otra velocidad

- **Arreglado:** el audio de un clip con velocidad distinta de 1× se leía a
  velocidad normal. Un clip a 2× sonaba el doble de largo que su imagen, y
  todo lo que venía detrás en la pista se desfasaba. También se leía desde
  el punto equivocado del archivo cuando la lectura empezaba a media clip.
- Cada clip elige qué hace su sonido: **Mantener tono** (`atempo`, lo que
  hace Premiere), **Cambiar tono** (`asetrate`, como una cinta) o
  **Silenciar**. El audio dura exactamente lo que la imagen, muestra por
  muestra.
- El rango de velocidad es de 0.25× a 4×.

### Encuadre, recorte y punto de anclaje

- Tres modos por clip: **Ajustar**, **Rellenar** y **Estirar**. Rellenar es
  cómo se hace un vertical a partir de un horizontal, y hay un comando para
  aplicarlo a todos los clips de un jalón.
- Recorte por orilla, al estilo del efecto Recortar de Premiere: lo
  recortado queda transparente y la imagen no se mueve de lugar.
- Punto de anclaje, con nueve posiciones listas: el clip crece y gira desde
  ahí sin desplazarse.
- Nada se pinta fuera del cuadro en el preview, aunque el clip esté
  rellenado o crecido.

### Transiciones

- **Fundido a negro** y **a blanco**, además de la cruzada. En la primera
  mitad el clip que sale se cubre de color y en la segunda se descubre el
  que entra, sin mezclar los dos.

### Títulos

- Fuente, color y grosor del contorno, y sombra con color, distancia,
  desenfoque y opacidad. La sombra desenfocada usa el mismo truco de las
  máscaras —encoger y volver a estirar—, que corre en C++.

### Enlace, portapapeles y pegar atributos

- El video y su audio entran **enlazados**: se mueven, recortan, cortan,
  deslizan, cambian de velocidad y se borran juntos. `Alt`+clic agarra un
  solo lado; `Ctrl+L` enlaza o desenlaza. Si se desfasan, el clip marca en
  rojo cuántos cuadros.
- Selección múltiple con `Ctrl`+clic, y lo seleccionado se arrastra junto.
- `Ctrl+C`, `Ctrl+X` y `Ctrl+V` para clips: se pega en el playhead, cada cosa
  en su pista, pisando lo de abajo, y el playhead queda al final para pegar
  otra vez detrás. Mientras se escribe en un cuadro de texto, esas teclas son
  del cuadro.
- `Ctrl+Shift+V` pega atributos: transformación, color, máscara y fusión,
  velocidad, volumen y fundidos, eligiendo cuáles.

### Pistas

- Botones en cada cabecera: mostrar y bloquear en video y texto; silenciar,
  solo y bloquear en audio. Una pista oculta no se pinta ni se exporta; una
  bloqueada no deja seleccionar, mover, cortar ni borrar lo que tiene. Solo
  manda y silencio gana, igual en el play que en el archivo.

### Marcadores

- Nombre, **nota** y **color**, en un diálogo que abre `Shift+M` o el doble
  clic sobre el marcador. La nota aparece al pasar el cursor.
- **Marcadores dentro del clip** (`Alt+Shift+M`), que viajan con él y se
  reparten al dividirlo.
- **Arreglado:** el nombre del marcador de la regla quedaba tapado por la
  primera pista y nunca se veía.

### Panel de medios y proxies

- **Panel de medios** a la izquierda: todo lo importado, con miniatura,
  buscador sin acentos ni mayúsculas y filtro por clase. Se arrastra a la
  pista que quieras o se agrega con doble clic. Las miniaturas se sacan en
  otro hilo y se guardan en la caché.
- **Proxies de 540p** con interruptor global, recordado entre sesiones. Se
  crean en segundo plano con un keyframe cada 15 cuadros —saltar es barato—
  y conservando las marcas de tiempo del original. El preview los usa; la
  exportación y el cuadro PNG leen siempre del original.

### Cola de render

- Exportar ya no detiene la edición: cada exportación va a una cola, con
  su copia congelada de la secuencia, su barra de progreso y su botón de
  cancelar. Un trabajo a la vez. Un error se reporta sin tumbar la cola.

### Cambiado

- Con un clip de audio seleccionado, la pestaña Transformar se apaga. Antes
  quedaba prendida con deslizadores que no hacían nada.

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
