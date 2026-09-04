## Context

See proposal.md for motivation. `episode-lifecycle-management` and
`tags-only-edit-fast-path` already established the render-parameter plumbing
pattern (`ScriptIn` → `AudioGenerationWorkflowInput` → `SynthesizeInput` →
`RenderJob`) and the audio-affecting-fields decision in `regenerate_script` this
change extends by one field, not a new mechanism.

## Goals / Non-Goals

**Goals:**
- Make an uploaded voice sample actually reach `narrator`'s synthesis pipeline
  without modifying `narrator` itself.
- Voice management data (files + metadata) survives container recreation the same
  way episode media already does.

**Non-Goals:**
- Audio transcoding / non-WAV uploads.
- Per-engine voice support — Chatterbox is the only engine with cloning
  (`kokoro`'s own code already ignores `--voice` for parity, per its own comment);
  this change doesn't add engine-conditional UI since the UI has never exposed an
  engine picker at all (silently fixed to `"chatterbox"`).
- Auto-importing the two pre-existing `voices/geo.*.wav` files into the new system.
- Renaming a voice, or bulk sample replacement across many voices at once.

## Decisions

**Reuse `resolve_voice()`'s exact filename convention instead of writing new
resolution logic.** The alternative — storing arbitrary per-language paths in the
`voices` Mongo doc and resolving them in `worker/activities.py` directly — would
mean reimplementing (and re-testing) the fallback logic `resolve_voice()` already
has, purely to avoid a fixed naming convention. Since `RenderJob.voice_family` is
already the integration point `narrator` exposes for exactly this, matching its
expected layout (`voice.wav`, `voice.{lang}.wav` in one directory) means
`voice_family_path()`'s result can be handed straight to `RenderJob(...)` with zero
narrator-side changes — the smallest possible integration surface, consistent with
every prior phase's "orchestrate, don't modify" rule. This is also why `languages`
is the only thing stored on the `voices` doc rather than actual file paths: paths
are always derivable from `voice_id` via the fixed convention, so there's nothing
to keep in sync or go stale.

**`worker/voice_storage.py` is a new, tiny, import-light module — not added to
`worker/id3.py` or inlined in `worker/activities.py`.** `api/main.py` needs the
same path-construction logic as `worker/activities.py` (to know where to write
uploads and what to delete), and `worker/types.py`'s own docstring already
establishes the precedent: keep anything `api/main.py` needs import-light so the
API process doesn't pull in `worker/activities.py`'s heavy ML/LLM dependency graph
(the same reasoning `tags-only-edit-fast-path` used for `worker/id3.py`).

**WAV-only uploads, enforced by extension check, not content sniffing.**
`resolve_voice()` builds the per-language filename by swapping in `.{lang}` before
a single shared suffix taken from the `voice_family` path — so every sample in one
voice must share the same extension for that swap to find them. Transcoding
non-WAV uploads to a consistent format would need a new dependency (ffmpeg is
already a system package here, but wiring it in for this is real added surface);
requiring WAV outright — matching the two samples that already exist in `voices/`
— avoids that entirely. A `.wav`-suffix check is enough for this project's
personal-scale, trusted-upload context; deeper content validation isn't justified.

**No cascade from voice deletion into past render_jobs.** A `render_jobs` doc
that already has a finished MP3 doesn't need its `voice_id` to remain resolvable —
the audio's already baked. Deleting a voice only removes it from `GET /voices`
(future selection); nothing about a past render breaks.

## Risks / Trade-offs

- **[Risk] Deleting a voice while a render referencing it is still in-flight.**
  → Accepted, same shape as `episode-lifecycle-management`'s existing edge cases:
  `SynthesizeInput.voice_id` is captured at `start_workflow` time, and
  `worker/activities.py::synthesize` resolves the file path fresh at execution
  time — if the voice's files are deleted mid-render, that render fails the same
  way any other missing-file error would (caught by `render_job()`'s own
  try/except, surfaced as a normal `"failed"` status). Not a new failure mode this
  change introduces, and not expected to matter in practice at personal-scale,
  single-operator usage.
