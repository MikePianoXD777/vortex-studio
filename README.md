# Vortex Studio

**Español** · [English](README.en.md)

Editor de video no lineal. Parte de Vortex Suite.

Las funciones de DaVinci Resolve, CapCut, Premiere Pro y After Effects, pero
fáciles de usar. La capacidad sí; la complejidad no.

> ### ⚠️ Pre-alfa — `0.6.0a1`
>
> **Esto no está listo para trabajo real.** Pasa 1000 pruebas automáticas,
> pero nadie lo ha usado todavía con material propio de verdad. Eso no es lo
> mismo que estar probado.
>
> Lo que puedes esperar:
>
> - Cosas que fallan de formas que no hemos visto
> - El formato del archivo `.vortex` subió a la versión 6: los proyectos de
>   la 0.1 a la 0.5 abren bien, pero al revés no
> - El flujo óptico tarda más de un segundo por cuadro: renderiza su zona
>   con `Enter` antes de reproducir
> - La caché de render y los análisis de estabilización ocupan disco en la
>   caché del sistema; se pueden borrar sin perder nada
> - En las transiciones de video, el audio sigue cortando seco
>
> Úsalo para curiosear y para reportar lo que se rompa. No para editar algo
> que te importe sin respaldo.

> ### 📦 No hay descarga lista para usar
>
> **No publicamos ejecutables todavía.** No hay `.exe` para Windows ni
> binario para Linux: en este repo solo está el código fuente.
>
> Para usarlo **tienes que compilarlo tú**, y para eso necesitas Python 3.11
> o más nuevo. Los pasos están justo abajo. Toma un par de minutos la
> primera vez, casi todo bajando PySide6, que pesa unos 250 MB.
>
> Habrá binarios cuando esté más estable; en pre-alfa no tiene sentido
> publicarlos.

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
no lo necesita porque PyAV trae su propio FFmpeg. NumPy se instala solo con
las demás dependencias.

Opcionales: `opencolorio` (espacios de color de OCIO) y `pyaaf2` (exportar
AAF). Se instalan con `pip install -e ".[pro]"`; sin ellas el editor
arranca igual y esas dos opciones no aparecen.

## Scripts

```bash
./correr.sh       # corre la app desde el código, sin compilar
./probar.sh       # el banco de pruebas (acepta argumentos de pytest)
./construir.sh    # compila el ejecutable
```

En Windows: `construir.bat` y `probar.bat`. Los tres crean el entorno
virtual solos si no existe.

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
| `test_mezcla.py` | Que dos pistas de audio encimadas se sumen |
| `test_mascara.py` | Máscaras, su borde suave y su recorte |
| `test_fusion.py` | Pistas de video apiladas y modos de fusión |
| `test_curvas.py` | Curva de color de cinco puntos y viñeta |
| `test_animacion.py` | Animaciones de texto listas |
| `test_hilo.py` | Decodificación fuera del hilo de la interfaz |
| `test_medios.py` | Sondeo de medios, su caché y las migraciones |
| `test_onda.py` | Onda de audio con mínimo y máximo, y su caché en disco |
| `test_fundido_suave.py` | Volumen y fundidos muestra por muestra |
| `test_atajos_config.py` | Atajos configurables y su editor |
| `test_comandos.py` | Capa de comandos y qué se lleva cada mitad al dividir |
| `test_slip.py` | Herramienta slip e imán a marcadores |
| `test_presets.py` | Exportar en 1080p, 4K y solo audio |
| `test_autoguardado.py` | Autoguardado y recuperación |
| `test_exportar.py` | Que el archivo salga como se ve al editar |
| `test_clip.py` | Fundidos, velocidad, congelar cuadro |
| `test_marcadores.py` | Marcadores y su navegación |
| `test_atajos.py` | Atajos, paneles y barra de estado |
| `test_transicion.py` | Fundido cruzado entre clips |
| `test_reproduccion.py` | Sonido y sincronía con la imagen |
| `test_transformar.py` | Transformación y animación por keyframes |
| `test_looks.py` | Looks de color y formatos de secuencia |
| `test_panel.py` | El panel de pestañas y su cambio automático |
| `test_identidad.py` | Que dos elementos iguales sigan siendo distintos |
| `test_velocidad_audio.py` | Audio a otra velocidad: tono, duración exacta y sincronía |
| `test_encuadre.py` | Ajustar, rellenar, estirar, recorte y punto de anclaje |
| `test_transicion_color.py` | Fundido a negro y a blanco |
| `test_titulos_estilo.py` | Fuente, contorno y sombra de los títulos |
| `test_pistas.py` | Mostrar, bloquear, silenciar y solo por pista |
| `test_enlace.py` | Video y audio enlazados |
| `test_portapapeles.py` | Copiar, cortar, pegar y pegar atributos |
| `test_marcadores_clip.py` | Marcadores con nota y color, en la secuencia y en el clip |
| `test_panel_medios.py` | Panel de medios, miniaturas, búsqueda y arrastrar |
| `test_proxies.py` | Proxies de 540p y su interruptor |
| `test_cola_render.py` | Exportar en segundo plano, con progreso y cancelar |
| `test_keyframes.py` | Interpolación, cualquier parámetro animado y el editor de curvas |
| `test_color_avanzado.py` | Exposición, tinte, lift/gamma/gain y LUTs |
| `test_croma.py` | Llave de croma y supresión de derrame |
| `test_capa_ajuste.py` | Capas de ajuste |
| `test_scopes.py` | Histograma, forma de onda y vectorscopio |
| `test_subtitulos.py` | Importar y exportar SRT y VTT |
| `test_audio_fx.py` | Ecualizador, compresor, LUFS y ducking |
| `test_estabilizar.py` | Estabilización por correlación de fase |
| `test_rangos_y_anidado.py` | Tramos por marcadores y ciclos de anidadas |
| `test_anidadas.py` | Secuencias anidadas en la ventana |
| `test_presets_propios.py` | Presets propios y exportar por marcadores |
| `test_zonas_render.py` | Zonas de render y su firma |
| `test_cache_render.py` | Caché de render por zonas |
| `test_casos_raros.py` | Proyectos dañados, archivos que faltan, pistas bloqueadas, valores imposibles |
| `test_remapeo_tiempo.py` | Remapeo de tiempo y recortar la cabeza sin despegar la animación |
| `test_cuadros_intermedios.py` | Mezcla de cuadros y flujo óptico |
| `test_perspectiva.py` | Perspectiva 3D y corner pin |
| `test_seguimiento.py` | Seguimiento de movimiento con máscara y texto |
| `test_silencios_escenas.py` | Quitar silencios y detectar escenas |
| `test_multicamara.py` | Multicámara por audio y por código de tiempo |
| `test_plugins.py` | Efectos como plugins y su validación |
| `test_versiones_fusion.py` | Versiones, candado y fusión a tres vías |
| `test_intercambio.py` | EDL, XML de Final Cut y AAF |
| `test_hdr_ocio.py` | Material HDR y espacios de OCIO |
| `test_render_paralelo.py` | Render por segmentos en paralelo |
| `test_nivel4_ventana.py` | Lo del nivel 4 desde la ventana |
| `test_portabilidad.py` | Que funcione igual en Linux y Windows |

## Atajos

**Todos se pueden cambiar** en Editar → Atajos de teclado (`Ctrl+/`). Se
guardan en `atajos.json`, en la carpeta de configuración del sistema
(`~/.config/vortex-studio/` en Linux). El editor no deja poner `Ctrl+Alt`
—en teclado latinoamericano es AltGr— ni dos acciones con la misma tecla.

Estos son los de fábrica:

| Archivo | |
|---|---|
| `Ctrl+N` / `Ctrl+O` | Nuevo / abrir proyecto |
| `Ctrl+S` / `Ctrl+Shift+S` | Guardar / guardar como |
| `Ctrl+I` | Importar video, audio o imagen |
| `Ctrl+E` | Exportar (video o solo audio) |
| `Ctrl+Shift+E` | Exportar el cuadro actual a PNG |

| Editar | |
|---|---|
| `Ctrl+Z` / `Ctrl+Shift+Z` | Deshacer / rehacer |
| `V` / `C` / `Y` | Herramienta selección / navaja / deslizar (slip) |
| `S` / `Ctrl+K` | Dividir en el playhead |
| `Alt+,` / `Alt+.` | Deslizar el contenido un cuadro atrás / adelante |
| `Ctrl+D` | Duplicar |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copiar / cortar / pegar clips |
| `Ctrl+Shift+V` | Pegar atributos (color, transformación, velocidad…) |
| `Ctrl+L` | Enlazar o desenlazar video y audio |
| `Ctrl+/` | Atajos de teclado |
| `Ctrl+Shift+D` | Fundir entrada y salida del clip |
| `Ctrl+Shift+F` | Congelar el cuadro actual |
| `Ctrl+Shift+K` | Poner keyframe de toda la transformación |
| `Ctrl+Shift+P` | Cuadro dentro de cuadro |
| `Supr` / `Shift+Supr` | Eliminar / eliminar cerrando el hueco |
| `Ctrl+T` / `Ctrl+Shift+T` | Insertar texto / subtítulo |

| Reproducción | |
|---|---|
| `Espacio` | Reproducir / pausar |
| `←` `→` | Cuadro a cuadro |
| `Shift`+flechas / `Ctrl`+flechas | Saltar 1 s / 10 s |
| `Inicio` / `Fin` | Ir al inicio / al final |
| `J` `K` `Shift+L` | Más lento / normal / más rápido |
| `L` | Repetir |
| `Ctrl+Shift+A` / `Ctrl+Shift+B` | Transición cruzada / fundido a negro con el clip anterior |
| `I` `O` / `Ctrl+Shift+X` | Marcar entrada, salida / quitar marcas |
| `M` / `Shift+M` | Poner marcador / editarlo: nombre, nota y color |
| `Alt+Shift+M` | Marcador dentro del clip seleccionado |
| `Shift+K` | Editor de keyframes |
| `Enter` | Renderizar la zona (entre marcas, o todo) |
| `Ctrl+Shift+N` | Anidar la selección en una secuencia |
| `1` `2` `3` `4` | Cortar a esa cámara en una multicámara |
| `Shift+↓` `Shift+↑` | Marcador siguiente / anterior |
| `F` | Pantalla completa |

En el timeline: `Ctrl`+rueda hace zoom, arrastrar un clip lo mueve, arrastrar
sus bordes lo recorta, y todo se imanta a los cortes vecinos, al playhead y
a los marcadores. Con la herramienta slip (`Y`), arrastrar dentro de un clip
cambia qué pedazo del archivo se ve sin moverlo. `Ctrl`+clic suma clips a la
selección, `Alt`+clic agarra un solo lado de un par enlazado, y doble clic
en un marcador lo abre.

## Estructura

- `model/` — proyecto, secuencia, pistas, clips, textos, imágenes, color,
  historial y guardado. Python puro, sin Qt: se puede probar sin ventana.
- `media/` — decodificación y corrección de color con PyAV/FFmpeg.
- `ui/` — ventana, preview, timeline, transporte y paneles. El compositor
  vive aparte y lo comparten el preview y la exportación: es lo que garantiza
  que el archivo final se vea igual que lo que viste al editar.

## El panel de propiedades

Una sola ventana a la derecha con seis pestañas: Transformar, Color,
Máscara, Clip, Texto e Imagen. Antes eran varias ventanas acopladas
apiladas, que dejaban media pantalla en controles que casi nunca se tocan a
la vez.

La pestaña se cambia sola según lo que selecciones, pero solo cuando la de
ese momento no aplica: si ya estabas en Color, seleccionar otro clip te deja
en Color. Las que no aplican se apagan en vez de esconderse, para que no
bailen de lugar.

Adentro de cada pestaña se aplica la misma idea: lo que se usa a diario
queda a la vista y lo que se usa de vez en cuando —la curva de color— va en
un grupo que arranca cerrado y se abre con un clic.

## Animación

Cada clip tiene posición, tamaño, giro y opacidad, y cualquiera de las cuatro
se puede animar. La capacidad es la de After Effects; la interfaz no: cada
propiedad tiene su deslizador y un rombo al lado. Rombo apagado es valor
fijo; rombo encendido es keyframe donde está el playhead. Se anima poniendo
un rombo, moviendo el playhead y moviendo el deslizador. No hay gráfica de
curvas que aprender.

La interpolación suaviza la entrada y la salida de cada tramo. Un movimiento
lineal delata que lo hizo una máquina —arranca y frena de golpe—; esta curva
se ve intencional sin pedirle nada al usuario.

Los keyframes se guardan en tiempo relativo al inicio del clip, así que mover
el clip se lleva su animación pegada.

## Formatos y looks

El menú Secuencia cambia el cuadro a vertical 9:16, cuadrado, 4:5 o cine
21:9 de un clic. El material no se recorta: se acomoda dentro y lo que sobra
queda negro; desde ahí se encuadra con Transformar.

El panel de Color trae looks listos (Cálido, Frío, Cine, Vívido, Suave,
Blanco y negro, Noche). No son una capa aparte: escriben en los mismos
deslizadores, así que se puede partir de uno y seguir ajustando a mano.

## Curva de color y viñeta

La curva son cinco deslizadores —negros, sombras, medios, luces y blancos—
y una gráfica que dibuja lo que están haciendo. Es la misma capacidad que
una curva de DaVinci: cualquier curva en S, levantar las sombras sin quemar
las luces, el "film look" de negros lavados. Lo que no hay es puntos que
arrastrar, que es de lo que más asusta al abrir un editor por primera vez.

Vienen curvas listas: Contraste en S, Negros lavados, Abrir sombras, Bajar
luces y Plano de cine.

La gráfica dibuja exactamente la curva que se le manda a FFmpeg. Se logra
mandándola ya muestreada en diecisiete puntos: con los cinco anclajes
pelones, FFmpeg interpolaría distinto y la gráfica mentiría un poco.

La viñeta es un deslizador de 0 a 100 que cierra las esquinas. Junto con los
negros lavados es de donde sale la sensación de "se ve como película", y por
eso los looks de Cine y Noche ya la traen puesta.

**Cuesta.** La viñeta son unos 12 ms por cuadro en 1080p —matemática por
pixel, no una tabla— contra medio milisegundo de la curva. Con ella puesta
el preview baja de unos 270 cuadros por segundo a unos 47: sigue
reproduciendo de sobra a 30, pero es el ajuste más caro que hay.

## Máscaras y modos de fusión

Cuatro formas: rectángulo, círculo, un corte recto, o ninguna. Cada una con
posición, tamaño, giro, suavizado del borde e invertir. Con eso se cubre lo
que de verdad se usa —tapar una cara, revelar media pantalla, encerrar algo
en un círculo— sin un editor de trazados con puntos bezier.

La máscara se mide sobre el cuadro de salida, como en CapCut, no sobre la
capa como en After Effects. La diferencia importa: uno la coloca mirando el
preview, y si el clip se anima la máscara se queda donde la pusiste, que es
justo lo que se quiere al tapar algo que está quieto.

Los trece modos de fusión son los de siempre: multiplicar, trama,
superponer, oscurecer, aclarar, sobreexponer, subexponer, luz fuerte, luz
suave, diferencia, exclusión y sumar.

Para que un modo de fusión tenga con qué fusionarse, **las pistas de video
ahora se apilan**: V1 y V2 se ven las dos. Antes solo se pintaba la más alta
con material, así que poner algo en V2 hacía desaparecer V1 por completo.
`Ctrl+Shift+P` deja armado un cuadro dentro de cuadro de un clic.

Las pistas de abajo se dejan de mirar en cuanto una de arriba las tapa del
todo. Sin esa cuenta, tener dos pistas costaría el doble de decodificación
aunque la de abajo quedara invisible.

## Animación de texto

Diez animaciones de entrada y nueve de salida: aparecer, subir,
escribiéndose, acercarse, alejarse, y deslizar desde los cuatro lados. Se
escogen de una lista y se les pone cuánto duran; no hay keyframes que poner.

Es lo que hace rápido a CapCut, y en After Effects el mismo efecto son
cuatro keyframes por propiedad más una expresión para la máquina de
escribir.

La salida no ofrece la máquina de escribir a propósito: des-escribirse se ve
como un error, no como un efecto.

En el proyecto se guarda el nombre de la animación y su duración, no los
keyframes que genera. Así, afinar una curva mejora los proyectos que ya
existen en vez de romperlos.

## Uso diario

**Encuadre.** Cada clip trae su modo: *Ajustar* (entero, con franjas),
*Rellenar* (llena el cuadro y lo que sobra se sale) o *Estirar*. Para pasar un
horizontal a vertical: Secuencia → Vertical 9:16, y luego Secuencia →
Rellenar el cuadro con todos los clips. En Transformar → Encuadre y recorte
se recorta por orilla —lo recortado queda transparente, la imagen no se
mueve— y se elige el punto de anclaje desde el que el clip crece y gira.

**Transiciones.** Además de la cruzada, fundido a negro y a blanco. Se ponen
desde el menú Clip o en la pestaña Clip, donde también se cambia el tipo.

**Títulos.** Fuente, color, tamaño y alineación a la vista; contorno con
color y grosor, y sombra con color, distancia, desenfoque y opacidad en un
grupo aparte.

**Enlace.** El video y su audio entran enlazados: se mueven, recortan,
cortan, deslizan, cambian de velocidad y se borran juntos. `Alt`+clic agarra
uno solo, y `Ctrl+L` los desenlaza. Si se desfasan, el clip marca en rojo
cuántos cuadros.

**Portapapeles.** `Ctrl+C` y `Ctrl+V` pegan en el playhead, cada cosa en su
pista, y el playhead queda al final para pegar otra vez detrás. Lo pegado
pisa lo que haya abajo. `Ctrl+Shift+V` pega solo los ajustes que elijas.

**Pistas.** Cada cabecera tiene sus botones: mostrar y bloquear en video y
texto; silenciar, solo y bloquear en audio. Una pista bloqueada no deja
seleccionar, mover ni borrar nada de lo que tiene.

**Marcadores.** Llevan nombre, nota y color, en la regla o dentro de un clip.
Los del clip viajan con él. La nota aparece al pasar el cursor encima.

## Producción

**Keyframes en cualquier parámetro.** Color, máscara, volumen, llave de
croma, imágenes y textos, además de la transformación. Si un valor ya está
animado, mover su deslizador pone un keyframe donde está el playhead. El
editor de keyframes (`Shift+K`) muestra la curva de cada parámetro; los
keyframes se arrastran, y cada tramo es lineal, suave, sostenido o bezier,
con sus dos manijas.

**Color.** Exposición y tinte junto a lo de siempre, y las tres ruedas de
DaVinci —lift, gamma y gain— como deslizadores por canal. LUTs `.cube` con
intensidad. Los **scopes** (Ver → Scopes) dan histograma, forma de onda y
vectorscopio del cuadro compuesto.

**Efectos.** Llave de croma con similitud, suavidad y supresión de derrame.
**Estabilización**: la primera vez analiza el movimiento del video en
segundo plano y lo guarda; desde ahí la toma se corrige igual en el preview
y en la exportación, saltes a donde saltes.

**Capa de ajuste** (Insertar → Capa de ajuste): corrige el color de todo lo
que tiene debajo, con su opacidad y su máscara.

**Audio.** Ecualizador de tres bandas, compresor, normalización a −14, −16
o −23 LUFS según BS.1770, y ducking: marca una pista como Voz y otra como
Música, y la música baja sola cuando suena la voz.

**Secuencias anidadas.** `Ctrl+Shift+N` mete lo seleccionado en una
secuencia nueva y deja un clip en su lugar; doble clic lo abre. Una
secuencia no se deja meter en otra si eso hace un ciclo.

**Subtítulos.** Archivo → Importar subtítulos (SRT o VTT) los pone como
textos; Exportar subtítulos saca los textos de vuelta.

**Exportar.** Presets propios, con su tamaño, calidad y cuadros por segundo.
Exportar por marcadores manda un archivo por cada tramo entre marcadores a
la cola.

**Caché de render.** La barra bajo la regla dice qué zonas son pesadas
(rojo), ligeras (amarillo) o ya renderizadas (verde). `Enter` renderiza las
rojas y el preview las reproduce desde el archivo. Si cambias algo de una
zona, vuelve a rojo sola.

## Pro

**Remapeo de tiempo.** Clip → Remapeo de tiempo: desde el playhead el clip
va más lento, más rápido, en reversa o congelado, y lo de antes no cambia.
Son keyframes de tiempo, así que en el editor de keyframes se ve la curva y
se puede suavizar la rampa. En cámara lenta, la pestaña Clip elige los
cuadros intermedios: repetir, mezclar o **flujo óptico**.

**3D y esquinas.** En Transformar, inclinar la capa hacia atrás o de lado y
mover cada esquina, para pegar un video en una pantalla o una pared.

**Seguimiento.** Pon una máscara sobre el objeto y Clip → Detectar y seguir:
la máscara lo sigue, o el texto que esté en el playhead. Quedan keyframes,
uno por cuadro; si se perdió en algún lado, la barra de estado lo dice.

**Silencios y escenas.** Clip → Detectar y seguir también quita los
silencios del clip —con su audio enlazado, cerrando huecos— y parte un clip
en cada cambio de escena o le pone marcadores.

**Multicámara.** Secuencia → Crear multicámara: elige las cámaras de la
misma toma y se sincronizan por el audio o por el código de tiempo. Da play
y corta en vivo con `1` a `4`; se oye el audio de la primera cámara.

**Efectos.** La pestaña Efectos agrega efectos de una lista y los apila en
orden. Son plugins: un `.json` en la carpeta `plugins` de la configuración
(`~/.config/vortex-studio/plugins/` en Linux) con el filtro y sus controles
agrega uno nuevo sin tocar el código.

**HDR y OCIO.** Un video HDR se convierte solo a Rec.709 al importarlo; en
Color → Espacio de color del material se cambia, y con `opencolorio`
instalado ahí aparecen todos los espacios de OCIO.

**Versiones y fusión.** Archivo → Guardar versión deja una copia con nombre
junto al proyecto. Si alguien más editó una copia que salió de esa versión,
Archivo → Fusionar con otra copia junta los dos trabajos. Si alguien más
tiene abierto el proyecto en una carpeta compartida, se avisa.

**Llevar la edición a otro programa.** Archivo → Exportar edición escribe XML
(Premiere, Resolve, Final Cut), EDL o AAF (Avid). Viajan los cortes, no el
color ni los textos.

**Render en paralelo.** En el diálogo de exportar: parte el video en
segmentos, los exporta a la vez y los une sin volver a codificar.

## Sonido

Se oye mientras editas, con volumen y silencio en la barra de transporte. El
playhead se guía por lo que ya salió por la tarjeta, no por el reloj de la
interfaz: el audio no se puede acelerar ni saltar sin que se note, así que
manda él y la imagen lo sigue.

**Las pistas se mezclan de verdad.** Los clips se reparten en carriles sin
traslape, cada carril se renderiza aparte y los carriles se suman con `amix`.
Antes el renderizador iba hacia adelante y nunca regresaba, así que dos
clips encimados no se podían oír juntos: el segundo se perdía sin ningún
aviso. Los carriles no son las pistas del timeline a propósito, así también
se resuelve el caso de dos clips encimados dentro de la misma pista.

La suma puede pasarse y recortar, igual que en Premiere. Se deja recortar en
vez de meter un limitador porque un limitador necesita mirar hacia adelante,
y ese adelanto desfasaría el sonido de la imagen. Para eso está el volumen
por clip.

**A otra velocidad**, cada clip elige qué hace su sonido: *Mantener tono*
(como Premiere: la voz se oye natural), *Cambiar tono* (como una cinta: más
agudo al acelerar) o *Silenciar*. El rango es de 0.25× a 4×, y el audio dura
exactamente lo que la imagen.

## Preview fluido

La imagen se decodifica en un hilo aparte, nunca en el de la interfaz.
Antes, cada salto del playhead trababa la ventana mientras decodificaba;
medido con el decodificador ya abierto:

| Material | Antes | Ahora |
|---|---|---|
| 1080p | 26 ms por salto | 0.45 ms |
| 4K | 111 ms por salto | 0.57 ms |

Al arrastrar el playhead solo se decodifica donde lo sueltas, y mientras
llega el cuadro nuevo se ve el anterior. Al reproducir se adelantan ocho
cuadros; si el hilo se atrasa se sueltan cuadros y el sonido sigue mandando.

## Importar

`Ctrl+I` acepta video, audio e imagen, y decide a qué pista va por lo que
trae el archivo, no por su extensión. El audio suelto cae en la primera
pista de audio libre en ese tramo.

Todo lo importado queda en el **panel de medios**, a la izquierda, con
miniatura y buscador (sin acentos ni mayúsculas, y por clase). De ahí se
arrastra a la pista que quieras o se agrega con doble clic en el playhead.
Archivo → Importar al panel de medios trae varios archivos sin ponerlos en
el timeline.

**Proxies.** Ver → Usar proxies (540p) hace que el preview lea copias
livianas de los videos pesados; se crean solas en segundo plano. Exportar
lee siempre de los originales. El interruptor se recuerda entre sesiones.

Lo que se sabe de cada archivo —duración, resolución, códecs, canales— se
guarda en el proyecto, y no se vuelve a abrir mientras el archivo no cambie.
La onda de audio se guarda en la caché del sistema, así que al reabrir un
proyecto aparece al instante.

## Exportar

`Ctrl+E` escribe un MP4 (H.264) con todo quemado: cortes, textos, imágenes y
corrección de color. Si hay marcas de entrada y salida, exporta solo ese tramo.

La exportación va a la **cola de render** y se puede seguir editando: se
lleva una copia congelada de la secuencia, así que lo que edites después no
cambia el archivo. Cada trabajo tiene su barra y su botón de cancelar; el
archivo incompleto se borra.

## Autoguardado

Cada 30 segundos, si hay cambios sin guardar, se escribe una copia en la
carpeta de datos del sistema (`~/.local/share/vortex-studio/` en Linux),
**nunca encima de tu proyecto**. Si el programa se cierra de golpe, al
volver a abrirlo te ofrece recuperarla. Al guardar o al cerrar normalmente,
la copia se borra.

## Portabilidad

El proyecto `.vortex` guarda las rutas **relativas** cuando el material está
junto al proyecto o debajo de él, y siempre con barras normales. Así la
carpeta se puede mover, mandar a otra máquina o pasar de Linux a Windows y
sigue abriendo. Solo se guarda absoluta la ruta de material que vive fuera.

No hay ningún atajo con `Ctrl+Alt`: en Windows con teclado latinoamericano
`AltGr` manda exactamente eso, y escribir `@` o `\` dispararía comandos del
editor. Hay una prueba que lo vigila.

## Qué ya funciona

- Cortar, mover, recortar, duplicar y borrar en el timeline, con imantado
- Dividir con `S` y herramienta slip
- Preview que decodifica en un hilo aparte
- Importar audio suelto, con sondeo de medios en caché
- Deshacer y rehacer, con capa de comandos
- Autoguardado y recuperación
- Atajos configurables, con editor
- Texto y subtítulos, con contorno y caja
- Animaciones de texto listas, de entrada y de salida
- Imágenes sobre el video
- Corrección de color con looks de un clic
- Curva de color de cinco puntos, con su gráfica, y viñeta
- Máscaras de rectángulo, círculo y corte recto, con borde suave
- Trece modos de fusión, y pistas de video apiladas
- Cuadro dentro de cuadro de un clic
- Animación por keyframes de posición, tamaño, giro y opacidad
- Fundidos, fundido cruzado, a negro y a blanco, y congelar cuadro
- Velocidad de 0.25× a 4× con el audio sincronizado, manteniendo o cambiando
  el tono
- Encuadre ajustar, rellenar y estirar; recorte y punto de anclaje
- Títulos con fuente, contorno de color y sombra
- Video y audio enlazados; copiar, pegar y pegar atributos
- Mostrar, bloquear, silenciar y solo por pista
- Panel de medios con miniaturas, búsqueda y arrastrar al timeline
- Proxies de 540p con interruptor global
- Cola de render en segundo plano
- Keyframes en cualquier parámetro, con interpolación lineal, suave,
  sostenida y bezier, y editor de curvas
- Exposición, tinte, lift/gamma/gain y LUTs `.cube`; scopes
- Llave de croma, estabilización y capa de ajuste
- Ecualizador, compresor, normalización LUFS y ducking
- Secuencias anidadas, subtítulos SRT y VTT, presets propios, exportar por
  marcadores y caché de render por zonas
- Remapeo de tiempo, mezcla de cuadros y flujo óptico
- Perspectiva 3D y corner pin
- Seguimiento de movimiento, quitar silencios y cortar por escenas
- Multicámara por audio o por código de tiempo
- Efectos como plugins
- Versiones, fusión a tres vías y candado
- Material HDR y OCIO
- Render en paralelo y exportar la edición a XML, EDL y AAF
- Sonido al editar, con mezcla de pistas y onda en las pistas de audio
- Marcadores con nota y color, en la secuencia y dentro de los clips
- Formatos vertical, cuadrado y cine
- Exportar a MP4 en el tamaño de la secuencia, 1080p o 4K, solo audio, y el
  cuadro actual a PNG
- Guardar y abrir proyectos, portables entre carpetas y sistemas

## Licencia

[MIT](LICENSE). Puedes usarlo, modificarlo y distribuirlo, incluso en algo
comercial; lo único que se pide es conservar el aviso de copyright. Sin
garantía de ninguna clase — y en pre-alfa eso no es una fórmula legal, es
una advertencia literal.

## Pendiente

- En las transiciones de video, el audio corta seco: no hay fundido cruzado
  de audio.
- El sonido solo acompaña al reproducir con el transporte a velocidad normal
  (J-K-L); la velocidad de cada clip sí se oye.
- La selección múltiple es con `Ctrl`+clic; no hay selección con rectángulo.
- El desfase en rojo solo se calcula entre clips enlazados del mismo archivo.
- La cola exporta un trabajo a la vez, y salir del editor la cancela.
- La mezcla de audio recorta si la suma se pasa de 1.0, y no hay medidores
  para verlo venir.
- No hay cortinillas ni efectos de transición más allá de cruzada, a negro y
  a blanco.
- La viñeta es el ajuste más caro que hay: unos 12 ms por cuadro en 1080p.
- La máscara es de una sola forma por capa.
- El seguimiento sigue posición, no giro ni escala, y la máscara no se
  deforma con el objeto.
- Lo del nivel 4 que necesita IA —transcribir, editar por texto, subtítulos
  por voz— llega cuando se integre un LLM.
- La fusión junta por elemento; dos clips que quedan encimados se reportan
  pero no se acomodan solos.
- Cambiar de secuencia reinicia el deshacer, y deshacer no quita la
  secuencia que creó un "Anidar".
- La estabilización corrige desplazamiento, no giro ni zoom de la cámara.
- La barra de zonas solo mide la imagen; el audio no se renderiza a caché.
