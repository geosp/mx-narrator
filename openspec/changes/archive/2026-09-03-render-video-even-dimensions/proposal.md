## Why

User's real, in-progress episode failed at render time right after approving
captions:

```
[libx264 @ ...] width not divisible by 2 (1671x941)
Error while opening encoder - maybe incorrect parameters such as bit_rate, rate, width or height.
```

`render_video()`'s only `-vf` was the `subtitles=...` filter — no
scaling/padding step normalized the input image's dimensions before
encoding. `-pix_fmt yuv420p` (needed for broad player/YouTube compatibility)
uses 2×2 chroma subsampling, which requires both width and height to be
even. The uploaded background image (1671×941 — both dimensions odd) failed
libx264's encoder open. This affects any background image with an odd
width or height, not something specific to one episode.

## What Changes

- `worker/video.py`: prepend `scale=trunc(iw/2)*2:trunc(ih/2)*2` to the
  existing `-vf` chain, rounding each dimension down to the nearest even
  number before encoding — the standard fix for this libx264 error class.
  Crops at most 1px off each dimension (1671×941 → 1670×940), imperceptible
  for a static background image.

## Capabilities

No API/data-model contract change — internal fix to an existing rendering
step. `skip_specs: true`.

## Impact

- `worker/video.py` only.
- Reproduced the exact failure first: ran the unfixed ffmpeg command
  directly against a deliberately odd-dimension (1671×941) test image
  inside the real `cpu-worker` container, confirmed the same
  `width not divisible by 2` error.
- Verified the fix resolves it: same test image now encodes successfully
  (exit 0), output resolution confirmed 1670×940 (both even) via `ffprobe`.
- Rebuilt and redeployed `api`/`gpu-worker`/`cpu-worker` together (all three
  share this image) after confirming via `temporal workflow describe` that
  no workflow was mid-activity.
- Did not touch the user's real in-progress video job's data directly —
  the fix was deployed live and the user retried via the existing "Revise
  captions" button, which succeeded (confirmed by the user's own follow-up
  screenshot showing a fully-rendered, playable video).
