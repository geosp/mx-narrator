## Why

The SRT review screen showed the entire subtitle file as one raw-text
`<textarea>` (index numbers, timestamp lines, and text all as plain text) next
to an unlinked audio player. To fix a mis-transcribed word, the user had to
manually search the raw text for the right block while listening. User
requested a synced view — the caption matching the current playback position
highlights and scrolls into view, so pausing on a word's timestamp shows exactly
the text to fix.

## What Changes

- New `web/src/srt.js`: pure `parseSrt`/`serializeSrt` functions for the SRT
  format's block structure — no dependency, mirrors this project's existing
  "small focused module" convention (e.g. `worker/id3.py`).
- `SrtReview` (`web/src/VideoReview.jsx`) now renders one row per caption
  (clickable timestamp + an editable text field) instead of one giant raw-text
  box. The active row (matching the audio's current playback position)
  highlights and auto-scrolls into view; clicking a timestamp seeks playback
  there.
- No backend change: `POST /video_jobs/{id}/srt/approve` already just validates
  and accepts a raw SRT string — the new UI reconstructs valid SRT text on
  submit via `serializeSrt()`, same contract as before.
- **Scope call**: reworks *text* editing per caption (the actual need — fixing
  wording the correctness check flagged), not timestamp/structural editing
  (merging, splitting, retiming). Real, disclosed limitation, not overlooked.

## Capabilities

No capability changes — this is a pure frontend UX change. The system-level
contract `workflow/video-production` already specifies (human review required,
server-side SRT validation, `POST /video_jobs/{id}/srt/approve`'s behavior) is
completely unchanged; only how a human interacts with the review screen differs.
`skip_specs: true` accordingly, rather than inventing a UI-interaction
requirement this project's specs don't otherwise describe at that level.

## Impact

- New file `web/src/srt.js`.
- `web/src/VideoReview.jsx`: `SrtReview` component reworked; nothing else in the
  file changes.
- Verified two real bugs found and fixed during implementation, not just the
  happy path: `timeupdate` alone doesn't reliably fire after a programmatic seek
  while paused (added a `seeked` listener too), and floating-point seek
  precision could land a hair below a caption's exact `start` time, failing a
  strict `>=` comparison (added a small epsilon tolerance).
