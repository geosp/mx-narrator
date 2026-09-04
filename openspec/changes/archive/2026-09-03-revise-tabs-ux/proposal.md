## Why

Follow-up to `unified-final-review`: the `ReadyForUpload`/`failed` screens
(out of that change's scope) still had "Revise captions"/"Replace
background image" as two collapsed links, each hiding its content until
clicked. User feedback: replace the collapsed-link pattern with tabs, so
the caption editor (and the video above it) stay visible without an extra
click.

## What Changes

`web/src/VideoReview.jsx` only, pure UX — no backend changes, since
`srt/revise`/`image/revise` (still separate actions here, unlike the
unified `revise-all` used by Final review — this status has no live
workflow to signal for a cheap combined save) already existed and needed no
changes:
- `ReviseCaptionsToggle`/`ReviseImageToggle` (collapsed links) replaced by
  `ReviseTabs` — a two-tab switcher ("Captions" / "Background image"), each
  tab's content only mounted while active, defaulting to "Captions" open.
- Extracted `ImageReviseForm` (the plain upload-form guts, previously
  inlined in `ReviseImageToggle`) so `ReviseTabs` can render it directly.
- Both usage sites (`ReadyForUpload`, the `failed` block) updated.

## Capabilities

Pure frontend presentation change — no new capability, no data-model or API
change. `skip_specs: true`.

## Impact

- `web/src/VideoReview.jsx` only.
- Verified end-to-end on a throwaway test video_job pushed to
  `ready_for_manual_upload`: Playwright screenshots confirm both tabs
  render correctly, default to "Captions," and switch cleanly to
  "Background image" — video and metadata stay visible throughout, no
  collapsed content.
- Cleaned up the throwaway video_job, media, and scratch files.
