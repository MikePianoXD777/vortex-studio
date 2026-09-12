# Vortex Studio

[Español](README.md) · **English**

A non-linear video editor. Part of Vortex Suite.

The features of DaVinci Resolve, CapCut, Premiere Pro and After Effects, but
easy to use. The capability, yes; the complexity, no.

> ### ⚠️ Pre-alpha — `0.3.0a1`
>
> **This is not ready for real work.** It passes 493 automated tests, but
> nobody has actually used it on their own footage yet. That is not the same
> as being tested.
>
> What to expect:
>
> - Things breaking in ways we haven't seen
> - The `.vortex` file format moved to version 3: projects from 0.1 and 0.2
>   open fine, but not the other way around
> - Audio of a clip with speed other than 1× drifts out of sync with the
>   picture
> - The only transition is still the cross dissolve
>
> Use it to poke around and to report what breaks. Not to edit anything you
> care about without a backup.

> ### 📦 There is no ready-made download
>
> **We don't publish executables yet.** There is no `.exe` for Windows and no
> Linux binary: this repo is source code only.
>
> To use it you **have to build it yourself**, which needs Python 3.11 or
> newer. The steps are right below. It takes a couple of minutes the first
> time, mostly downloading PySide6, which is around 250 MB.
>
> Binaries will come once it's more stable; publishing them in pre-alpha
> makes no sense.

## Getting started

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
- Fades, cross dissolve, clip speed and freeze frame
- Sound while editing, with track mixing and waveforms on the audio tracks
- Markers
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
| `Ctrl+Shift+A` | Cross dissolve with the previous clip |
| `I` `O` / `Ctrl+Shift+X` | Mark in, out / clear marks |
| `M` / `Shift+M` | Add marker / named marker |
| `Shift+↓` `Shift+↑` | Next / previous marker |
| `F` | Fullscreen |

On the timeline: `Ctrl`+wheel zooms, dragging a clip moves it, dragging its
edges trims it, and everything snaps to neighbouring cuts, the playhead and
markers. With the slip tool (`Y`), dragging inside a clip changes which part
of the file is shown without moving it.

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

What's known about each file — duration, resolution, codecs, channels — is
stored in the project and isn't read again while the file doesn't change.
The audio waveform goes to the system cache, so it shows up instantly when a
project is reopened.

## Export

`Ctrl+E` writes an MP4 (H.264) with everything burned in: cuts, text, images
and color correction. If in and out marks are set, only that range is
exported. It can be cancelled mid-export; the incomplete file is deleted.

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
warranty of any kind — and in pre-alpha that isn't legal boilerplate, it's a
literal warning.

## Not there yet

- **Audio of a clip with speed other than 1× is read at normal speed**, so it
  drifts out of sync with the picture, in playback and export. Audio speed
  belongs to level 2.
- Export still decodes on the UI thread, with the progress bar on top.
  Moving it off is the render queue, from level 2.
- Sound only follows playback at normal speed. At 2× it would come out
  pitch-shifted, which is worse than not hearing it.
- With an audio clip selected, the Transform tab stays enabled with sliders
  that do nothing.
- The audio mix clips when the sum goes past 1.0, and there are no meters to
  see it coming.
- The only transition is the cross dissolve; no wipes, no effects.
- The vignette is the most expensive adjustment there is: around 12 ms per
  frame at 1080p.
- One mask shape per layer, and it can't be animated.
- No animated masks and no motion tracking.

## Language

The code, comments, commit messages and the user interface are in Spanish.
This file and `CHANGELOG.en.md` are the English entry points.
