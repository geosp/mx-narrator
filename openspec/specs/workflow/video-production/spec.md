# workflow/video-production Specification

## Purpose
The first slice of `VideoProductionWorkflow` (RFC §7.2): transcribes a finished
episode's audio, checks the transcript against mx_narrator's own known TTS input text,
and requires human review of both any mismatches and the resulting SRT subtitle file
before the episode is considered ready for video rendering.

## Requirements

### Requirement: Audio is transcribed into a timestamped subtitle file
The system SHALL transcribe a render job's finished audio and produce an SRT subtitle
file with timing information.

#### Scenario: Successful transcription
- **WHEN** video production starts for a `render_jobs` document with a valid audio
  file
- **THEN** a `video_jobs` document is created and its `srt_path` points to a subtitle
  file containing the transcribed text with timestamps

### Requirement: Transcript is checked against the script's known text
The system SHALL compare the transcript against the exact text mx_narrator's synthesis
pipeline was given for that script, and record whether they match or where they
diverge.

#### Scenario: Transcript matches the known text
- **WHEN** the transcript's content matches the script's known text after
  transcription
- **THEN** `video_jobs.correctness_check.status` is `"pass"` and no mismatches are
  recorded

#### Scenario: Transcript diverges from the known text
- **WHEN** the transcript is missing or alters words present in the script's known
  text
- **THEN** `video_jobs.correctness_check.status` is `"mismatch"`, and each divergence
  is recorded with the expected text, the actual (transcribed) text, and an
  approximate timestamp

#### Scenario: Correctly narrated numbers are not falsely flagged
- **WHEN** the script's known text contains a number or scripture chapter:verse
  reference that was narrated and transcribed correctly
- **THEN** the correctness check does not report it as a mismatch, regardless of
  whether the number is written as digits or spelled out on either side of the
  comparison

#### Scenario: Accent-mark differences are not falsely flagged
- **WHEN** a word appears with an accent mark on one side of the comparison and
  without it (or with a different accent) on the other, but is otherwise the same
  word
- **THEN** the correctness check does not report it as a mismatch

#### Scenario: Known one-word/two-word Spanish spelling variants are not falsely flagged
- **WHEN** a Spanish word with two RAE-recognized spellings (one word or two, e.g.
  "adonde"/"a donde") is narrated correctly but rendered differently between the
  script and the transcript
- **THEN** the correctness check does not report it as a mismatch

### Requirement: A correctness-check mismatch requires human review before continuing
The system SHALL pause video production when a correctness-check mismatch is found,
and SHALL NOT continue until a human has reviewed and acknowledged it.

#### Scenario: Mismatch pauses the workflow
- **WHEN** a correctness-check mismatch is found for a `video_jobs` document
- **THEN** `video_jobs.status` becomes `"mismatch_needs_review"` and video production
  does not proceed further until acknowledged

#### Scenario: Acknowledgment resumes the workflow
- **WHEN** a human acknowledges a mismatch for a `video_jobs` document in
  `"mismatch_needs_review"` status
- **THEN** video production resumes and proceeds to SRT review

### Requirement: SRT review is always required, regardless of correctness-check outcome
The system SHALL require human review and approval of the subtitle file before this
slice of video production is considered complete, whether or not a correctness-check
mismatch occurred.

#### Scenario: Clean correctness check still requires SRT review
- **WHEN** a correctness check passes with no mismatches
- **THEN** `video_jobs.status` becomes `"srt_review_pending"` and a human must still
  approve the subtitle file before video production continues

#### Scenario: Approved subtitle text becomes the file of record
- **WHEN** a human approves subtitle text (edited or unedited) for a `video_jobs`
  document in `"srt_review_pending"` status
- **THEN** the approved text is written to `srt_path`, and `video_jobs.status`
  becomes `"srt_approved"`

#### Scenario: Malformed subtitle text is rejected before reaching the workflow
- **WHEN** a human submits subtitle text that isn't valid SRT format
- **THEN** the submission is rejected and `video_jobs.status` remains
  `"srt_review_pending"`

### Requirement: Video job status is visible in real time, not by polling
The system SHALL push `video_jobs` status changes to connected UI clients as they
happen, via a live update channel, rather than requiring the client to poll.

#### Scenario: Status changes while a client is connected
- **WHEN** a `video_jobs` document's `status` field changes while a UI client holds
  an open connection
- **THEN** the client receives the updated status without making a new request

### Requirement: An approved episode is rendered into a video with burned-in captions
Once its subtitle file is approved, the system SHALL produce a video file from the
episode's background image and finished audio, with the approved subtitles burned
directly into the video's picture so they are visible in any player without
further action. The system SHALL also mux the same subtitles as a selectable
(soft) subtitle track alongside the burned-in captions.

#### Scenario: Video produced after SRT approval
- **WHEN** a `video_jobs` document's SRT is approved
- **THEN** a video file is produced containing the background image with the
  approved captions burned into the picture, the episode's audio in full, and a
  selectable subtitle track matching the approved SRT, and `video_jobs.status`
  becomes `"rendering"` then advances once it completes

#### Scenario: Captions are visible without any viewer action
- **WHEN** a produced video is played in any standard video player, including a
  browser's native player
- **THEN** the captions are visible in the picture with no need to select or
  enable a subtitle track

### Requirement: YouTube metadata is generated and requires human approval
After rendering, the system SHALL generate a title, description, and tags for the
episode and SHALL require human review and approval — with the ability to edit any
field — before the episode is considered ready.

#### Scenario: Metadata generated and awaiting review
- **WHEN** video rendering completes for a `video_jobs` document
- **THEN** `video_jobs.status` becomes `"generating_metadata"`, generated
  title/description/tags are recorded, and status then becomes
  `"metadata_review_pending"`

#### Scenario: Human-edited metadata is what's recorded as approved
- **WHEN** a human edits and approves the generated title, description, or tags
- **THEN** the edited values (not the original generated ones) are recorded as the
  approved metadata, timestamped

### Requirement: Approval reaches a terminal ready-for-manual-upload state
Once metadata is approved, the system SHALL mark the episode
`"ready_for_manual_upload"` as a terminal state — the system SHALL NOT attempt any
upload to YouTube or any other platform.

#### Scenario: Workflow completes at the terminal state
- **WHEN** a human approves an episode's metadata
- **THEN** `video_jobs.status` becomes `"ready_for_manual_upload"` and the workflow
  takes no further automatic action

#### Scenario: Manual-upload tracking is separate bookkeeping
- **WHEN** a user marks an episode `"ready_for_manual_upload"` as manually
  uploaded
- **THEN** that tracking flag is recorded without any call to YouTube or any
  other external platform

### Requirement: Failures in rendering or metadata generation are recorded
The system SHALL record a failure state and an error message if video rendering
or metadata generation fails, rather than leaving the episode stuck in an
in-progress state. The system SHALL detect a lost worker during video rendering
promptly (via heartbeat), rather than only after the full activity timeout
elapses.

#### Scenario: Video rendering fails
- **WHEN** video rendering raises an error for a `video_jobs` document
- **THEN** `video_jobs.status` becomes `"failed"` and an error message is recorded

#### Scenario: The worker running video rendering is lost
- **WHEN** the worker process executing video rendering for a `video_jobs`
  document stops without completing (e.g. the container is restarted)
- **THEN** the loss is detected within the activity's heartbeat timeout, not only
  after its full start-to-close timeout

### Requirement: Approved captions can be revised, with the video re-rendered to match
Once captions have been approved at least once (the episode has reached
`metadata_review_pending`, `ready_for_manual_upload`, or `failed`), the system
SHALL allow submitting corrected caption text and SHALL re-render the video
against the correction. The system SHALL NOT re-run transcription or the
correctness check when revising — the human-submitted text is authoritative.
When metadata was already approved, the system SHALL NOT regenerate it; when it
was not yet approved, the system SHALL generate and require review of it again.

#### Scenario: Revising after full completion
- **WHEN** a video job at `ready_for_manual_upload` has its captions revised
- **THEN** the video is re-rendered with the corrected captions burned in, and
  the episode returns to `ready_for_manual_upload` without regenerating
  metadata

#### Scenario: Revising before metadata was ever approved
- **WHEN** a video job at `metadata_review_pending` (metadata not yet approved)
  has its captions revised
- **THEN** the video is re-rendered, metadata is generated again, and the
  episode returns to `metadata_review_pending` for review

#### Scenario: Revising doubles as a retry after a failure
- **WHEN** a video job at `failed` has its captions resubmitted (corrected or
  unchanged)
- **THEN** rendering is attempted again from that submission

#### Scenario: A stale manual-upload record is cleared on revision
- **WHEN** a video job that had already been marked manually uploaded has its
  captions revised
- **THEN** the manually-uploaded record is cleared, since the previously
  uploaded file no longer matches the corrected video

#### Scenario: Approval signals reach whichever execution is currently active
- **WHEN** a human approves metadata for a video job whose captions were
  revised (a new workflow execution, distinct from the one that ran
  originally)
- **THEN** the approval reaches that current execution, not the original one
