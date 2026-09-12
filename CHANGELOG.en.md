# Changelog

[Español](CHANGELOG.md) · **English**

Everything that changes in Vortex Studio, newest first.

Versions follow [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
While we're on `0.x`, any minor version may break compatibility.

## [Unreleased]

Nothing yet.

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
