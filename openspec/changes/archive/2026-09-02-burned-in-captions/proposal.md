## Why

`video-production-completion` muxed captions as a soft (embedded, selectable)
`mov_text` subtitle stream, matching the RFC's original wording. In practice this
made captions invisible: no browser exposes an embedded MP4 subtitle track in its
native `<video>` controls, and YouTube doesn't auto-pull captions from one either
— confirmed when the user reviewed a real rendered episode and the captions
simply didn't appear anywhere. Separately, the same review surfaced that
`render_video` was taking several real minutes for a ~20-minute episode when the
underlying workload (a 1fps static-image mux) should be trivial — traced to `-r 1`
being an output option rather than the input-side rate that actually controls how
many frames `-loop 1` generates in the first place.

## What Changes

- Captions are now burned directly into the video frames via ffmpeg's `subtitles`
  filter (libass), styled for readability (white text, black outline, bottom
  placement) — visible in any player, any review screen, no extra manual step.
  The soft `mov_text` track is kept alongside it (costs nothing, still helps
  players that do support it).
- `-framerate 1` moved to the image input (before `-i`), so `-loop 1` generates
  frames at the intended rate from the start instead of downsampling from a
  higher default rate. Verified against the real ~16-minute episode that
  prompted this: 22 seconds end-to-end, down from several minutes.
- `deploy/gpu-worker/Dockerfile` gains `fontconfig`/`fonts-dejavu-core` — needed
  for libass to have an actual font to render text with (`ffmpeg`'s own package
  already depends on libass itself). Added as a **separate, later** `RUN`
  step, after `uv sync`, specifically so a future addition to this runtime-only
  package list doesn't invalidate the image's most expensive layer (the full ML
  dependency install) — learned the hard way when the first attempt at this
  change (adding the packages to the existing early `apt-get` line) triggered a
  full, unnecessary `uv sync` rebuild.

## Capabilities

### Modified Capabilities
- `workflow/video-production`: captions are burned into the rendered video, not
  only muxed as a soft track.

## Impact

- `worker/video.py`: `render_video()`'s ffmpeg invocation — `-vf subtitles=...`
  added, `-framerate` moved to the input side.
- `deploy/gpu-worker/Dockerfile`: new packages, placed after `uv sync` on
  purpose.
- No API, workflow-shape, or frontend changes — same inputs/outputs as before.
