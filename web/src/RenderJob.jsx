import { useState, useEffect } from "react";
import { API_BASE, styles, renderStatusBadge, ProgressBar, encodeMediaPath } from "./lib.js";

function ReplaceAudio({ renderJobId }) {
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("audio", file);
      const res = await fetch(`${API_BASE}/render_jobs/${renderJobId}/audio/replace`, {
        method: "POST",
        body: formData,
      });
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
    <form onSubmit={handleSubmit} style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #eee" }}>
      <div style={{ fontSize: 13, fontWeight: 500, color: "#444", marginBottom: 8 }}>
        Replace this audio (e.g. after adding music elsewhere) — the uploaded file becomes
        what's used for video production.
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} required />
        <button type="submit" style={{ ...styles.button, ...(submitting ? styles.buttonDisabled : {}) }} disabled={submitting}>
          {submitting ? "Uploading…" : "Upload and use this audio"}
        </button>
      </div>
      {error && <div style={styles.error}>{error}</div>}
    </form>
  );
}

function StartVideoProduction({ renderJobId }) {
  const [image, setImage] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleStart(e) {
    e.preventDefault();
    if (!image) return;
    setSubmitting(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("render_job_id", renderJobId);
      formData.append("image", image);
      const res = await fetch(`${API_BASE}/video_jobs`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      window.location.href = `${window.location.pathname}?video_job_id=${data.video_job_id}`;
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleStart} style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center" }}>
      <input type="file" accept="image/*" onChange={(e) => setImage(e.target.files[0])} required />
      <button type="submit" style={{ ...styles.button, ...(submitting ? styles.buttonDisabled : {}) }} disabled={submitting}>
        {submitting ? "Starting…" : "Start video production"}
      </button>
      {error && <div style={styles.error}>{error}</div>}
    </form>
  );
}

export default function RenderJob({ renderJobId }) {
  const [job, setJob] = useState(null);

  useEffect(() => {
    if (!renderJobId) return;
    const source = new EventSource(`${API_BASE}/render_jobs/${renderJobId}/events`);
    source.onmessage = (event) => setJob(JSON.parse(event.data));
    return () => source.close();
  }, [renderJobId]);

  // audio_url's path is identical across every replace (same render_job_id, same
  // "audio{ext}" name) — a browser has no natural signal to refetch after a second
  // replace without this. Same fix, same reason, as video_url in VideoReview.jsx.
  const audioUrl = job?.audio_url
    ? `${encodeMediaPath(job.audio_url)}?t=${encodeURIComponent(job.audio_replaced_at || "")}`
    : undefined;

  return (
    <div style={styles.page}>
      <a href="/" style={styles.breadcrumb}>&larr; Dashboard</a>
      <h1 style={styles.h1}>Render status</h1>
      <div style={styles.subtitle}>Tracking render job {renderJobId}.</div>

      <div style={styles.section}>
        <div style={styles.statusRow}>
          <span>render job {renderJobId}</span>
          <span style={renderStatusBadge(job?.status)}>{job?.status || "connecting"}</span>
        </div>
        {job?.status === "rendering" && job?.progress && (
          <ProgressBar current={job.progress.current} total={job.progress.total} />
        )}
        {audioUrl && (
          <audio style={{ width: "100%", marginTop: 16 }} controls src={`${API_BASE}${audioUrl}`} />
        )}
        {job?.audio_path && (
          <div style={{ fontSize: 13, color: "#444", marginTop: 8, wordBreak: "break-all" }}>{job.audio_path}</div>
        )}
        {job?.error && <div style={styles.error}>{job.error}</div>}
        {job?.status === "complete" && <StartVideoProduction renderJobId={renderJobId} />}
        {(job?.status === "complete" || job?.status === "failed") && <ReplaceAudio renderJobId={renderJobId} />}
        {job?.script_id && (
          <div style={{ marginTop: 16 }}>
            <a style={styles.link} href={`?edit_script_id=${job.script_id}`}>Edit script &amp; regenerate</a>
          </div>
        )}
      </div>
    </div>
  );
}
