"""Dataclasses shared between the Temporal worker and the FastAPI backend.

Deliberately has zero mx_narrator/torch/pymongo imports — the `api` service (which
starts workflows but has no GPU/ML stack) imports only this module, not
`worker.activities` or `worker.workflows`, to build type-correct Temporal workflow
input without pulling in mx_narrator's heavy dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Id3Fields:
    artist: str
    title: str
    album: str
    track: int = 1
    year: str = ""
    genre: str = ""
    comments: str = ""


@dataclass
class SynthesizeInput:
    render_job_id: str
    unit_id: str
    lang: str
    script_text: str
    id3: Id3Fields
    engine_name: str = "chatterbox"
    speed: float = 0.95
    exaggeration: float = 0.3
    cfg_weight: float = 0.5
    seed: int = 0
    series_album: str = ""
    title: str | None = None
    voice_id: str | None = None


@dataclass
class SynthesizeResult:
    audio_path: str


@dataclass
class AudioGenerationWorkflowInput:
    render_job_id: str
    unit_id: str
    lang: str
    script_text: str
    id3: Id3Fields
    engine_name: str = "chatterbox"
    speed: float = 0.95
    exaggeration: float = 0.3
    cfg_weight: float = 0.5
    seed: int = 0
    series_album: str = ""
    title: str | None = None
    voice_id: str | None = None


@dataclass
class VideoMetadataFields:
    title: str
    description: str
    tags: list[str]


@dataclass
class GenerateMetadataInput:
    render_job_id: str


@dataclass
class GenerateMetadataResult:
    metadata: VideoMetadataFields


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class TranscribeInput:
    video_job_id: str
    audio_path: str
    lang: str


@dataclass
class TranscribeResult:
    srt_path: str
    transcript_text: str
    words: list[WordTiming]


@dataclass
class Mismatch:
    expected: str
    actual: str
    approx_time: float


@dataclass
class CorrectnessCheckInput:
    script_text: str
    lang: str
    words: list[WordTiming]


@dataclass
class CorrectnessCheckResult:
    status: str  # "pass" | "mismatch"
    mismatches: list[Mismatch]


@dataclass
class VideoProductionWorkflowInput:
    video_job_id: str
    render_job_id: str
    audio_path: str
    script_text: str
    lang: str
    image_path: str = ""


@dataclass
class FinalizeSrtInput:
    video_job_id: str
    srt_path: str
    srt_text: str


@dataclass
class RenderVideoInput:
    video_job_id: str
    image_path: str
    audio_path: str
    srt_path: str


@dataclass
class RenderVideoResult:
    video_path: str


@dataclass
class SaveMetadataDraftInput:
    video_job_id: str
    render_job_id: str
    metadata: VideoMetadataFields


@dataclass
class ApproveMetadataInput:
    video_job_id: str
    title: str
    description: str
    tags: list[str]


@dataclass
class AlignCaptionsInput:
    video_job_id: str
    audio_path: str
    lang: str
    srt_path: str


@dataclass
class AlignCaptionsResult:
    aligned: bool


@dataclass
class ReviseCaptionsWorkflowInput:
    video_job_id: str
    render_job_id: str
    srt_path: str
    srt_text: str
    image_path: str
    audio_path: str
    lang: str
    metadata_already_approved: bool
    # Set only by the unified "revise-all" endpoint, when metadata was edited
    # in the same submit as captions/image — the workflow writes it via the
    # existing approve_metadata Activity instead of the API layer duplicating
    # that write. None when metadata wasn't touched by this revise (the
    # standalone "Revise captions"/"Replace background image" flows).
    metadata: VideoMetadataFields | None = None
