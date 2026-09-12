# Changelog

[Español](CHANGELOG.md) · **English**

Everything that changes in Vortex Studio, newest first.

Versions follow [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
While we're on `0.x`, any minor version may break compatibility.

## [Unreleased]

Nothing yet.

## [0.3.0a1] — 2026-09-12

**Level 1 of the roadmap, complete.** Everything an editor needs to be an
editor: decoding off the UI thread, media probing, slip, configurable
shortcuts, cached audio waveforms, export presets and autosave. Still
pre-alpha: it passes 493 automated tests — 205 more than 0.2.0a1 — but
nobody has used it on their own footage yet.

**The file format moved to version 3.** Projects from 0.1 and 0.2 open
without trouble, because every format change now has its migration. Not
the other way around: 0.2.0a1 refuses to open a project from this one.

**Still no executables.** Binaries come when pre-alpha ends.

### Decoding off the UI thread

- Before, every playhead move decoded inside the window itself, and the UI
  froze meanwhile. Measured jumping to 25 random positions, with the
  decoder already open:

  | Footage | Before | Now |
  |---|---|---|
  | 1080p | 26 ms per jump (worst: 41) | 0.45 ms (worst: 0.8) |
  | 4K | 111 ms per jump (worst: 176) | 0.57 ms (worst: 1.1) |

- A frame server decodes on its own thread. The newest request wins:
  dragging the playhead doesn't decode every position it passed, only where
  it was released.
- While the new frame arrives, the previous one for that clip stays on
  screen instead of black. During playback 8 frames are read ahead, and if
  the thread falls behind frames are dropped: the clock leads.
- A frame that fails is remembered, so it isn't requested again on every
  repaint.
- Export still decodes in order on the UI thread. Moving it off is the
  render queue, from level 2.

### Import and media probing

- Probing reads duration, resolution, fps, codecs, channels and sample rate,
  and tells video, audio and image apart by content, not by extension. An
  MP3 with cover art is recognised as audio.
- It's stored in the project with the file's size and date: while those
  don't change, the container isn't opened again.
- MP3, WAV, FLAC, M4A, AAC, OGG and Opus can be imported. They land on the
  first audio track that's free for that span.

### Waveforms and audio with NumPy

- The waveform stores min and max per bucket, so it's drawn with its real
  shape. It's computed at import and saved as .npy in the system cache:
  reopening the project doesn't decode again, and zooming never recomputes
  it.
- Fades and gain are applied per sample. Before, the level was computed
  once per second, and a three-second fade was three steps.

### Configurable shortcuts

- Every action has a key and its shortcut comes from a map, stored in
  atajos.json in the config folder. Edit → Keyboard shortcuts opens an
  editor with search.
- It's validated on load: nothing with Ctrl+Alt, which is AltGr on Latin
  American keyboards; never two actions on the same key; a damaged file
  doesn't stop the editor from opening.
- Arrows, Home and End went from being hard-coded to configurable actions.
  They're disabled while typing even with Ctrl, because Ctrl+← jumps a word
  inside a subtitle.

### Split, slip and command layer

- S splits at the playhead.
- Slip tool (Y): changes which part of the file is shown without moving or
  stretching the clip. Alt+, and Alt+. slip one frame.
- Every edit is a named command on top of the snapshot history, which stays
  as it was. It's what the scripting console and the AI agent will use
  later.
- Snapping also sticks to markers.

### Export presets

- Sequence size, H.264 1080p, H.264 4K and audio only in AAC. "1080p" is
  the short side: a vertical video comes out at 1080 × 1920.
- Frames are composed directly at the output size, so text stays sharp.
- "Exported" moved from a modal dialog to the status bar.

### Autosave

- Every 30 seconds, if there are changes, a copy in the system data folder,
  never on top of the project. It's deleted on save or on a normal close; if
  the program crashes, it stays and is offered at startup.
- A copy older than its saved project isn't offered.

### Fixed

- **The last second of audio was lost.** A clip that reached the end of its
  file lost up to a second of its ending, in playback and export: the FIFO
  only released full blocks.
- **Gain or fades sounded like noise in playback.** The volume filter
  returned floats even though playback asks for 16-bit integers.
- **Recolouring while paused advanced a frame.** The decoder compared only
  four colour settings; moving temperature, vignette or the curve decoded
  the next frame.
- **Cutting with nothing selected only cut one track**: the video was split
  and its audio wasn't.
- **Splitting a clip** ignored speed, broke keyframe animation, duplicated
  fades and inherited the cross dissolve.
- The export dialog said audio doesn't play while editing, and it has for
  two versions.
- The PyInstaller .spec excluded NumPy: the executable would have crashed.

### Under the hood

- **Hybrid stack.** From the roadmap's base stack, what truly improves
  things and works on this machine was adopted: threaded decoding with PyAV
  and NumPy for audio. The QPainter timeline, the compositor and Qt audio
  stayed, because they already work and rewriting them adds no features.
  moderngl has no build for Python 3.14, and QOpenGLWidget doesn't paint
  without a display, which would leave the preview untested; the GPU waits
  until there's a way to test it.
- **Undo still uses snapshots**, with the command layer on top.
- NumPy becomes a dependency.
- 493 tests in 43 seconds. Each new piece ran its tests three times in a
  row; the threading ones, thirteen.
- The test bench isolates cache, config and data in throwaway folders, so it
  never touches the user's.

## [0.2.0a1] — 2026-09-12

**Still pre-alpha.** It passes 288 automated tests — 121 more than the
previous release — but nobody has used it on their own footage yet.

**The file format moved to version 2.** Projects from `0.1.0a1` open without
trouble and their new fields are filled with neutral values. Not the other
way around: `0.1.0a1` refuses to open a project from this one, with a clear
message instead of opening it halfway and losing the settings on save.

**Still no executables.** There is no `.exe` and no Linux binary.

### Audio mixing — the costliest bug of this release

- **Two overlapping audio clips are both audible now.** They weren't before.
  The renderer moved forward and never went back, so by the time the second
  clip came up the cursor was already past it and that clip was lost
  entirely, with no warning: music and voice overlapping sounded like music
  alone.
- Clips are split into non-overlapping **lanes**, each lane is rendered
  separately, and the lanes are summed with FFmpeg's `amix`. The lanes
  deliberately aren't the timeline's tracks: that also solves two
  overlapping clips on the same track, which a per-track mix would still
  lose.
- With a single lane no filter is built at all. The common case — one voice,
  one music bed, no overlap — pays nothing for the mixer existing.
- `amix` runs with `normalize=0`. By default it divides by the number of
  inputs, so adding a silent track would have halved the volume of the rest.
- The sum can go past full scale and clip, same as Premiere. It's allowed to
  clip rather than adding a limiter: a limiter needs to look ahead, and that
  lookahead would push the sound out of sync with the picture.

### Stacked video tracks

- **V1 and V2 are both visible.** Before, only the highest track with
  footage was painted, so putting something on V2 made V1 disappear
  entirely: there was no way to build a picture in picture, and a blend mode
  would have had nothing to blend with.
- `Ctrl+Shift+P` sets up picture in picture in one click, and "Fill the
  frame" undoes it.
- Lower tracks stop being looked at as soon as one above covers them
  completely — opaque, no mask, no blend, no partial fade, not scaled down.
  Without that check, having two tracks would cost twice the decoding even
  when the lower one is invisible.

### Masks

- Four shapes: rectangle, ellipse, straight cut and none. With position,
  size, rotation, edge softness and invert.
- The mask is measured against the **output frame**, like CapCut, not
  against the layer like After Effects: you place it looking at the preview,
  and if the clip is animated the mask stays where you put it.
- The soft edge is produced by scaling the alpha map down and back up. It
  sounds like a hack but it is exactly a box blur, Qt does it in C++ and it
  costs nothing. FFmpeg's `boxblur`, the other option, isn't in the PyAV
  wheels.
- The shape is drawn on an oversized canvas and then cropped. Without that
  margin the blur also softened the edges of the frame, and a linear mask
  covering half the screen came out with all four borders washed instead of
  just the cut line.
- Inverting doesn't flip pixels: it's the other composition mode
  (`DestinationOut` instead of `DestinationIn`). Flipping a premultiplied
  image gives garbage.
- Alpha maps are cached by size and values. Without that it would be one
  blur per frame.

### Blend modes

- Thirteen: multiply, darken, color burn, screen, lighten, color dodge,
  plus, overlay, hard light, soft light, difference, exclusion and normal.
- They map onto Qt composition modes, which Qt ships natively: a blend mode
  costs no more than a plain draw.
- A mode this version doesn't know is painted normally. Better that the layer
  shows up too plainly than that it disappears.

### Color curve and vignette

- A five-point curve — blacks, shadows, midtones, highlights, whites — with
  its graph next to it. The same capability as a DaVinci curve, without
  points to drag.
- Ready-made curves: S-curve contrast, Washed blacks, Open shadows, Pull
  highlights and Flat film.
- The graph draws exactly what goes to FFmpeg. That works by sending the
  curve already sampled at seventeen points: with the five bare anchors the
  `curves` filter would interpolate differently and the graph would lie a
  little.
- Interpolation is monotone Hermite (Fritsch–Carlson) rather than a natural
  spline: the natural one overshoots between two widely spaced anchors, and
  that shows up as a brightness bounce where the user put nothing.
- A 0-to-100 vignette, through the `vignette` filter.
- The Cinema, Night, Vivid, Soft and Black-and-white looks now ship with a
  curve — and the first two with a vignette too. With only brightness and
  contrast the look stopped halfway.
- **The vignette costs:** around 12 ms per frame at 1080p, against half a
  millisecond for the curve. It's per-pixel math, not a lookup table. With it
  on, the preview drops from roughly 270 frames per second to roughly 47:
  still plenty for 30 fps, but it's the most expensive adjustment there is.

### Text animations

- Ten in and nine out: appear, rise, typewriter, zoom in, zoom out, and
  slide from each of the four sides. You pick from a list and set how long
  it takes.
- "Zoom in" overshoots slightly and settles back. That overshoot is what
  makes it look hand-made; without it the text just grows and looks cheap.
- The typewriter measures its width against the complete text, not the part
  already typed: measured against the visible part, centered text would
  shuffle letter by letter and read as a jitter.
- The out list doesn't offer the typewriter. Un-typing reads as a bug, not
  as an effect.
- If the in and out animations together don't fit the item, they're scaled
  down proportionally. Overlapping, the text would never come to rest.
- The project stores the animation's name and duration, not the keyframes it
  generates. That way, tuning a curve improves projects that already exist
  instead of breaking them.
- Images over the video accept them too.

### Interface

- A new **Mask** tab, with the blend mode on top and the mask below: they're
  used together, and CapCut keeps them in the same place for the same
  reason.
- The color curve lives in a group that starts collapsed. With it in plain
  sight the Color panel was eleven sliders, and there went "easy to use".
  The group opens on its own if the clip already had a curve, so a cinema
  look doesn't hide what it's doing to the picture.
- Controls that don't apply to the chosen mask shape are disabled. An
  enabled control that does nothing looks like a broken program.
- The text duration field is now labelled "Duración del texto": the same
  panel holds another duration, the animation's, and two fields with the
  same name side by side can't be told apart.

### Fixed

- `amix` returned whatever format suited it for summing: asked for `s16`, it
  gave back packed `flt`. Read as 16-bit integers that sounds like white
  noise at full volume, and only on playback — the export looked perfect. A
  test caught it before it shipped.
- Serialization didn't rebuild nested dataclasses: `clip.color` came back as
  a `dict` and anything asking it for an attribute blew up, but several
  steps later.
- Selecting an audio clip left the Mask tab enabled with an empty panel.

### Under the hood

- 288 automated tests that run in 27 seconds without opening windows.
- The model is still plain Python: text animations, the curve and the mask
  are tested without Qt. The translation to Qt — composition modes and alpha
  maps — lives entirely in the compositor.
- One compositor for the preview and the export, now for masks and blending
  too. There are tests checking that the mask comes out burned into the
  final file.

## [0.1.0a1] — 2026-09-12

**Pre-alpha.** First version with everything working end to end: it cuts,
animates, plays sound and exports. It passes 167 automated tests, but nobody
has used it on their own footage yet, so expect things to break. The
`.vortex` file format may change before a real 0.1.0.

**No executables.** There is no `.exe` and no Linux binary: you have to build
it with `./correr.sh` or `construir.bat`. Binaries will come once it's more
stable.

### Player

- Playback driven by a real clock: the position is computed against elapsed
  time, so a slow frame gets skipped instead of accumulating lag.
- Speeds from 0.25× to 4×, looping, in and out marks, 1 and 10 second jumps,
  fullscreen.
- Sound while editing, with volume and mute. The playhead follows what has
  actually left the sound card, not the UI clock.

### Editing

- Select, drag and move clips between tracks, snapping to neighbouring cuts
  and to the playhead.
- Trimming by the edges. On a file clip, trimming the start advances the in
  point instead of stretching the picture.
- Razor, cut at the playhead, duplicate, delete with and without closing the
  gap.
- What you drop on top trims what was there — no silent overlaps.
- Undo and redo by snapshots, with the name of the action.
- Six tracks: T1 for text, V2 and V1 for video, A1 to A3 for audio.
- Named markers, navigable with `Shift`+arrows.

### Text and images

- Titles and subtitles with preset positions, size relative to the frame,
  color, alignment, outline and caption box.
- Images over the video, with position, size, opacity and duration.

### Color

- Brightness, contrast, saturation, gamma and temperature per clip.
- One-click looks: Warm, Cool, Cinema, Vivid, Soft, Black and white, Night.
  They write into the same controls, so you can keep adjusting afterwards.

### Animation

- Position, scale, rotation and opacity per clip, all four animatable by
  keyframes, with eased interpolation.
- Keyframes are stored relative to the clip, so moving the clip takes its
  animation along.

### Transitions

- Fade in and out on clips, images and text.
- Cross dissolve between adjacent clips, split around the cut.

### Timing

- Clip speed from 0.1× to 10×, adjusting the duration so no footage is lost.
- Freeze frame.

### Audio

- The audio of an imported video lands as its own clip on A1.
- Waveforms on the audio tracks, computed from peaks.
- Volume and fades per clip.

### Project and export

- Save and open `.vortex`, with relative paths: the folder can be moved,
  sent to another machine or carried from Linux to Windows and still opens.
- Export MP4 H.264 with everything burned in, with audio, with progress and
  cancellable. Cancelling deletes the partial file.
- Export the current frame to PNG.
- Sequence formats: vertical 9:16, square, 4:5, cinematic 21:9.

### Interface

- Loading splash that covers the real loading, not a fake delay.
- Launcher to choose between Video and Photos (Photos not enabled yet).
- Properties panel with five tabs, which switches itself based on the
  selection but respects the one you picked by hand.
- Status bar with resolution, fps, duration, item count and active tool.

### Fixed

- Fifteen single-key shortcuts were eating what you typed: `c` triggered the
  razor and `Del` deleted the selected clip.
- No shortcut uses `Ctrl+Alt`, which is `AltGr` on a Latin American keyboard.
- Clips compared by value, so deleting the audio took the video with it.
- One decoder per file collapsed to seconds per frame during a transition
  between two halves of the same video.
- The audio waveform was computed inside the repaint and froze the window.
- The splash wasn't visible under Wayland.
- `Export frame` ignored the sequence format.
- Three notices appeared as modal dialogs that interrupted for no reason.

### Under the hood

- 167 automated tests that run in 14 seconds without opening windows.
- The model is plain Python: it's tested without Qt.
- A single compositor for the preview and the export, so the final file
  looks like what you saw while editing.
- Color correction and volume through FFmpeg filters, not Python loops.
