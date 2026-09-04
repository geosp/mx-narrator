## Purpose

The Temporal workflow that turns a persisted script into a finished, ID3-tagged MP3
by calling narrator's existing synthesis pipeline — the first phase of Narrator
Studio's pipeline to run real application logic, not just infrastructure (RFC §7.1).

## ADDED Requirements

### Requirement: Workflow produces a correctly-tagged MP3 on success
The workflow SHALL call narrator's synthesis pipeline with the render job's
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
- **WHEN** narrator's synthesis pipeline raises an error while `AudioGenerationWorkflow`
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
