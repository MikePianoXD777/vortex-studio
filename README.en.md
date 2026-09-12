# Vortex Studio

[Español](README.md) · **English**

A non-linear video editor. Part of Vortex Suite.

The features of DaVinci Resolve, CapCut, Premiere Pro and After Effects, but
easy to use. The capability, yes; the complexity, no.

> ### ⚠️ Pre-alpha — `0.1.0a1`
>
> **This is not ready for real work.** It passes 167 automated tests, but
> nobody has actually used it on their own footage yet. That is not the same
> as being tested.
>
> What to expect:
>
> - Things breaking in ways we haven't seen
> - The `.vortex` file format may change and break old projects
> - 4K footage will crawl: decoding still runs on the UI thread
> - No mixing across audio tracks, no transitions beyond the cross dissolve
>
> Use it to poke around and to report what breaks. Not to edit anything you
> care about without a backup.

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
- Undo and redo
- Text and subtitles, with outline and caption box
- Images over the video
- Color correction with one-click looks
- Keyframe animation of position, scale, rotation and opacity
- Fades, cross dissolve, clip speed and freeze frame
- Sound while editing, with waveforms on the audio tracks
- Markers
- Vertical, square and cinema formats
- Export to MP4 with audio, and the current frame to PNG
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

| File | |
|---|---|
| `Ctrl+N` / `Ctrl+O` | New / open project |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / save as |
| `Ctrl+I` | Import video or image |
| `Ctrl+E` | Export video to MP4 |
| `Ctrl+Shift+E` | Export the current frame to PNG |

| Edit | |
|---|---|
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / redo |
| `V` / `C` | Selection / razor tool |
| `Ctrl+K` / `Ctrl+D` | Cut at the playhead / duplicate |
| `Ctrl+Shift+D` | Fade the clip in and out |
| `Ctrl+Shift+F` | Freeze the current frame |
| `Ctrl+Shift+K` | Key every transform property |
| `Del` / `Shift+Del` | Delete / ripple delete |
| `Ctrl+T` / `Ctrl+Shift+T` | Insert text / subtitle |

| Playback | |
|---|---|
| `Space` | Play / pause |
| `←` `→` | Frame by frame |
| `Shift`+arrows / `Ctrl`+arrows | Jump 1 s / 10 s |
| `J` `K` `Shift+L` | Slower / normal / faster |
| `L` | Loop |
| `Ctrl+Shift+A` | Cross dissolve with the previous clip |
| `I` `O` / `Ctrl+Shift+X` | Mark in, out / clear marks |
| `M` / `Shift+M` | Add marker / named marker |
| `Shift+↓` `Shift+↑` | Next / previous marker |
| `F` | Fullscreen |

On the timeline: `Ctrl`+wheel zooms, dragging a clip moves it, dragging its
edges trims it, and everything snaps to neighbouring cuts and to the
playhead.

## Layout

- `model/` — project, sequence, tracks, clips, text, images, color, history
  and saving. Plain Python, no Qt: it can be tested without a window.
- `media/` — decoding and color correction through PyAV/FFmpeg.
- `ui/` — window, preview, timeline, transport and panels. The compositor
  lives on its own and is shared by the preview and the export: that's what
  guarantees the final file looks like what you saw while editing.

## The properties panel

One window on the right with five tabs: Transform, Color, Clip, Text and
Image. They used to be five stacked docks, which took half the screen for
controls you rarely touch at the same time.

The tab switches itself based on your selection, but only when the current
one doesn't apply: if you were already on Color, selecting another clip
leaves you on Color. The ones that don't apply are disabled rather than
hidden, so they don't shuffle around.

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

## Sound

You hear it while editing, with volume and mute on the transport bar. The
playhead follows what has actually left the sound card, not the UI clock:
audio can't be sped up or skipped without it being audible, so it leads and
the picture follows.

## Export

`Ctrl+E` writes an MP4 (H.264) with everything burned in: cuts, text, images
and color correction. If in and out marks are set, only that range is
exported. It can be cancelled mid-export; the incomplete file is deleted.

## Portability

The `.vortex` project stores **relative** paths when the footage sits next to
the project or below it, always with forward slashes. That way the folder can
be moved, sent to another machine or carried from Linux to Windows and still
opens. Only footage living elsewhere is stored with an absolute path.

There is no `Ctrl+Alt` shortcut anywhere: on Windows with a Latin American
keyboard, `AltGr` sends exactly that, and typing `@` or `\` would fire editor
commands. A test watches for it.

## Not there yet

- Mixing doesn't sum tracks: it takes the audio clips in order and fills the
  gaps with silence. Two overlapping clips don't blend.
- Sound only follows at normal speed. At 2× it would come out pitch-shifted,
  which is worse than not hearing it.
- Picture decoding runs on the UI thread: 4K will crawl. It needs a redesign
  with a decoding thread and a frame buffer, and it's the biggest thing left.
- The only transition is the cross dissolve; no wipes, no effects.
- No masks and no blend modes.
- No color curves and no vignette.

## Language

The code, comments, commit messages and the user interface are in Spanish.
This file and `CHANGELOG.en.md` are the English entry points.
