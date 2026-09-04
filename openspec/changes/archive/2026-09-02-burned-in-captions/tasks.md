## 1. Burned-in captions and framerate fix

- [x] 1.1 Add `-vf subtitles=...` (libass) to `render_video()`'s ffmpeg command
      (`worker/video.py`), styled for readability, keeping the existing
      `mov_text` soft track alongside it — verified by extracting a real frame
      from a produced video (`ffmpeg -ss ... -frames:v 1`) and reading it back:
      caption text visible, correctly positioned, matching the actual script
      content at that timestamp, on both a full ~16-minute real episode and a
      short end-to-end API-driven test
- [x] 1.2 Move `-framerate 1` to the image input (before `-i`), removing the
      redundant output-side `-r` — verified against the real ~16-minute episode
      that prompted this change: 22 seconds end-to-end (previously several
      real minutes for the same content)
- [x] 1.3 Add `fontconfig`/`fonts-dejavu-core` to `deploy/gpu-worker/Dockerfile`
      as a separate `RUN` step placed *after* `uv sync`, not folded into the
      existing early `apt-get` line — verified the rebuild only re-ran the new
      package-install layer (8 seconds) and hit cache for `uv sync`, after an
      initial attempt that put the packages in the wrong place triggered a full,
      unwanted ML-dependency reinstall (caught and killed mid-build, then fixed
      by this reordering before retrying)

## 2. Documentation

- [x] 2.1 This proposal and spec delta, archived alongside the fix.
