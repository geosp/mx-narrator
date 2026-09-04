## ADDED Requirements

### Requirement: An approved episode is rendered into a video with soft subtitles
Once its subtitle file is approved, the system SHALL produce a video file from the
episode's background image and finished audio, with the approved subtitles muxed
in as a selectable (soft) subtitle track rather than burned into the image.

#### Scenario: Video produced after SRT approval
- **WHEN** a `video_jobs` document's SRT is approved
- **THEN** a video file is produced containing the background image, the episode's
  audio in full, and a selectable subtitle track matching the approved SRT, and
  `video_jobs.status` becomes `"rendering"` then advances once it completes

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
in-progress state.

#### Scenario: Video rendering fails
- **WHEN** video rendering raises an error for a `video_jobs` document
- **THEN** `video_jobs.status` becomes `"failed"` and an error message is recorded
