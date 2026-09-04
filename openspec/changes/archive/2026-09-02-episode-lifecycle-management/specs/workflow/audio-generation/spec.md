## ADDED Requirements

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
