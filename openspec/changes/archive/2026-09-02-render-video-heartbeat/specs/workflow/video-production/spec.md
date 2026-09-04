## MODIFIED Requirements

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
