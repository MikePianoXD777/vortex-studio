# Vortex Studio

**Español** · [English](README.en.md)

Editor de video no lineal. Parte de Vortex Suite.

Las funciones de DaVinci Resolve, CapCut, Premiere Pro y After Effects, pero
fáciles de usar. La capacidad sí; la complejidad no.

> ### ⚠️ Pre-alfa — `0.2.0a1`
>
> **Esto no está listo para trabajo real.** Pasa 286 pruebas automáticas,
> pero nadie lo ha usado todavía con material propio de verdad. Eso no es lo
> mismo que estar probado.
>
> Lo que puedes esperar:
>
> - Cosas que fallan de formas que no hemos visto
> - El formato del archivo `.vortex` subió a la versión 2 en esta entrega:
>   los proyectos de la `0.1.0a1` abren bien, pero al revés no
> - Material en 4K va a ir lento: la decodificación aún corre en el hilo de
>   la interfaz
> - La única transición sigue siendo el fundido cruzado
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
no lo necesita porque PyAV trae su propio FFmpeg.

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
| `Ctrl+Shift+K` | Poner keyframe de toda la transformación |
| `Ctrl+Shift+P` | Cuadro dentro de cuadro |
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

## Qué ya funciona

- Cortar, mover, recortar, duplicar y borrar en el timeline, con imantado
- Deshacer y rehacer
- Texto y subtítulos, con contorno y caja
- Animaciones de texto listas, de entrada y de salida
- Imágenes sobre el video
- Corrección de color con looks de un clic
- Curva de color de cinco puntos, con su gráfica, y viñeta
- Máscaras de rectángulo, círculo y corte recto, con borde suave
- Trece modos de fusión, y pistas de video apiladas
- Cuadro dentro de cuadro de un clic
- Animación por keyframes de posición, tamaño, giro y opacidad
- Fundidos, fundido cruzado, velocidad y congelar cuadro
- Sonido al editar, con mezcla de pistas y onda en las pistas de audio
- Marcadores
- Formatos vertical, cuadrado y cine
- Exportar a MP4 con audio, y el cuadro actual a PNG
- Guardar y abrir proyectos, portables entre carpetas y sistemas

## Licencia

[MIT](LICENSE). Puedes usarlo, modificarlo y distribuirlo, incluso en algo
comercial; lo único que se pide es conservar el aviso de copyright. Sin
garantía de ninguna clase — y en pre-alfa eso no es una fórmula legal, es
una advertencia literal.

## Pendiente

- La decodificación de imagen corre en el hilo de la interfaz: con 4K se va
  a arrastrar. Pide un rediseño con hilo de decodificación y buffer de
  cuadros, y es lo más grande que falta.
- El sonido solo acompaña a velocidad normal. A 2× saldría con el tono
  cambiado, que es peor que no oírlo.
- La mezcla de audio recorta si la suma se pasa de 1.0, y no hay medidores
  para verlo venir.
- La única transición es el fundido cruzado; no hay cortinillas ni efectos.
- La viñeta es el ajuste más caro que hay: unos 12 ms por cuadro en 1080p.
- La máscara es de una sola forma por capa, y sin animar.
- No hay máscaras animadas ni seguimiento de movimiento.
