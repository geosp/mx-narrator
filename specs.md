# Project: `mx-narrator` — local multilingual narration CLI

Build spec for Claude Code. Anything marked **DECIDED** is already settled — implement it,
don't re-evaluate it. Anything marked **VERIFY** requires you to check current
documentation before writing code.

The tool's own prose, code, and docs are in English. The **content it processes is not** —
it narrates Spanish, English, and Portuguese. Every example in sections 6 and 7 is in the
language it belongs to on purpose. Do not "normalize" them.

---

## 1. Goal

A CLI that turns biblical reflection scripts into narrated MP3s — **in Spanish, English,
and Portuguese** — running entirely locally on NVIDIA GPUs.

The concrete use case: a ten-part series on 1 John, where **each unit exists as a parallel
translation in all three languages**. Each script runs 3,000–4,000 words, which is twenty
to thirty minutes of audio. That means roughly thirty renders for one series, produced a
unit at a time, weekly. The tool must make it cheap to iterate on voice, speed, and
pronunciation, and it must treat the three language versions of a unit as one thing with
three outputs, not three unrelated jobs.

**The quality bar is not "intelligible."** It is that the result sounds like a person
reading with reverence, in each language. If the output sounds like a synthesizer, or if
the English version sounds like a Spanish speaker's voice model straining, the project
failed even if it runs.

---

## 2. Environment

- Local machine with **multiple NVIDIA GPUs** and ample memory.
- Linux (assumed; if Windows, adapt paths and `CUDA_VISIBLE_DEVICES` handling).
- Package manager: **`uv`** — DECIDED.
- Python **3.11** — DECIDED. Do not move to 3.12+ without verifying that torch and the TTS
  model ship wheels for it; this ecosystem tends to lag a release behind.

On the multiple GPUs, so no effort is wasted: **none of the TTS models here shard across
cards.** A single file uses a single GPU. Parallelism belongs at the batch level. With
three languages per unit, the natural mapping is one render per GPU — a four-GPU box
finishes a unit's three languages in roughly the time of one (see section 9).

---

## 3. Synthesis engine — DECIDED, with caveats

### Primary engine: Chatterbox Multilingual (Resemble AI)

Reasons, in order of weight:

1. **It covers all three languages.** Spanish, English, and Portuguese all sit inside its
   23-language set. A single engine for the whole pipeline is worth a great deal here —
   two engines means two sets of quirks, two voice systems, and outputs that don't match
   each other.
2. **MIT license.** XTTS-v2 is comparable or better at cloning, but it ships under CPML —
   non-commercial only — and Coqui shut down in January 2024, so there is nobody left to
   buy a commercial license from. For material that may be distributed to a congregation
   or published, MIT removes the entire problem.
3. **Voice cloning** from roughly five seconds of reference audio, including across
   languages (see section 8, which is where the real difficulty lives).
4. Modest footprint: about **4 GB of VRAM**, so several renders fit on one card if needed.
5. An expressiveness control ("exaggeration") that can be dialed *down* — relevant here,
   because the material is devotional, not promotional.

**VERIFY** before installing: the exact PyPI package name, the current API, how the
multilingual model differs from the English base model, and the language codes it expects.

### Secondary engine: Kokoro (fast drafts)

Kokoro-82M, Apache 2.0, runs faster than real time even on CPU, and it has usable voices
for all three target languages (`em_alex` Spanish, `am_puck` / `bm_george` English,
`pm_alex` Portuguese). It has **no voice cloning** and its non-English voices are a clear
step down, but it is ideal for proofing a script — especially for catching a mangled
scripture reference — in seconds instead of GPU minutes.

Expose it as `--engine kokoro`. The default engine is Chatterbox.

### Do not implement for now

XTTS-v2 (license), F5-TTS (needs 12–16 GB VRAM and adds nothing here), IndexTTS-2 (its
strength is Asian languages), CosyVoice 2, Fish Speech. List them in the README as
evaluated-and-rejected, with the reason.

---

## 4. Project layout

```
mx-narrator/
├── pyproject.toml
├── uv.lock
├── README.md
├── src/mx_narrator/
│   ├── __init__.py
│   ├── cli.py                 # entry point, arguments
│   ├── units.py               # unit discovery, language pairing, naming
│   ├── prep/
│   │   ├── __init__.py        # orchestration: pick pack, run pipeline
│   │   ├── base.py            # LanguagePack protocol — see section 5
│   │   ├── common.py          # language-neutral steps (markdown stripping, blocks)
│   │   ├── registry.py        # code -> pack
│   │   └── langs/
│   │       ├── es.py
│   │       ├── en.py
│   │       └── pt.py
│   ├── detect.py              # language resolution, fail-loud
│   ├── chunk.py               # sentence-boundary chunking within model limits
│   ├── engines/
│   │   ├── base.py            # shared interface: synth(text, lang, out_path, **opts)
│   │   ├── chatterbox.py
│   │   └── kokoro.py
│   ├── voices.py              # reference-sample resolution per language
│   ├── assemble.py            # concatenation, silences, loudness, tagging
│   └── batch.py               # multi-GPU batch runner
├── voices/                    # reference samples (see section 8 for naming)
├── scripts/                   # input scripts, named <unit>.<lang>.txt
└── out/                       # resulting MP3s, named <unit>.<lang>.mp3
```

---

## 5. Language packs — the extension point

**DECIDED:** language-specific behavior lives behind one interface, and nothing outside
`prep/langs/` may branch on language code. Adding a fourth language must mean writing one
new module and registering it, never touching the pipeline.

The protocol each pack implements:

```python
class LanguagePack(Protocol):
    code: str                     # "es" | "en" | "pt"
    num2words_locale: str         # "es" | "en" | "pt_BR"
    kokoro_voice: str             # fallback engine default voice

    def expand_scripture(self, text: str) -> str: ...
    def expand_numbers(self, text: str) -> str: ...
    def expand_abbreviations(self, text: str) -> str: ...
    def split_sentences(self, text: str) -> list[str]: ...
    def sanity_checks(self, text: str) -> list[str]: ...   # warnings, not exceptions
```

**Each pack owns its own 66-book abbreviation table. Never share one across languages.**
This is not tidiness, it is correctness: the same abbreviation means different books in
different languages, and a shared table will silently produce the wrong book name. Spanish
`Jue` is Judges while Portuguese `Jz` is the same book and `Jo` is John; English `Jn` is
John while `Jg` is Judges. Cross-contamination here is the kind of bug nobody catches
until it is in the audio.

---

## 6. Text preparation — the part that actually matters

This module is where the project is won or lost. A TTS engine reads literally whatever you
hand it. **Do not implement this as a markdown `strip()`.**

### 6.1 Structural cleanup (language-neutral, lives in `common.py`)

- Remove markdown syntax: `#`, `*`, `_`, backticks, link syntax, table pipes, horizontal
  rules.
- Headings become **spoken lines followed by a long pause** — they are not dropped.
- URLs are removed entirely. They are unlistenable.
- Blank lines in the source mark pauses. Preserve them as metadata; do not discard them.

### 6.2 Sentence shape (language-neutral rule, language-specific splitting)

- Break any sentence over ~25 words. A listener cannot re-scan a clause.
- Replace semicolons and parentheticals with separate sentences. Parenthetical asides are
  especially bad — the listener has no closing bracket to see.
- Spanish and Portuguese run to longer sentences than English. Break those harder than the
  source suggests.

### 6.3 Expected behavior

`prep` must be **idempotent and auditable**. `--dry-run` prints the result so the user can
review before spending GPU time. If a transformation is uncertain, log it rather than
applying it silently.

Scripts for this series **arrive already hand-prepared** — references expanded, sentences
short. `prep` must not damage them: clean input should pass through essentially untouched,
in every language. Write a test that proves it, per pack.

---

## 7. Per-language rules

### 7.1 Spanish (`es`)

**Never strip accents or opening marks.** `¿` and `¡` are what give the synthesizer the
right intonation; without them a question reads flat. `ñ` is not `n`.

Numbers: `2026` → "dos mil veintiséis" · `3,5` → "tres coma cinco" · `1.000` → "mil" ·
`1º`/`1ª` → "primero"/"primera".

Scripture — ranges use **"al"**:

| Written | Spoken |
|---|---|
| `1 Jn 1:1-4` | Primera de Juan, capítulo uno, versículos uno al cuatro |
| `Jn 1:1` | Juan, capítulo uno, versículo uno |
| `Ro 8:28` | Romanos ocho, veintiocho |
| `Sal 23` | Salmo veintitrés |
| `1 Co 13` | Primera de Corintios trece |
| `Heb 12:18-24` | Hebreos, capítulo doce, versículos dieciocho al veinticuatro |
| `vv. 4-6` | versículos cuatro al seis |
| `v. 2` | versículo dos |

### 7.2 English (`en`)

Numbers: `2026` → "twenty twenty-six" · `3.5` → "three point five" · `1,000` → "one
thousand". Note the decimal separator is **inverted** relative to Spanish and Portuguese —
see the trap in section 11.

Scripture — ranges use **"through"**:

| Written | Spoken |
|---|---|
| `1 Jn 1:1-4` | First John, chapter one, verses one through four |
| `Jn 1:1` | John, chapter one, verse one |
| `Rom 8:28` | Romans eight, twenty-eight |
| `Ps 23` | Psalm twenty-three |
| `1 Cor 13` | First Corinthians thirteen |
| `Heb 12:18-24` | Hebrews, chapter twelve, verses eighteen through twenty-four |
| `vv. 4-6` | verses four through six |
| `v. 2` | verse two |

### 7.3 Portuguese (`pt`)

Keep accents and the tilde: `ã`, `õ`, `ç`, `é`, `ê` all change the word or its stress.

Numbers: `2026` → "dois mil e vinte e seis" · `3,5` → "três vírgula cinco" · `1.000` →
"mil". Use the `pt_BR` locale in `num2words` unless the user asks for European Portuguese
— **VERIFY** which the ARC translation's audience expects.

Scripture — ranges use **"a"**:

| Written | Spoken |
|---|---|
| `1 Jo 1:1-4` | Primeira de João, capítulo um, versículos um a quatro |
| `Jo 1:1` | João, capítulo um, versículo um |
| `Rm 8:28` | Romanos oito, vinte e oito |
| `Sl 23` | Salmo vinte e três |
| `1 Co 13` | Primeira de Coríntios treze |
| `Hb 12:18-24` | Hebreus, capítulo doze, versículos dezoito a vinte e quatro |
| `vv. 4-6` | versículos quatro a seis |
| `v. 2` | versículo dois |

### 7.4 Ambiguity rule (all languages)

`Juan 1:1` / `John 1:1` / `João 1:1` could be the Gospel or the epistle. If the reference
carries a numeral prefix, it is the epistle. Bare, it is the Gospel. **Do not guess beyond
that** — log a warning and leave the text alone rather than inventing a resolution.

---

## 8. Voice identity across languages — the hard problem

This is the section most likely to be underestimated. Read it before designing `voices.py`.

The goal is that the three language versions of a unit sound like **the same narrator**,
because they are meant to be the same series. But cloning a voice from a Spanish sample and
having it read English tends to carry the source accent, and quality varies by language
pair.

Three strategies, in preference order:

1. **One reference sample per language, same human speaker.** Highest quality by a wide
   margin, and identity is preserved because it genuinely is the same person. Requires the
   narrator to speak all three. If the user can supply this, nothing else competes.
2. **One reference sample, cross-lingual cloning.** Identity is preserved, but expect
   accent bleed. **VERIFY** how Chatterbox Multilingual handles cross-lingual conditioning
   and whether it exposes a language tag separate from the reference audio.
3. **A different voice per language.** Best naturalness per language, but the series loses
   its single narrator. Fall back to this only if strategy 2 sounds wrong.

Implement resolution that supports all three without code changes:

```
voices/geo.es.wav   ->  used for Spanish
voices/geo.en.wav   ->  used for English
voices/geo.pt.wav   ->  used for Portuguese
voices/geo.wav      ->  fallback for any language with no specific sample
```

`--voice voices/geo.wav` selects the *family*; `voices.py` resolves the per-language file
and falls back to the bare name. Log which sample was actually used for each render — when
one language sounds off, this is the first thing to check.

**Reference sample quality.** The model asks for about five seconds, but quality improves
noticeably with 15–30 seconds of clean audio: mono, no background music, no reverb, no
clipping. Document this in the README, because a bad sample ruins the output no matter how
good the model is.

---

## 9. Units, pairing, and batch

### Naming — DECIDED

- Input: `scripts/<unit-id>.<lang>.txt`, e.g. `scripts/1jn-1-1-4.es.txt`
- Output: `out/<unit-id>.<lang>.mp3`

The unit id is **language-neutral** so the three versions sort together and pair
automatically. `units.py` discovers units by globbing and grouping on the id.

### Language resolution — fail loud

Resolve in this order: the `--lang` flag, then the filename suffix, then content-based
detection. **If detection is not confident, error out rather than guessing.** Guessing
wrong does not produce a slight accent — it applies the wrong scripture table and the wrong
number locale, and the whole narration is subtly broken in a way that is tedious to
diagnose from audio.

### Batch

`mx-narrator batch scripts/ -o out/ --gpus 0,1,2,3` discovers units, expands each into one
render per available language version, and distributes the renders across GPUs — one
process per GPU with `CUDA_VISIBLE_DEVICES` pinned, fed from a shared work queue.

Do not try to split one render across GPUs. Report progress per render, and make sure one
failure does not take down the batch. Print a summary at the end listing which unit ×
language combinations succeeded, failed, or were missing a source script.

---

## 10. CLI surface

```bash
# one script
uv run mx-narrator scripts/1jn-1-1-4.es.txt -o out/

# a whole unit, every language version that exists
uv run mx-narrator unit 1jn-1-1-4 -o out/ --voice voices/geo.wav

# only two of the three
uv run mx-narrator unit 1jn-1-1-4 --langs es,pt

# fast draft to proof the script
uv run mx-narrator scripts/1jn-1-1-4.en.txt --engine kokoro --draft

# audition voices without a full render
uv run mx-narrator scripts/1jn-1-1-4.pt.txt --preview 600 --voice voices/geo.wav

# whole series, all languages, across four GPUs
uv run mx-narrator batch scripts/ -o out/ --gpus 0,1,2,3
```

| Option | Effect |
|---|---|
| `--engine {chatterbox,kokoro}` | Engine. Defaults to `chatterbox`. |
| `--lang {es,en,pt}` | Override language resolution for a single file. |
| `--langs es,en,pt` | For `unit` and `batch`: which languages to render. Defaults to all found. |
| `--voice PATH` | Reference sample family. Resolved per language — see section 8. |
| `--speed FLOAT` | Defaults to `0.95` — the material is reflective, not informational. |
| `--expressiveness FLOAT` | Chatterbox only. Defaults **low** (~0.3). |
| `--preview N` | Synthesize only the first N characters. |
| `--draft` | Shorthand for `--engine kokoro --format wav`, skipping loudness and tagging. |
| `--seed INT` | Fixed seed. **Defaulted, not random** — see section 11. |
| `--dry-run` | Run prep only and print the prepared text. No synthesis. |
| `--format {mp3,wav}` | Defaults to `mp3`. |

On expressiveness: the default must be **low**. These models tend to overact, and in
devotional material a theatrical read is grotesque. Let the user dial it up, not down.

---

## 11. Synthesis, assembly, and known traps

### Chunking

Models cap tokens per call. Chunk **at sentence boundaries**, never mid-sentence. Pack
sentences up toward the limit rather than sending one per call — fewer calls means fewer
audible seams. Sentence splitting is language-specific and belongs in the pack.

### Silences

Insert digital silence between blocks rather than relying on the model:

- Between sentences inside a paragraph: whatever the model produces, add nothing.
- Between paragraphs (blank line): **600 ms**.
- Before and after a section heading: **1,200 ms**.
- Before and after a long scripture quotation: **900 ms**.

### Post-processing

1. Concatenate with `ffmpeg` (use the `concat` filter, not `-f concat` with a list file).
2. **Normalize loudness** with `loudnorm` to **-16 LUFS**, the spoken-word standard.
   Apply identical settings across languages so the three versions match.
3. Encode to MP3, mono, 128 kbps, 44.1 kHz.
4. Write ID3 tags: title, artist, album (series name), track number, **and the language
   tag** so players and podcast feeds handle the three versions correctly.

### Traps

**Voice drift between chunks.** The most irritating failure mode of cloning models: timbre
shifts subtly between fragments and the result sounds like several people. Compute the
reference embedding **once** and reuse it across every call, and **fix the seed**. That is
why `--seed` has a default. Write a test that synthesizes the same text twice with the same
seed and asserts the audio is identical.

**Inverted decimal separators.** `3.5` is three-point-five in English and three-thousand-
five-hundred-ish nonsense if parsed with Spanish rules; `1.000` is one thousand in Spanish
and Portuguese but one-point-zero-zero-zero in English. A shared number parser will mangle
this. Number handling belongs in the pack, always.

**Shared abbreviation tables.** Covered in section 5. Worth repeating because it fails
silently.

**PyTorch CUDA wheels.** `uv` does not resolve from the PyTorch index by default. You will
need `[tool.uv.sources]` or the `cu12x` extra index in `pyproject.toml`. **VERIFY** which
index matches the machine's CUDA version before pinning.

**System dependencies.** Several engines need `espeak-ng` for phonemization and `ffmpeg`
for audio. Not Python packages — document them with the distro install command.

**Model downloads.** Weights run to hundreds of megabytes. Cache at a stable path
(`~/.cache/mx-narrator/`) and do not re-download per run.

---

## 12. Acceptance criteria

1. `uv sync` produces a working environment on a clean machine with an NVIDIA GPU.
2. `--dry-run` correctly expands every scripture reference in the section 7 tables — **all
   three languages**, each against its own table.
3. A ~3,600-word script produces a 23–25 minute MP3 with even loudness start to finish, in
   each language.
4. With `--voice` and reference samples, the voice **does not drift** within a render, and
   the three language versions of one unit are recognizably the same narrator.
5. `mx-narrator unit <id>` renders every language version that exists and names the outputs
   consistently.
6. `--preview 600` returns a fragment in under thirty seconds.
7. `batch` across four GPUs processes a unit's three languages in roughly the time of one
   render.
8. Language resolution **errors out** on an ambiguous file instead of guessing.
9. Each language pack has tests, including the idempotency test on already-prepared text.

---

## 13. First deliverable

Before building everything, produce a **vertical slice**: install Chatterbox, synthesize the
same paragraph in Spanish, English, and Portuguese from one cloned voice, write three MP3s.
Have the user listen and confirm two things — that the quality justifies the project, and
that the three renders sound like the same person.

If either fails, stop and report it. The voice-identity question (section 8) is the one
most likely to force a change of strategy, and it is much cheaper to discover it here than
after the pipeline is built around it.