"""Transcription + SRT generation — see design.md's Decisions.

Plain function, no Temporal import (mirrors `worker/llm.py`) — `activities.py` wraps
this with the heartbeat-thread machinery, same shape as `synthesize`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import srt
from faster_whisper import WhisperModel

from worker.types import WordTiming

# large-v2, not large-v3: large-v3 is widely reported (and confirmed on our
# own real episode audio) to hallucinate more than large-v2 on real-world
# audio despite scoring better on clean benchmarks — see design.md. Verified
# a ~48% drop in correctness_check mismatches (31 -> 16) on the same audio.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v2")
# float16 was tried and reverted: empirically, on this GPU/model it produced
# real hallucinations (e.g. an invented sentence, duplicated clauses) not
# present with int8_float16 on the same real audio — see design.md.
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8_float16")


@dataclass
class TranscriptionOutput:
    srt_path: Path
    transcript_text: str
    words: list[WordTiming]


def transcribe_audio(audio_path: Path, lang: str, srt_path: Path) -> TranscriptionOutput:
    # Fresh model load per call — same already-accepted inefficiency as
    # ChatterboxEngine.load() in synthesize(), not something this change fixes.
    model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type=WHISPER_COMPUTE_TYPE)
    # condition_on_previous_text=False was tried and reverted: empirically it
    # caused word/clause duplication ("Pedro lo lo habrá negado") and
    # progressive loss of capitalization/punctuation on real audio — see
    # design.md. vad_filter=True alone was verified clean.
    segments, _info = model.transcribe(
        str(audio_path),
        language=lang,
        word_timestamps=True,
        vad_filter=True,
    )

    subtitles = []
    words: list[WordTiming] = []
    transcript_parts: list[str] = []
    for i, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        transcript_parts.append(text)
        subtitles.append(
            srt.Subtitle(
                index=i,
                start=timedelta(seconds=segment.start),
                end=timedelta(seconds=segment.end),
                content=text,
            )
        )
        for word in segment.words or []:
            words.append(WordTiming(word=word.word.strip(), start=word.start, end=word.end))

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(srt.compose(subtitles), encoding="utf-8")

    return TranscriptionOutput(
        srt_path=srt_path,
        transcript_text=" ".join(transcript_parts),
        words=words,
    )
