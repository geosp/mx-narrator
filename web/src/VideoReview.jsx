import { useState, useEffect, useRef } from "react";
import { API_BASE, styles, videoStatusBadge } from "./lib.js";
import { parseSrt, serializeSrt } from "./srt.js";

const localStyles = {
  textarea: {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    border: "1px solid #d0d0cd",
    borderRadius: 6,
    fontSize: 13,
    fontFamily: "monospace",
    minHeight: 240,
    resize: "vertical",
  },
  mismatchRow: {
    display: "flex",
    gap: 12,
    padding: "8px 0",
    borderBottom: "1px solid #eee",
    fontSize: 13,
  },
  audio: { width: "100%", marginBottom: 16 },
  video: { width: "100%", marginBottom: 16, borderRadius: 6 },
  captionRow: {
    display: "flex",
    gap: 10,
    alignItems: "flex-start",
    padding: "6px 8px",
    borderRadius: 6,
    marginBottom: 4,
  },
  captionRowActive: { background: "#fff4e5" },
  captionRowMismatch: { borderLeft: "3px solid #c0392b", background: "#fdeeee" },
  mismatchNote: { fontSize: 12, color: "#c0392b", marginTop: 4 },
  tabRow: { display: "flex", gap: 4, borderBottom: "1px solid #e2e2df", marginBottom: 16 },
  tabButton: {
    padding: "8px 16px",
    background: "none",
    border: "none",
    borderBottom: "2px solid transparent",
    fontSize: 14,
    color: "#666",
    cursor: "pointer",
    marginBottom: -1,
  },
  tabButtonActive: { color: "#2a2a2a", borderBottomColor: "#2a2a2a", fontWeight: 600 },
  timestampButton: {
    flexShrink: 0,
    width: 56,
    marginTop: 6,
    padding: "2px 0",
    background: "none",
    border: "none",
    color: "#2a2a2a",
    fontFamily: "monospace",
    fontSize: 12,
    cursor: "pointer",
    textDecoration: "underline",
  },
  captionText: {
    flex: 1,
    width: "100%",
    boxSizing: "border-box",
    padding: "6px 8px",
    border: "1px solid #d0d0cd",
    borderRadius: 6,
    fontSize: 13,
    fontFamily: "inherit",
    resize: "vertical",
    minHeight: 32,
  },
  captionList: { maxHeight: 420, overflowY: "auto", border: "1px solid #eee", borderRadius: 6, padding: 8 },
  field: { display: "flex", flexDirection: "column", gap: 4, marginBottom: 16 },
  label: { fontSize: 13, color: "#444", fontWeight: 500 },
  input: { padding: "8px 10px", border: "1px solid #d0d0cd", borderRadius: 6, fontSize: 14 },
  tagsHint: { fontSize: 12, color: "#888", marginTop: 4 },
  readOnlyBlock: {
    background: "#f7f7f5",
    border: "1px solid #e2e2df",
    borderRadius: 6,
    padding: "10px 12px",
    fontSize: 13,
    whiteSpace: "pre-wrap",
    marginBottom: 12,
  },
  checkboxRow: { display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 14 },
  busy: { color: "#666", fontSize: 14 },
};

function useVideoJobEvents(videoJobId) {
  const [job, setJob] = useState(null);

  useEffect(() => {
    if (!videoJobId) return;
    const source = new EventSource(`${API_BASE}/video_jobs/${videoJobId}/events`);
    source.onmessage = (event) => setJob(JSON.parse(event.data));
    return () => source.close();
  }, [videoJobId]);

  return job;
}

function MismatchReview({ videoJobId, job }) {
  const [submitting, setSubmitting] = useState(false);

  async function handleAcknowledge() {
    setSubmitting(true);
    await fetch(`${API_BASE}/video_jobs/${videoJobId}/mismatch/acknowledge`, { method: "POST" });
    setSubmitting(false);
  }

  const mismatches = job?.correctness_check?.mismatches || [];

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Correctness check mismatches</div>
      <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>
        These are flagged automatically — the caption editor on the next screen highlights the
        matching captions so you don't have to remember the timestamps.
      </div>
      {mismatches.map((m, i) => (
        <div key={i} style={localStyles.mismatchRow}>
          <span>~{m.approx_time?.toFixed(1)}s</span>
          <span>expected: "{m.expected}"</span>
          <span>actual: "{m.actual}"</span>
        </div>
      ))}
      <button
        style={{ ...styles.button, marginTop: 16, ...(submitting ? styles.buttonDisabled : {}) }}
        onClick={handleAcknowledge}
        disabled={submitting}
      >
        {submitting ? "Acknowledging…" : "Acknowledge and continue"}
      </button>
    </div>
  );
}

function formatClock(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  return `${mm}:${String(ss).padStart(2, "0")}`;
}

// A mismatch's approx_time is a transcribed word's own timestamp, which can drift
// slightly from an SRT entry's [start, end] after align_captions re-times entries
// (worker/align.py) — a generous tolerance keeps the flag attached to the right
// caption without needing exact boundary precision.
const MISMATCH_TIME_TOLERANCE = 1.5;

function mismatchesForEntry(entry, mismatches) {
  return mismatches.filter(
    (m) => m.approx_time >= entry.start - MISMATCH_TIME_TOLERANCE && m.approx_time <= entry.end + MISMATCH_TIME_TOLERANCE
  );
}

// Presentational: the audio player + editable caption row list, with mismatch
// highlighting. No fetch, no submit button of its own — the parent owns
// `entries` state and decides what "save" means (a lone SrtReview posts just
// the SRT; MetadataReview's unified save posts this alongside metadata/image).
function CaptionEditor({ entries, onEntryChange, mismatches = [], audioUrl }) {
  const [activeIndex, setActiveIndex] = useState(-1);
  const audioRef = useRef(null);
  const rowRefs = useRef([]);

  useEffect(() => {
    // Only scroll when the active caption actually changes, not on every
    // timeupdate tick — otherwise it'd fight in-progress reading/editing.
    rowRefs.current[activeIndex]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIndex]);

  function updateActiveIndex() {
    // `timeupdate` alone isn't reliably fired after a programmatic seek while
    // paused (browser-dependent) — also bound to `seeked` so clicking a
    // timestamp highlights the row immediately, not just during playback.
    const t = audioRef.current?.currentTime;
    if (t === undefined || !entries) return;
    // A small tolerance: seeking to e.start can land a hair below it (browser
    // seek precision snaps to the nearest decodable sample, not the exact
    // requested time), which would otherwise fail `t >= e.start` right after
    // clicking that very row's own timestamp.
    const EPSILON = 0.05;
    const idx = entries.findIndex((e) => t >= e.start - EPSILON && t < e.end + EPSILON);
    setActiveIndex((prev) => (prev === idx ? prev : idx));
  }

  function seekTo(seconds) {
    if (audioRef.current) audioRef.current.currentTime = seconds;
  }

  return (
    <>
      {audioUrl && (
        <audio
          ref={audioRef}
          style={localStyles.audio}
          controls
          src={`${API_BASE}${audioUrl}`}
          onTimeUpdate={updateActiveIndex}
          onSeeked={updateActiveIndex}
        />
      )}
      {entries ? (
        <div style={localStyles.captionList}>
          {entries.map((e, i) => {
            const rowMismatches = mismatchesForEntry(e, mismatches);
            return (
              <div
                key={i}
                ref={(el) => (rowRefs.current[i] = el)}
                style={{
                  ...localStyles.captionRow,
                  ...(rowMismatches.length ? localStyles.captionRowMismatch : {}),
                  ...(i === activeIndex ? localStyles.captionRowActive : {}),
                }}
              >
                <button type="button" style={localStyles.timestampButton} onClick={() => seekTo(e.start)}>
                  {formatClock(e.start)}
                </button>
                <div style={{ flex: 1 }}>
                  <textarea
                    style={localStyles.captionText}
                    value={e.text}
                    onChange={(ev) => onEntryChange(i, ev.target.value)}
                  />
                  {rowMismatches.map((m, mi) => (
                    <div key={mi} style={localStyles.mismatchNote}>
                      ⚠ expected "{m.expected}" — heard "{m.actual}"
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div>Loading…</div>
      )}
    </>
  );
}

function SrtReview({ videoJobId, audioUrl, mismatches = [], endpoint = "srt/approve", submitLabel = "Approve" }) {
  const [entries, setEntries] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/video_jobs/${videoJobId}/srt`)
      .then((res) => res.json())
      .then((data) => setEntries(parseSrt(data.srt_text || "")));
  }, [videoJobId]);

  function setEntryText(i, text) {
    setEntries((prev) => prev.map((e, idx) => (idx === i ? { ...e, text } : e)));
  }

  async function handleApprove() {
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/video_jobs/${videoJobId}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ srt_text: serializeSrt(entries) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>SRT review</div>
      <CaptionEditor entries={entries} onEntryChange={setEntryText} mismatches={mismatches} audioUrl={audioUrl} />
      <button
        style={{ ...styles.button, marginTop: 16, ...(submitting ? styles.buttonDisabled : {}) }}
        onClick={handleApprove}
        disabled={submitting || !entries}
      >
        {submitting ? "Saving…" : submitLabel}
      </button>
      {error && <div style={styles.error}>{error}</div>}
    </div>
  );
}

function ImageReviseForm({ videoJobId }) {
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!file) return;
    setSubmitting(true);
    setError("");
    try {
      const body = new FormData();
      body.append("image", file);
      const res = await fetch(`${API_BASE}/video_jobs/${videoJobId}/image/revise`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      setFile(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files[0])} />
      <button
        style={{ ...styles.button, marginTop: 8, ...(submitting || !file ? styles.buttonDisabled : {}) }}
        onClick={handleSubmit}
        disabled={submitting || !file}
      >
        {submitting ? "Uploading…" : "Save and re-render video"}
      </button>
      {error && <div style={styles.error}>{error}</div>}
    </div>
  );
}

// Revising after the first "Final review" save — no live workflow left to
// signal for a cheap combined save (that status has already closed), so
// captions and background image stay separate re-render actions here. Tabs
// instead of collapsed links: both the caption editor and the video above
// stay visible without an extra click to reveal them.
function ReviseTabs({ videoJobId, audioUrl, mismatches = [] }) {
  const [tab, setTab] = useState("captions");

  return (
    <div style={{ marginTop: 16 }}>
      <div style={localStyles.tabRow}>
        <button
          type="button"
          style={{ ...localStyles.tabButton, ...(tab === "captions" ? localStyles.tabButtonActive : {}) }}
          onClick={() => setTab("captions")}
        >
          Captions
        </button>
        <button
          type="button"
          style={{ ...localStyles.tabButton, ...(tab === "image" ? localStyles.tabButtonActive : {}) }}
          onClick={() => setTab("image")}
        >
          Background image
        </button>
      </div>
      {tab === "captions" ? (
        <SrtReview
          videoJobId={videoJobId}
          audioUrl={audioUrl}
          mismatches={mismatches}
          endpoint="srt/revise"
          submitLabel="Save and re-render video"
        />
      ) : (
        <ImageReviseForm videoJobId={videoJobId} />
      )}
    </div>
  );
}

function BusyStep({ status }) {
  const label = status === "rendering" ? "Rendering video…" : "Generating metadata…";
  return (
    <div style={styles.section}>
      <div style={localStyles.busy}>{label} this page will update automatically.</div>
    </div>
  );
}

// The first-time review screen (video_jobs status metadata_review_pending):
// captions, background image, and metadata are all editable together here,
// saved in one call to /revise-all. Later revisions (ReadyForUpload/failed,
// after this screen's Save has already run once) keep the separate
// ReviseTabs flow below — those statuses have no live workflow left to
// signal for a cheap metadata-only save.
function MetadataReview({ videoJobId, videoUrl, audioUrl, mismatches = [] }) {
  const [entries, setEntries] = useState(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [imageFile, setImageFile] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/video_jobs/${videoJobId}/srt`).then((res) => res.json()),
      fetch(`${API_BASE}/video_jobs/${videoJobId}/metadata`).then((res) => res.json()),
    ]).then(([srtData, metaData]) => {
      setEntries(parseSrt(srtData.srt_text || ""));
      setTitle(metaData.title || "");
      setDescription(metaData.description || "");
      setTagsText((metaData.tags || []).join(", "));
      setLoaded(true);
    });
  }, [videoJobId]);

  function setEntryText(i, text) {
    setEntries((prev) => prev.map((e, idx) => (idx === i ? { ...e, text } : e)));
  }

  async function handleSave() {
    setSubmitting(true);
    setError("");
    try {
      const body = new FormData();
      body.append("srt_text", serializeSrt(entries));
      body.append("title", title);
      body.append("description", description);
      body.append("tags", tagsText);
      if (imageFile) body.append("image", imageFile);
      const res = await fetch(`${API_BASE}/video_jobs/${videoJobId}/revise-all`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      setImageFile(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Final review</div>
      {videoUrl && <video style={localStyles.video} controls src={`${API_BASE}${videoUrl}`} />}
      {loaded ? (
        <>
          <div style={localStyles.field}>
            <label style={localStyles.label} htmlFor="metadata-title">Title</label>
            <input id="metadata-title" style={localStyles.input} value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div style={localStyles.field}>
            <label style={localStyles.label} htmlFor="metadata-description">Description</label>
            <textarea
              id="metadata-description"
              style={localStyles.textarea}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div style={localStyles.field}>
            <label style={localStyles.label} htmlFor="metadata-tags">Tags</label>
            <input id="metadata-tags" style={localStyles.input} value={tagsText} onChange={(e) => setTagsText(e.target.value)} />
            <div style={localStyles.tagsHint}>Comma-separated</div>
          </div>
          <div style={localStyles.field}>
            <label style={localStyles.label} htmlFor="metadata-image">Background image</label>
            <input id="metadata-image" type="file" accept="image/*" onChange={(e) => setImageFile(e.target.files[0])} />
            <div style={localStyles.tagsHint}>Leave empty to keep the current image</div>
          </div>
          <div style={localStyles.field}>
            <label style={localStyles.label}>Captions</label>
            <CaptionEditor entries={entries} onEntryChange={setEntryText} mismatches={mismatches} audioUrl={audioUrl} />
          </div>
        </>
      ) : (
        <div>Loading…</div>
      )}
      <button
        style={{ ...styles.button, ...(submitting || !loaded ? styles.buttonDisabled : {}) }}
        onClick={handleSave}
        disabled={submitting || !loaded}
      >
        {submitting ? "Saving…" : "Save"}
      </button>
      {error && <div style={styles.error}>{error}</div>}
    </div>
  );
}

function ReadyForUpload({ videoJobId, videoUrl, audioUrl, mismatches = [] }) {
  const [metadata, setMetadata] = useState(null);
  const [marking, setMarking] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/video_jobs/${videoJobId}/metadata`)
      .then((res) => res.json())
      .then(setMetadata);
  }, [videoJobId]);

  async function handleMarkUploaded() {
    setMarking(true);
    try {
      await fetch(`${API_BASE}/video_jobs/${videoJobId}/manually_uploaded`, { method: "POST" });
      setMetadata((prev) => (prev ? { ...prev, manually_uploaded: true } : prev));
    } finally {
      setMarking(false);
    }
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Ready for manual upload</div>
      {videoUrl && <video style={localStyles.video} controls src={`${API_BASE}${videoUrl}`} />}
      {metadata && (
        <>
          <div style={localStyles.readOnlyBlock}>{metadata.title}</div>
          <div style={localStyles.readOnlyBlock}>{metadata.description}</div>
          <div style={localStyles.readOnlyBlock}>{metadata.tags.join(", ")}</div>
        </>
      )}
      <label style={localStyles.checkboxRow}>
        <input
          type="checkbox"
          checked={metadata?.manually_uploaded || false}
          disabled={marking || metadata?.manually_uploaded}
          onChange={handleMarkUploaded}
        />
        Marked as manually uploaded to YouTube
      </label>
      <ReviseTabs videoJobId={videoJobId} audioUrl={audioUrl} mismatches={mismatches} />
    </div>
  );
}

export default function VideoReview({ videoJobId }) {
  const job = useVideoJobEvents(videoJobId);
  // video_url's path is identical across every re-render (worker/activities.py's
  // mark_video_job comment) — a browser has no natural signal to refetch after a
  // revise without this. Confirmed the hard way: a real revise re-rendered
  // correctly, but the page kept showing the old video.
  const videoUrl = job?.video_url
    ? `${job.video_url}?t=${encodeURIComponent(job.video_rendered_at || "")}`
    : undefined;

  return (
    <div style={styles.page}>
      <a href="/" style={styles.breadcrumb}>&larr; Dashboard</a>
      <h1 style={styles.h1}>Video review</h1>
      <div style={styles.subtitle}>Review the transcript check and approve captions.</div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>Status</div>
        <div style={styles.statusRow}>
          <span>video job {videoJobId}</span>
          <span style={videoStatusBadge(job?.status)}>{job?.status || "connecting"}</span>
        </div>
      </div>

      {job?.status === "mismatch_needs_review" && <MismatchReview videoJobId={videoJobId} job={job} />}
      {job?.status === "srt_review_pending" && (
        <SrtReview
          videoJobId={videoJobId}
          audioUrl={job?.audio_url}
          mismatches={job?.correctness_check?.mismatches || []}
        />
      )}
      {(job?.status === "rendering" || job?.status === "generating_metadata") && (
        <BusyStep status={job.status} />
      )}
      {job?.status === "metadata_review_pending" && (
        <MetadataReview
          videoJobId={videoJobId}
          videoUrl={videoUrl}
          audioUrl={job?.audio_url}
          mismatches={job?.correctness_check?.mismatches || []}
        />
      )}
      {job?.status === "ready_for_manual_upload" && (
        <ReadyForUpload
          videoJobId={videoJobId}
          videoUrl={videoUrl}
          audioUrl={job?.audio_url}
          mismatches={job?.correctness_check?.mismatches || []}
        />
      )}
      {job?.status === "failed" && (
        <div style={styles.section}>
          {job?.error && <div style={styles.error}>{job.error}</div>}
          {job?.srt_path && (
            <ReviseTabs
              videoJobId={videoJobId}
              audioUrl={job?.audio_url}
              mismatches={job?.correctness_check?.mismatches || []}
            />
          )}
        </div>
      )}
    </div>
  );
}
