# Mx Narrator Studio

A self-hosted pipeline that turns a biblical reflection script into a finished,
captioned video with YouTube-ready metadata — built for a small team producing a
weekly multilingual (Spanish, English, Portuguese) devotional series.

```
script  ->  narrated MP3  ->  transcribed & reviewed captions  ->  captioned video  ->  LLM-generated title/description/tags
```

A human approves every consequential step along the way — captions, corrections,
metadata. The system never touches YouTube itself: it stops at "everything is ready
for you to upload," staged in the web UI for you to publish manually. See
[`docs/rfc-narrator-studio.md`](docs/rfc-narrator-studio.md) for the full design and
the reasoning behind that boundary.

## Architecture

- **[`mx-narrator`](#the-mx-narrator-cli)** — the underlying narration CLI (voice
  cloning, multilingual scripture/number handling, ID3 tagging). The Studio
  orchestrates it; it's also fully usable on its own.
- **Temporal** — durable, observable workflow execution (`AudioGenerationWorkflow`,
  `VideoProductionWorkflow`, `ReviseCaptionsWorkflow`), survives worker restarts and
  GPU contention.
- **MongoDB** — pipeline state, with change streams pushed to the web UI live via
  Server-Sent Events (no polling).
- **FastAPI** — the backend the web UI and Temporal workers talk to.
- **React (Vite)** — the review/approval UI.
- **Docker Compose** — everything self-hosted on one GPU-equipped host, no recurring
  cloud costs.

## Running the Studio

```bash
cd deploy
docker compose up -d --build
```

Then open:

| | |
|---|---|
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 |
| Temporal UI | http://localhost:8080 |

See [`deploy/README.md`](deploy/README.md) for prerequisites, service breakdown,
LLM-provider configuration, and troubleshooting.

## The pipeline

1. **Upload a script** in the web UI — sets the ID3 tags and render parameters
   (speed, expressiveness, CFG weight), starts `AudioGenerationWorkflow`.
2. **Audio renders** via the `mx-narrator` CLI's real voice-cloning pipeline. You can
   replace the resulting file directly (e.g. after adding music externally) before
   moving on — the upload becomes what everything downstream uses.
3. **Start video production**: upload a background image, `VideoProductionWorkflow`
   transcribes the audio (faster-whisper) and checks it against the exact text that
   was synthesized — catching TTS content problems (dropped or repeated speech)
   before they reach a viewer.
4. **Review captions** — always, not just when a mismatch is found. Caption text is
   fully editable, synced to audio playback, with any correctness-check mismatches
   highlighted right on the caption they affect.
5. **Video renders** with captions burned in, then an LLM generates a YouTube
   title/description/tags draft.
6. **Final review**: captions, background image, and metadata are all editable
   together in one screen — edit any of them, save once. Nothing re-renders unless
   something actually changed.
7. **Ready for manual upload.** The finished video and metadata sit in the UI; you
   upload to YouTube yourself and check it off. The system never does this step for
   you.

## The `mx-narrator` CLI

A CLI that turns biblical reflection scripts into narrated MP3s — in Spanish, English,
and Portuguese — running entirely locally on an NVIDIA GPU. Built for a weekly ten-part
series on 1 John, where each unit exists as a parallel translation in all three languages.

The quality bar is not "intelligible." It's that the result sounds like a person reading
with reverence, in each language.

### Requirements

- Linux, an NVIDIA GPU (Chatterbox needs ~4 GB VRAM; more GPUs let `batch` render a
  unit's three languages in parallel — see [Multi-GPU](#multi-gpu-batch)).
- [`uv`](https://docs.astral.sh/uv/) for Python and dependency management.
- System packages (not installed by `uv`): `ffmpeg` and `espeak-ng`.

  ```bash
  # Debian/Ubuntu
  sudo apt install ffmpeg espeak-ng

  # Fedora
  sudo dnf install ffmpeg espeak-ng
  ```

### Install

```bash
uv sync
```

This resolves Python 3.11 and installs everything, including a CUDA-enabled PyTorch —
modern PyTorch's default Linux pip wheel bundles CUDA support (via the `nvidia-*`
packages), so no special `[tool.uv.sources]` index is needed for a standard NVIDIA setup.
Model weights (Chatterbox Multilingual, several hundred MB) download on first use and
cache under `~/.cache/huggingface/`.

**Known packaging issue, already worked around in `pyproject.toml`:** Chatterbox's
watermarking dependency (`resemble-perth`) still imports the deprecated `pkg_resources`
API. Recent `setuptools` releases (80+) no longer vendor `pkg_resources` at all, and `uv`
venvs don't install `setuptools` by default the way old `pip` venvs did — so without help,
loading the model fails with `TypeError: 'NoneType' object is not callable` deep inside
`chatterbox.mtl_tts`. This project pins `setuptools<81` to route around it.

### Quickstart

```bash
# one script
uv run mx-narrator scripts/1jn-1-1-4.es.txt -o out/

# a whole unit, every language version that exists
uv run mx-narrator unit 1jn-1-1-4 -o out/ --voice voices/geo.wav

# only two of the three languages
uv run mx-narrator unit 1jn-1-1-4 --langs es,pt

# fast draft to proof the script (seconds, not GPU-minutes)
uv run mx-narrator scripts/1jn-1-1-4.en.txt --engine kokoro --draft

# audition voices without a full render
uv run mx-narrator scripts/1jn-1-1-4.pt.txt --preview 600 --voice voices/geo.wav

# check what prep will do before spending any GPU time
uv run mx-narrator scripts/1jn-1-1-4.es.txt --dry-run

# whole series, all languages, across every available GPU
uv run mx-narrator batch scripts/ -o out/ --gpus 0,1,2,3
```

Two example scripts ship in `scripts/` (`vertical-slice.*.txt`, the parallel-translation
paragraph used to sanity-check the pipeline, and `1jn-1-1-4.es.txt`, which exercises
headings, a blockquote, a parenthetical, and several scripture references) with their
rendered `out/*.mp3` — a quick way to hear the pipeline work without waiting on a full
unit.

#### CLI options

| Option | Effect |
|---|---|
| `--engine {chatterbox,kokoro}` | Synthesis engine. Defaults to `chatterbox`. |
| `--lang {es,en,pt}` | Override language resolution for a single file. |
| `--langs es,en,pt` | For `unit`/`batch`: which languages to render. Defaults to all found. |
| `--voice PATH` | Reference sample family, resolved per language — see [Voice identity](#voice-identity-across-languages). |
| `--speed FLOAT` | Defaults to `0.95` — the material is reflective, not informational. |
| `--expressiveness FLOAT` | Chatterbox only. Defaults low (`0.3`) — devotional, not promotional. |
| `--cfg-weight FLOAT` | Chatterbox only. Defaults to `0.5` (library default). Pacing control — **higher reads faster/more rushed, lower is slower and more deliberate** (measured: ~13% shorter audio for the same text going from `0.5` to `2.0`). Counterintuitive at first glance, so worth stating plainly: to fix rushed-sounding narration, lower this, don't raise it. |
| `--preview N` | Synthesize only the first N characters. |
| `--draft` | Shorthand for `--engine kokoro --format wav`, skipping loudness normalization and ID3 tagging. |
| `--seed INT` | Fixed seed (default `0`), for reproducible synthesis. |
| `--dry-run` | Run prep only and print the prepared text — no synthesis. |
| `--format {mp3,wav}` | Defaults to `mp3`. |

### Synthesis engines

**Chatterbox Multilingual** (default) — MIT licensed, covers all three target languages,
clones a voice from ~5 seconds of reference audio, and exposes an "exaggeration" control
kept low by default for devotional material. ~4 GB VRAM.

**Kokoro** (`--engine kokoro`) — Apache 2.0, faster than real time even on CPU, no voice
cloning. Used for `--draft` proofing passes — catching a mangled scripture reference in
seconds instead of GPU minutes — not for final renders.

#### Evaluated and rejected

- **XTTS-v2** — comparable or better cloning quality, but CPML-licensed (non-commercial
  only) and Coqui shut down in January 2024, so there's no path to a commercial license.
- **F5-TTS** — needs 12–16 GB VRAM for no benefit here.
- **IndexTTS-2** — its strength is Asian languages, not the Latin-alphabet trio this
  project needs.
- **CosyVoice 2, Fish Speech** — evaluated, no compelling advantage over Chatterbox for
  this use case.

### Voice identity across languages

The goal is that all three language versions of a unit sound like the same narrator.
Reference samples resolve per language with a family fallback:

```
voices/geo.es.wav   ->  used for Spanish
voices/geo.en.wav   ->  used for English
voices/geo.pt.wav   ->  used for Portuguese
voices/geo.wav      ->  fallback for any language with no specific sample
```

`--voice voices/geo.wav` selects the family; the per-language file is used when present,
else the tool falls back to the bare file. Every render logs which sample was actually
used — when one language sounds off, that's the first thing to check.

**Recording quality matters more than the docs suggest.** Chatterbox will accept ~5
seconds, but 15–30 seconds of clean audio makes a noticeable difference: mono, no
background music, no reverb, no clipping. A bad sample ruins the output no matter how
good the model is.

**Strategy, in preference order** (see spec section 8 for the full reasoning):

1. One reference sample per language, same speaker — highest quality, identity
   genuinely preserved.
2. One reference sample, cross-lingual cloning — identity preserved, but expect some
   accent bleed.
3. A different voice per language — best per-language naturalness, but the series loses
   its single narrator. Fall back to this only if option 2 sounds wrong.

Cross-chunk voice drift (the model's timbre subtly shifting between fragments) is
avoided by computing the reference embedding once via Chatterbox's
`prepare_conditionals()` and reusing it for every chunk in a render, rather than
recomputing it from the reference file on every call.

**Pinned to Chatterbox Multilingual V3, not the V2 checkpoint the PyPI release
(`chatterbox-tts` 0.1.7) hardcodes** — via a specific commit under `[tool.uv.sources]` in
`pyproject.toml`, since V3 isn't on PyPI yet. This followed directly from a problem: V2's
`AlignmentStreamAnalyzer` forces an abrupt EOS override on the large majority of chunks
(it zeroes out every token's logit except EOS and forces it, regardless of what the model
was mid-way through generating), which the vocoder renders as an audible chirp/glitch
right at the end of the chunk. Earlier versions of this project watched V2's analyzer log
output and worked around this — retrying unstable chunks with an escalating
`repetition_penalty`, then trimming the tail of every forced-stop — but V3's generation
loop doesn't have that analyzer at all anymore. Confirmed directly in the installed
source: V3 instead unconditionally drops the final speech token's audio on every call,
with its own comment explaining why — *"it is emitted just before EOS with degraded
attention and decodes to ~40ms of noise"* — a precise, native fix, so no equivalent
trimming happens in this project's code anymore.

**The tradeoff, worth stating plainly:** V2's analyzer was also the only signal this
project had for detecting a genuine repetition/hallucination loop, which is what drove
the automatic retry. That detection doesn't exist against V3 — it relies solely on a
standard `repetition_penalty` logits processor (still passed through, default `1.2`, no
escalation), same idea, no custom analyzer layered on top. If V3 does hallucinate or loop
despite that, there is currently no detection and no automatic retry — it would ship
as-is. This is a deliberate choice, not an oversight: V3 is specifically trained to need
this less, and rebuilding an equivalent safety net from scratch (nothing native to hook
into anymore) isn't worth the complexity unless it turns out to be a real problem in
practice.

### How text becomes speech

1. **`prep`** (`src/mx_narrator/prep/`) strips markdown structurally (not with a `strip()`
   call) into blocks — headings, paragraphs, blockquotes — preserving blank lines and
   headings as pauses rather than dropping them. Each language pack then expands
   scripture references, numbers, and abbreviations, and splits long sentences at
   sentence and clause boundaries. `--dry-run` prints the result before any GPU time is
   spent.
2. **`chunk`** packs the prepared sentences into TTS-call-sized pieces without ever
   splitting a sentence. A short one-line paragraph — a rhetorical fragment like "Fue
   oído." — is disproportionately likely to trigger Chatterbox's repetition instability
   when synthesized alone (observed in practice), so a paragraph block that comes out
   shorter than ~50 characters on its own is folded into a neighboring paragraph's TTS
   call instead. That specific paragraph-boundary pause is skipped where this happens
   (the two become one continuous synthesized segment), but every other boundary —
   including both edges of the folded group — still gets its normal pause. Headings and
   quotes are never folded regardless of length; their bracketing pauses are structurally
   meaningful, not just a length threshold.
3. **engines** synthesize each chunk to a WAV.
4. **`assemble`** concatenates chunks via ffmpeg's `concat` filter, inserts silence at
   real block boundaries (600ms between paragraphs, 1200ms around headings, 900ms around
   quoted scripture), normalizes loudness to -16 LUFS, encodes to MP3, and writes ID3
   tags (title, artist, album, track, and language).

#### Language packs

Each of `prep/langs/{es,en,pt}.py` owns its own 66-book scripture abbreviation table,
number-expansion rules, and abbreviation list — nothing outside `prep/langs/` branches on
language code. Tables are never shared across languages on purpose: Spanish `Jue` and
Portuguese `Jz` are both Judges, but Portuguese `Jo` is John while Spanish uses `Jn` for
it. A shared table would silently produce the wrong book name.

### Testing

```bash
uv run pytest
```

Covers every worked example from the scripture and number tables (all three languages),
prep idempotency on already-prepared text, sentence splitting, structural markdown
cleanup, and the full chunk → synth → assemble → tag pipeline (using a fake engine, so it
runs without a GPU). This covers the CLI (`src/mx_narrator/`) only — the Studio layer
(`worker/`, `api/`, `web/`) is verified against real infrastructure (Docker, Temporal,
MongoDB) rather than a mocked unit-test suite; see the archived OpenSpec changes under
`openspec/changes/archive/` for that verification history.

GPU-dependent tests (real Chatterbox inference, including the seed-reproducibility check
described in the spec's "voice drift" trap) are marked `slow` and skipped by default:

```bash
uv run pytest -m slow  # requires a CUDA GPU and downloads model weights on first run
```

### Known limitations / things to verify for your setup

- **European vs. Brazilian Portuguese**: the Portuguese pack defaults to the `pt_BR`
  num2words locale, on the assumption that an ARC-translation audience is Brazilian. If
  your audience expects European Portuguese, this needs revisiting (`prep/langs/pt.py`).
- **Scripture abbreviation coverage**: all 66 books are mapped per language, but only
  the most common abbreviation spellings are included. An unrecognized reference is left
  untouched and flagged by `sanity_checks` (visible in `--dry-run` and log warnings)
  rather than guessed at.
- **Single-GPU development machine**: `batch`'s multi-GPU distribution is implemented
  and tested with `--gpus 0`, but wasn't exercised across multiple physical GPUs during
  development.
