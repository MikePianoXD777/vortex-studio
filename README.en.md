# Vortex Studio

[Español](README.md) · **English**

A non-linear video editor. Part of Vortex Suite.

The features of DaVinci Resolve, CapCut, Premiere Pro and After Effects, but
easy to use. The capability, yes; the complexity, no.

> ### 🧪 Beta — `0.1.0b1`
>
> **It's usable now, but it's a beta.** It passes 1121 automated tests
> and left pre-alpha with a new design and executables, but it still needs
> real footage to find what the tests don't see.
>
> What to expect:
>
> - Things breaking in ways we haven't seen: save often
> - Numbering started over: `0.1.0b1` is newer than `0.6.0a1` and opens all
>   of its projects
> - Optical flow takes over a second per frame: render its zone with `Enter`
>   before playing it back
> - The render cache and stabilization analyses take disk space in the
>   system cache; they can be deleted without losing anything
> - During video transitions, audio still hard-cuts
>
> Report what breaks in
> [Issues](https://github.com/MikePianoXD777/vortex-studio/issues).

## Download

Every version's executables are in
[Releases](https://github.com/MikePianoXD777/vortex-studio/releases).

**Windows** (64-bit):

- `VortexStudio-0.1.0b1-windows-x64-instalador.exe` installs it and adds it to
  the Start menu. No admin rights needed.
- `VortexStudio-0.1.0b1-windows-x64-portable.zip` is the portable version:
  unzip it and open `vortex-studio.exe`.

The executables aren't signed, so Windows may warn through SmartScreen:
**More info → Run anyway**.

**Linux** (x86_64, glibc 2.35 or newer: Ubuntu 22.04, Fedora 36, Debian 12 or
later):

```bash
tar xzf VortexStudio-0.1.0b1-linux-x86_64.tar.gz
cd VortexStudio-0.1.0b1-linux-x86_64
./instalar.sh
```

It shows up in your applications menu as **Vortex Studio**, and in the
terminal as `vortex-studio`. No password needed: everything goes in your
home folder. To remove it, run `~/.local/opt/vortex-studio/desinstalar.sh`;
your projects and settings are kept.

*(The script names are Spanish: install, uninstall.)*

**macOS** has no executable yet; run it from source, as below.

## Getting started from source

Linux and macOS:

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

Windows also has shortcuts: `construir.bat` builds the executable to
`dist\vortex-studio\vortex-studio.exe` and `probar.bat` runs the tests. Both
create the virtual environment if it's missing.

In VS Code it's the same on any system: `Ctrl+F5` runs, `F5` runs with the
debugger, `Ctrl+Shift+B` builds the executable and
`Ctrl+Shift+P → Run Test Task` runs the tests. The tasks carry their Windows
variant.

You need **ffmpeg on the PATH** only to run the tests; the application
doesn't, because PyAV ships its own FFmpeg.

Optional: `opencolorio` (OCIO color spaces) and `pyaaf2` (AAF export).
Install them with `pip install -e ".[pro]"`; without them the editor starts
the same and those two options don't show up.

## Scripts

```bash
./correr.sh       # run the app from source, no build
./probar.sh       # the test suite (takes pytest arguments)
./construir.sh    # build the executable
```

On Windows: `construir.bat` and `probar.bat`. All of them create the virtual
environment if it doesn't exist.

*(The script names are Spanish: run, test, build.)*

## What already works

- Cut, move, trim, duplicate and delete on the timeline, with snapping
- Split with `S` and a slip tool
- Preview decoding on its own thread
- Standalone audio import, with cached media probing
- Undo and redo, with a command layer
- Autosave and recovery
- Configurable shortcuts, with an editor
- Text and subtitles, with outline and caption box
- Ready-made text animations, in and out
- Images over the video
- Color correction with one-click looks
- A five-point color curve, with its graph, and a vignette
- Rectangle, ellipse and linear masks, with a soft edge
- Thirteen blend modes, and stacked video tracks
- One-click picture in picture
- Keyframe animation of position, scale, rotation and opacity
- Fades, cross dissolve, dip to black and to white, and freeze frame
- Speed from 0.25× to 4× with synced audio, keeping or shifting pitch
- Fit, fill and stretch framing; crop and anchor point
- Titles with font, colored outline and drop shadow
- Linked video and audio; copy, paste and paste attributes
- Show, lock, mute and solo per track
- Media bin with thumbnails, search and drag to the timeline
- 540p proxies with a global switch
- Background render queue
- Keyframes on any parameter, with linear, ease, hold and bezier
  interpolation, and a curve editor
- Exposure, tint, lift/gamma/gain and `.cube` LUTs; scopes
- Chroma key, stabilization and adjustment layers
- EQ, compressor, LUFS normalization and ducking
- Nested sequences, SRT and VTT subtitles, custom presets, export by markers
  and a zone render cache
- Time remapping, frame blending and optical flow
- 3D perspective and corner pin
- Motion tracking, silence removal and scene cuts
- Multicam synced by audio or timecode
- Effects as plugins
- Versions, three-way merge and project lock
- HDR and OCIO footage
- Parallel rendering and exporting the edit to XML, EDL and AAF
- Sound while editing, with track mixing and waveforms on the audio tracks
- Markers with notes and colors, on the sequence and inside clips
- Vertical, square and cinema formats
- Export to MP4 at sequence size, 1080p or 4K, audio only, and the current
  frame to PNG
- Save and open projects, portable across folders and systems

## Tests

```bash
./.venv/bin/python -m pytest -q
```

The suite generates its own footage with ffmpeg the first time and runs
without opening windows, so it works over SSH or on a headless machine.

| File | What it covers |
|---|---|
| `test_modelo.py` | Tracks, clips, timing, timecode |
| `test_guardado.py` | Round-trip of the .vortex file |
| `test_historial.py` | Undo, redo, branching |
| `test_edicion.py` | Cut, drag, trim, delete, duplicate |
| `test_color.py` | Brightness, contrast, saturation, gamma |
| `test_audio.py` | Waveforms and mixing with gaps |
| `test_mezcla.py` | That two overlapping audio tracks sum |
| `test_mascara.py` | Masks, their soft edge and their crop |
| `test_fusion.py` | Stacked video tracks and blend modes |
| `test_curvas.py` | The five-point color curve and the vignette |
| `test_animacion.py` | Ready-made text animations |
| `test_hilo.py` | Decoding off the UI thread |
| `test_medios.py` | Media probing, its cache and migrations |
| `test_onda.py` | Min/max audio waveform and its disk cache |
| `test_fundido_suave.py` | Per-sample gain and fades |
| `test_atajos_config.py` | Configurable shortcuts and their editor |
| `test_comandos.py` | Command layer, and what each half keeps on split |
| `test_slip.py` | Slip tool and snapping to markers |
| `test_presets.py` | Export at 1080p, 4K and audio only |
| `test_autoguardado.py` | Autosave and recovery |
| `test_exportar.py` | That the file comes out looking like the edit |
| `test_clip.py` | Fades, speed, freeze frame |
| `test_marcadores.py` | Markers and navigating them |
| `test_atajos.py` | Shortcuts, panels and status bar |
| `test_transicion.py` | Cross dissolve between clips |
| `test_reproduccion.py` | Sound and sync with the picture |
| `test_transformar.py` | Transform and keyframe animation |
| `test_looks.py` | Color looks and sequence formats |
| `test_panel.py` | The tabbed panel and its auto-switching |
| `test_identidad.py` | That two equal items stay distinct |
| `test_velocidad_audio.py` | Audio at other speeds: pitch, exact length and sync |
| `test_encuadre.py` | Fit, fill, stretch, crop and anchor point |
| `test_transicion_color.py` | Dip to black and to white |
| `test_titulos_estilo.py` | Title font, outline and shadow |
| `test_pistas.py` | Show, lock, mute and solo per track |
| `test_enlace.py` | Linked video and audio |
| `test_portapapeles.py` | Copy, cut, paste and paste attributes |
| `test_marcadores_clip.py` | Markers with notes and colors, on the sequence and in clips |
| `test_panel_medios.py` | Media bin, thumbnails, search and drag |
| `test_proxies.py` | 540p proxies and their switch |
| `test_cola_render.py` | Background export, with progress and cancel |
| `test_keyframes.py` | Interpolation, animating any parameter and the curve editor |
| `test_color_avanzado.py` | Exposure, tint, lift/gamma/gain and LUTs |
| `test_croma.py` | Chroma key and spill suppression |
| `test_capa_ajuste.py` | Adjustment layers |
| `test_scopes.py` | Histogram, waveform and vectorscope |
| `test_subtitulos.py` | SRT and VTT import and export |
| `test_audio_fx.py` | EQ, compressor, LUFS and ducking |
| `test_estabilizar.py` | Phase-correlation stabilization |
| `test_rangos_y_anidado.py` | Marker ranges and nesting cycles |
| `test_anidadas.py` | Nested sequences in the window |
| `test_presets_propios.py` | Custom presets and export by markers |
| `test_zonas_render.py` | Render zones and their signature |
| `test_cache_render.py` | Zone render cache |
| `test_casos_raros.py` | Broken projects, missing files, locked tracks, impossible values |
| `test_remapeo_tiempo.py` | Time remapping and trimming the head without unglueing animation |
| `test_cuadros_intermedios.py` | Frame blending and optical flow |
| `test_perspectiva.py` | 3D perspective and corner pin |
| `test_seguimiento.py` | Motion tracking with masks and titles |
| `test_silencios_escenas.py` | Silence removal and scene detection |
| `test_multicamara.py` | Multicam by audio and by timecode |
| `test_plugins.py` | Effects as plugins and their validation |
| `test_versiones_fusion.py` | Versions, lock and three-way merge |
| `test_intercambio.py` | EDL, Final Cut XML and AAF |
| `test_hdr_ocio.py` | HDR footage and OCIO color spaces |
| `test_render_paralelo.py` | Parallel segment rendering |
| `test_nivel4_ventana.py` | Level 4 from the window |
| `test_pestanas_pildora.py` | The pill tabs in the properties panel |
| `test_diseno_beta.py` | Top bar, transport, tools, media, switches and panels of the new design |
| `test_binarios.py` | Icon, smoke test, Linux and Windows installers and the automated build |
| `test_portabilidad.py` | That it behaves the same on Linux and Windows |

## Shortcuts

**Every one can be changed** in Edit → Keyboard shortcuts (`Ctrl+/`). They're
stored in `atajos.json`, in the system config folder
(`~/.config/vortex-studio/` on Linux). The editor won't allow `Ctrl+Alt` —
it's AltGr on Latin American keyboards — nor two actions on the same key.

These are the defaults:

| File | |
|---|---|
| `Ctrl+N` / `Ctrl+O` | New / open project |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / save as |
| `Ctrl+I` | Import video, audio or image |
| `Ctrl+E` | Export (video or audio only) |
| `Ctrl+Shift+E` | Export the current frame to PNG |

| Edit | |
|---|---|
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / redo |
| `V` / `C` / `Y` | Selection / razor / slip tool |
| `S` / `Ctrl+K` | Split at the playhead |
| `Alt+,` / `Alt+.` | Slip the content one frame back / forward |
| `Ctrl+D` | Duplicate |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copy / cut / paste clips |
| `Ctrl+Shift+V` | Paste attributes (color, transform, speed…) |
| `Ctrl+L` | Link or unlink video and audio |
| `Ctrl+/` | Keyboard shortcuts |
| `Ctrl+Shift+D` | Fade the clip in and out |
| `Ctrl+Shift+F` | Freeze the current frame |
| `Ctrl+Shift+K` | Key every transform property |
| `Ctrl+Shift+P` | Picture in picture |
| `Del` / `Shift+Del` | Delete / ripple delete |
| `Ctrl+T` / `Ctrl+Shift+T` | Insert text / subtitle |

| Playback | |
|---|---|
| `Space` | Play / pause |
| `←` `→` | Frame by frame |
| `Shift`+arrows / `Ctrl`+arrows | Jump 1 s / 10 s |
| `Home` / `End` | Go to start / end |
| `J` `K` `Shift+L` | Slower / normal / faster |
| `L` | Loop |
| `Ctrl+Shift+A` / `Ctrl+Shift+B` | Cross dissolve / dip to black with the previous clip |
| `I` `O` / `Ctrl+Shift+X` | Mark in, out / clear marks |
| `M` / `Shift+M` | Add marker / edit it: name, note and color |
| `Alt+Shift+M` | Marker inside the selected clip |
| `Shift+K` | Keyframe editor |
| `Enter` | Render the zone (between marks, or everything) |
| `Ctrl+Shift+N` | Nest the selection into a sequence |
| `1` `2` `3` `4` | Cut to that camera in a multicam |
| `Shift+↓` `Shift+↑` | Next / previous marker |
| `F` | Fullscreen |

On the timeline: `Ctrl`+wheel zooms, dragging a clip moves it, dragging its
edges trims it, and everything snaps to neighbouring cuts, the playhead and
markers. With the slip tool (`Y`), dragging inside a clip changes which part
of the file is shown without moving it. `Ctrl`+click adds clips to the
selection, `Alt`+click grabs just one side of a linked pair, and
double-clicking a marker opens it.

## Layout

- `model/` — project, sequence, tracks, clips, text, images, color, history
  and saving. Plain Python, no Qt: it can be tested without a window.
- `media/` — decoding and color correction through PyAV/FFmpeg.
- `ui/` — window, preview, timeline, transport and panels. The compositor
  lives on its own and is shared by the preview and the export: that's what
  guarantees the final file looks like what you saw while editing.

## The properties panel

One window on the right with six tabs: Transform, Color, Mask, Clip, Text
and Image. They used to be several stacked docks, which took half the screen
for controls you rarely touch at the same time.

The tab switches itself based on your selection, but only when the current
one doesn't apply: if you were already on Color, selecting another clip
leaves you on Color. The ones that don't apply are disabled rather than
hidden, so they don't shuffle around.

The same idea applies inside each tab: what you use daily stays in sight,
and what you use now and then — the color curve — goes in a group that
starts collapsed and opens with a click.

## Animation

Every clip has position, scale, rotation and opacity, and any of the four can
be animated. The capability is After Effects'; the interface isn't. Each
property has its slider and a diamond next to it. Diamond off means a fixed
value; diamond on means there's a keyframe where the playhead is. You animate
by turning on a diamond, moving the playhead and moving the slider. There is
no curve editor to learn.

Interpolation eases in and out of every segment. Linear motion gives away
that a machine made it — it starts and stops abruptly; this curve looks
deliberate without asking anything of the user.

Keyframes are stored relative to the start of the clip, so moving the clip
takes its animation along.

## Formats and looks

The Sequence menu switches the frame to vertical 9:16, square, 4:5 or
cinematic 21:9 in one click. Footage isn't cropped: it's fitted inside and
whatever is left over goes black; from there you frame it with Transform.

The Color panel ships ready-made looks (Warm, Cool, Cinema, Vivid, Soft,
Black and white, Night). They aren't a separate layer: they write into the
same sliders, so you can start from one and keep adjusting by hand.

## Color curve and vignette

The curve is five sliders — blacks, shadows, midtones, highlights, whites —
and a graph that draws what they're doing. It's the same capability as a
DaVinci curve: any S-curve, lifting shadows without blowing highlights, the
washed-blacks film look. What's missing is points to drag, which is the part
that scares people off when they first open an editor.

Ready-made curves ship with it: S-curve contrast, Washed blacks, Open
shadows, Pull highlights and Flat film.

The graph draws exactly the curve that goes to FFmpeg. That works by sending
it already sampled at seventeen points: with the five bare anchors, FFmpeg
would interpolate differently and the graph would lie a little.

The vignette is a 0-to-100 slider that closes down the corners. Together with
washed blacks it's where the "looks like film" feeling comes from, which is
why the Cinema and Night looks already ship with it.

**It costs.** The vignette is around 12 ms per frame at 1080p — per-pixel
math, not a lookup table — against half a millisecond for the curve. With it
on, the preview drops from roughly 270 frames per second to roughly 47: still
plenty for 30 fps playback, but it's the most expensive adjustment there is.

## Masks and blend modes

Four shapes: rectangle, ellipse, a straight cut, or none. Each with
position, size, rotation, edge softness and invert. That covers what actually
gets used — hiding a face, revealing half the screen, framing something in a
circle — without a path editor and bezier handles.

The mask is measured against the output frame, like CapCut, not against the
layer like After Effects. The difference matters: you place it looking at the
preview, and if the clip is animated the mask stays where you put it, which
is exactly what you want when covering something that isn't moving.

The thirteen blend modes are the usual ones: multiply, screen, overlay,
darken, lighten, color dodge, color burn, hard light, soft light,
difference, exclusion and plus.

For a blend mode to have anything to blend with, **video tracks now stack**:
V1 and V2 are both visible. Before, only the highest track with footage was
painted, so putting something on V2 made V1 disappear entirely.
`Ctrl+Shift+P` sets up picture in picture in one click.

Lower tracks stop being looked at as soon as one above covers them
completely. Without that check, having two tracks would cost twice the
decoding even when the lower one is invisible.

## Text animation

Ten in animations and nine out: appear, rise, typewriter, zoom in, zoom out,
and slide from each of the four sides. You pick one from a list and set how
long it takes; there are no keyframes to place.

It's what makes CapCut fast, and in After Effects the same effect is four
keyframes per property plus an expression for the typewriter.

The out list deliberately doesn't offer the typewriter: un-typing reads as a
bug, not as an effect.

The project stores the animation's name and duration, not the keyframes it
generates. That way, tuning a curve improves projects that already exist
instead of breaking them.

## Everyday editing

**Framing.** Every clip has its mode: *Fit* (whole, with bars), *Fill* (fills
the frame and the excess spills out) or *Stretch*. To turn a horizontal edit
vertical: Sequence → Vertical 9:16, then Sequence → Fill the frame with every
clip. Under Transform → Framing and crop you crop per edge — the cropped part
turns transparent and the picture doesn't move — and pick the anchor point
the clip scales and rotates from.

**Transitions.** Besides the cross dissolve, dip to black and to white. Add
them from the Clip menu or the Clip tab, where the type can also be changed.

**Titles.** Font, color, size and alignment up front; outline with color and
width, and a drop shadow with color, distance, blur and opacity in a group
of their own.

**Linking.** Video and its audio come in linked: they move, trim, cut, slip,
change speed and delete together. `Alt`+click grabs just one, and `Ctrl+L`
unlinks them. If they drift apart, the clip shows how many frames in red.

**Clipboard.** `Ctrl+C` and `Ctrl+V` paste at the playhead, each item on its
own track, and the playhead lands at the end so you can paste again right
after. What you paste overwrites what's underneath. `Ctrl+Shift+V` pastes
only the settings you pick.

**Tracks.** Every header has its buttons: show and lock on video and text;
mute, solo and lock on audio. A locked track won't let you select, move or
delete anything on it.

**Markers.** They carry a name, a note and a color, on the ruler or inside a
clip. Clip markers travel with the clip. The note shows up on hover.

## Production

**Keyframes on any parameter.** Color, mask, volume, chroma key, images and
text, besides the transform. Once a value is animated, moving its slider sets
a keyframe at the playhead. The keyframe editor (`Shift+K`) shows each
parameter's curve; keyframes are dragged, and each segment is linear, ease,
hold or bezier, with its two handles.

**Color.** Exposure and tint next to the usual controls, and DaVinci's three
wheels — lift, gamma and gain — as per-channel sliders. `.cube` LUTs with
intensity. **Scopes** (View → Scopes) show the histogram, waveform and
vectorscope of the composited frame.

**Effects.** Chroma key with similarity, smoothness and spill suppression.
**Stabilization**: the first time it analyzes the video's motion in the
background and stores it; from then on the shot is corrected the same way in
the preview and in the export, wherever you jump to.

**Adjustment layer** (Insert → Adjustment layer): corrects the color of
everything below it, with its own opacity and mask.

**Audio.** Three-band EQ, compressor, normalization to −14, −16 or −23 LUFS
per BS.1770, and ducking: mark one track as Voice and another as Music, and
the music dips on its own whenever the voice plays.

**Nested sequences.** `Ctrl+Shift+N` moves the selection into a new sequence
and leaves a clip in its place; double-click opens it. A sequence can't be
placed inside another if that would make a cycle.

**Subtitles.** File → Import subtitles (SRT or VTT) brings them in as text;
Export subtitles writes the text back out.

**Export.** Custom presets, with their size, quality and frame rate. Export by
markers sends one file per range between markers to the queue.

**Render cache.** The bar under the ruler shows which zones are heavy (red),
light (yellow) or already rendered (green). `Enter` renders the red ones and
the preview plays them back from the file. Change anything in a zone and it
turns red again by itself.

## Pro

**Time remapping.** Clip → Time remapping: from the playhead on, the clip
goes slower, faster, in reverse or frozen, and what came before doesn't
change. They're time keyframes, so the keyframe editor shows the curve and
the ramp can be eased. In slow motion, the Clip tab picks the in-between
frames: repeat, blend or **optical flow**.

**3D and corners.** In Transform, tilt the layer back or sideways and move
each corner, to stick a video onto a screen or a wall.

**Tracking.** Put a mask over the object and use Clip → Detect and track:
the mask follows it, or the title at the playhead does. You get keyframes,
one per frame; if it lost track somewhere, the status bar says so.

**Silences and scenes.** Clip → Detect and track also removes the clip's
silences — with its linked audio, closing gaps — and splits a clip at each
scene change or marks them.

**Multicam.** Sequence → Create multicam: pick the cameras of the same take
and they sync by audio or by timecode. Hit play and cut live with `1` to
`4`; the first camera's audio is heard.

**Effects.** The Effects tab adds effects from a list and stacks them in
order. They're plugins: a `.json` in the config `plugins` folder
(`~/.config/vortex-studio/plugins/` on Linux) with the filter and its
controls adds a new one without touching the code.

**HDR and OCIO.** HDR video is converted to Rec.709 on import; Color → Source
color space changes it, and with `opencolorio` installed every OCIO color
space shows up there.

**Versions and merging.** File → Save version keeps a named copy next to the
project. If someone else edited a copy that came from that version, File →
Merge with another copy joins both jobs. If someone else has the project open
in a shared folder, you're warned.

**Taking the edit elsewhere.** File → Export edit writes XML (Premiere,
Resolve, Final Cut), EDL or AAF (Avid). The cuts travel, not the color or the
titles.

**Parallel rendering.** In the export dialog: splits the video into segments,
exports them at once and joins them without re-encoding.

## Sound

You hear it while editing, with volume and mute on the transport bar. The
playhead follows what has actually left the sound card, not the UI clock:
audio can't be sped up or skipped without it being audible, so it leads and
the picture follows.

**Tracks really do mix now.** Clips are split into non-overlapping lanes,
each lane is rendered separately and the lanes are summed with `amix`.
Before, the renderer moved forward and never went back, so two overlapping
clips couldn't be heard together: the second one was lost with no warning.
The lanes deliberately aren't the timeline's tracks, so the case of two
overlapping clips on the same track is solved too.

The sum can go past full scale and clip, same as Premiere. It's allowed to
clip rather than adding a limiter, because a limiter needs to look ahead and
that lookahead would push the sound out of sync with the picture. Per-clip
gain is there for that.

**At other speeds**, each clip chooses what its sound does: *Keep pitch* (like
Premiere: a voice sounds natural), *Shift pitch* (like tape: higher when sped
up) or *Mute*. The range is 0.25× to 4×, and the audio lasts exactly as long
as the picture.

## Smooth preview

Picture decoding runs on its own thread, never on the UI thread. Before,
every playhead jump froze the window while it decoded; measured with the
decoder already open:

| Footage | Before | Now |
|---|---|---|
| 1080p | 26 ms per jump | 0.45 ms |
| 4K | 111 ms per jump | 0.57 ms |

Dragging the playhead only decodes where you let go, and the previous frame
stays on screen while the new one arrives. During playback eight frames are
read ahead; if the thread falls behind, frames are dropped and sound keeps
leading.

## Import

`Ctrl+I` takes video, audio and images, and picks the track from what the
file actually contains, not from its extension. Standalone audio lands on
the first audio track that's free for that span.

Everything imported stays in the **media bin**, on the left, with a thumbnail
and a search box (accent- and case-insensitive, and by kind). From there you
drag it onto any track or double-click to add it at the playhead. File →
Import to the media bin brings in several files without placing them on the
timeline.

**Proxies.** View → Use proxies (540p) makes the preview read lightweight
copies of heavy videos; they're created on their own in the background.
Export always reads the originals. The switch is remembered between sessions.

What's known about each file — duration, resolution, codecs, channels — is
stored in the project and isn't read again while the file doesn't change.
The audio waveform goes to the system cache, so it shows up instantly when a
project is reopened.

## Export

`Ctrl+E` writes an MP4 (H.264) with everything burned in: cuts, text, images
and color correction. If in and out marks are set, only that range is
exported.

Exports go to the **render queue** and you can keep editing: each one takes a
frozen copy of the sequence, so whatever you edit afterwards doesn't change
the file. Every job has its progress bar and cancel button; the incomplete
file is deleted.

## Autosave

Every 30 seconds, if there are unsaved changes, a copy is written to the
system data folder (`~/.local/share/vortex-studio/` on Linux), **never on
top of your project**. If the program closes abruptly, it offers to recover
it the next time it opens. Saving or closing normally deletes the copy.

## Portability

The `.vortex` project stores **relative** paths when the footage sits next to
the project or below it, always with forward slashes. That way the folder can
be moved, sent to another machine or carried from Linux to Windows and still
opens. Only footage living elsewhere is stored with an absolute path.

There is no `Ctrl+Alt` shortcut anywhere: on Windows with a Latin American
keyboard, `AltGr` sends exactly that, and typing `@` or `\` would fire editor
commands. A test watches for it.

## License

[MIT](LICENSE). You can use, modify and distribute it, including in something
commercial; all that's asked is that you keep the copyright notice. No
warranty of any kind — and in beta that isn't legal boilerplate, it's a
literal warning.

## Not there yet

- During video transitions, audio hard-cuts: there's no audio crossfade.
- Sound only follows playback with the transport at normal speed (J-K-L);
  each clip's own speed is heard.
- Multi-selection is `Ctrl`+click only; no rubber-band selection.
- The red drift badge is only computed between linked clips from the same
  file.
- The queue exports one job at a time, and quitting the editor cancels it.
- The audio mix clips when the sum goes past 1.0, and there are no meters to
  see it coming.
- No wipes or transition effects beyond cross, dip to black and dip to
  white.
- The vignette is the most expensive adjustment there is: around 12 ms per
  frame at 1080p.
- One mask shape per layer.
- Tracking follows position, not rotation or scale, and the mask doesn't
  deform with the object.
- The level-4 items that need AI — transcription, text-based editing,
  speech subtitles — arrive once an LLM is integrated.
- Merging works per item; two clips left overlapping are reported but not
  rearranged.
- Switching sequences resets undo, and undo doesn't remove the sequence a
  "Nest" created.
- Stabilization corrects shifts, not camera rotation or zoom.
- The zone bar only measures the picture; audio isn't rendered to cache.

## Language

The code, comments, commit messages and the user interface are in Spanish.
This file and `CHANGELOG.en.md` are the English entry points.
