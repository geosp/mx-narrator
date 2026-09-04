## MODIFIED Requirements

### Requirement: An approved episode is rendered into a video with soft subtitles
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
