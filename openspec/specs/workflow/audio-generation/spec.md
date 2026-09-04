# workflow/audio-generation Specification

## Purpose
The Temporal workflow that turns a persisted script into a finished, ID3-tagged MP3
by calling mx_narrator's existing synthesis pipeline — the first phase of Mx Narrator
Studio's pipeline to run real application logic, not just infrastructure (RFC §7.1).

## Requirements

### Requirement: Workflow produces a correctly-tagged MP3 on success
The workflow SHALL call mx_narrator's synthesis pipeline with the render job's
parameters and, on success, record the resulting MP3's path and mark the render job
complete.

#### Scenario: Successful synthesis
- **WHEN** `AudioGenerationWorkflow` runs for a `render_jobs` document with valid
  script text and render parameters
- **THEN** `render_jobs.status` becomes `"complete"` and `render_jobs.audio_path`
  points to an MP3 file tagged with the submitted `id3` fields

### Requirement: Synthesis failures are recorded, not silently lost
The workflow SHALL record a failure state and an error message on the render job
rather than leaving it stuck in an in-progress state when synthesis fails.

#### Scenario: Synthesis raises an error
- **WHEN** mx_narrator's synthesis pipeline raises an error while `AudioGenerationWorkflow`
  is running (e.g. an unsupported engine name)
- **THEN** `render_jobs.status` becomes `"failed"` and an error message is recorded on
  the document

### Requirement: Workflow execution is durable and independently observable
The workflow's execution history and current state SHALL be visible through Temporal's
own Web UI, independent of the application's own database records.

#### Scenario: Operator inspects a run in Temporal's Web UI
- **WHEN** an operator opens Temporal's Web UI for a running or completed
  `AudioGenerationWorkflow` execution
- **THEN** its current state and full event history are visible there, matching what
  `render_jobs` in MongoDB reports

### Requirement: Render progress is visible incrementally during synthesis
The workflow SHALL record how many of a script's synthesis chunks have completed
while a render job is in progress, not only its final status.

#### Scenario: Multi-chunk script partway through rendering
- **WHEN** a render job's script has been split into multiple synthesis chunks and
  some but not all have finished synthesizing
- **THEN** the render job's current and total chunk counts are recorded and visible
  to a connected client before the render completes

### Requirement: A completed render job includes a playback URL
The workflow SHALL record a URL for a completed render job's audio file, so clients
can offer playback without separately computing it from the file's on-disk path.

#### Scenario: Render completes successfully
- **WHEN** a render job's synthesis completes successfully
- **THEN** the render job's playback URL is recorded alongside its `"complete"`
  status

### Requirement: A selected voice is resolved and applied during synthesis
When a render job specifies a voice, the workflow SHALL resolve that voice's
reference sample for the render job's language (falling back to the voice's
language-independent sample if no language-specific one exists) and use it for
synthesis, without requiring any change to mx_narrator's own synthesis pipeline.

#### Scenario: Language-specific sample available
- **WHEN** a render job specifies a voice that has a sample for the render job's
  language
- **THEN** synthesis uses that language-specific sample

#### Scenario: Falls back to the voice's default sample
- **WHEN** a render job specifies a voice that has no sample for the render job's
  language but does have a language-independent fallback sample
- **THEN** synthesis uses the fallback sample

#### Scenario: No voice specified
- **WHEN** a render job specifies no voice
- **THEN** synthesis uses the engine's built-in default voice, unchanged from
  behavior before voice selection existed
