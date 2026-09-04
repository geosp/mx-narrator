## Purpose

The first slice of `VideoProductionWorkflow` (RFC §7.2): transcribes a finished
episode's audio, checks the transcript against narrator's own known TTS input text,
and requires human review of both any mismatches and the resulting SRT subtitle file
before the episode is considered ready for video rendering.

## ADDED Requirements

### Requirement: Audio is transcribed into a timestamped subtitle file
The system SHALL transcribe a render job's finished audio and produce an SRT subtitle
file with timing information.

#### Scenario: Successful transcription
- **WHEN** video production starts for a `render_jobs` document with a valid audio
  file
- **THEN** a `video_jobs` document is created and its `srt_path` points to a subtitle
  file containing the transcribed text with timestamps

### Requirement: Transcript is checked against the script's known text
The system SHALL compare the transcript against the exact text narrator's synthesis
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
