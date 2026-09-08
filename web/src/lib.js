import { createElement } from "react";

// Computed at runtime from wherever the browser actually loaded this page from —
// not baked in at build time. `api` and `web` are published on the same Docker host
// under different ports, so whatever hostname/IP got you here is also the right host
// for the API. A build-time VITE_API_BASE still wins if explicitly set (e.g. for a
// reverse-proxy topology where that assumption doesn't hold).
export const API_BASE =
  import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;

// A stored media path (audio_url/video_url) can contain characters that are
// unsafe left raw in a URL — a literal "?" in particular gets parsed by the
// browser as the query-string delimiter, silently truncating the path before
// the request is even sent. Plain encodeURI() doesn't fix this — it
// deliberately leaves "? # & = + : @ , ; $" unescaped, assuming they're
// already meaningful URI syntax. Encoding each path segment individually
// (and rejoining with "/") is what actually escapes those characters while
// keeping "/" as the path separator the backend's /media mount expects.
export function encodeMediaPath(path) {
  return path ? path.split("/").map(encodeURIComponent).join("/") : path;
}

export const styles = {
  page: { maxWidth: 720, margin: "0 auto", padding: "32px 20px 80px" },
  h1: { fontSize: 24, marginBottom: 4 },
  subtitle: { color: "#666", marginBottom: 32 },
  section: {
    background: "#fff",
    border: "1px solid #e2e2df",
    borderRadius: 8,
    padding: 24,
    marginBottom: 24,
  },
  sectionTitle: { fontSize: 16, fontWeight: 600, marginBottom: 16 },
  statusRow: { display: "flex", alignItems: "center", gap: 10 },
  button: {
    padding: "10px 20px",
    background: "#2a2a2a",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: 14,
    cursor: "pointer",
  },
  buttonDisabled: { opacity: 0.5, cursor: "not-allowed" },
  error: { color: "#b3261e", fontSize: 13, marginTop: 8 },
  breadcrumb: { display: "inline-block", marginBottom: 16, color: "#555", fontSize: 13, textDecoration: "none" },
  link: { color: "#2a2a2a", fontSize: 13, textDecoration: "none" },
};

export function badgeStyle(background) {
  return {
    display: "inline-block",
    padding: "3px 10px",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 600,
    textTransform: "uppercase",
    color: "#fff",
    background,
  };
}

const RENDER_STATUS_COLOR = {
  complete: "#2e7d32",
  failed: "#b3261e",
  rendering: "#c77700",
};

export function renderStatusBadge(status) {
  return badgeStyle(RENDER_STATUS_COLOR[status] || "#666");
}

const VIDEO_STATUS_COLOR = {
  ready_for_manual_upload: "#2e7d32",
  srt_approved: "#2e7d32",
  failed: "#b3261e",
  mismatch_needs_review: "#b3261e",
  srt_review_pending: "#c77700",
  checking_correctness: "#c77700",
  transcribing: "#c77700",
  rendering: "#c77700",
  generating_metadata: "#c77700",
  metadata_review_pending: "#c77700",
};

export function videoStatusBadge(status) {
  return badgeStyle(VIDEO_STATUS_COLOR[status] || "#666");
}

const progressBarStyles = {
  wrap: { marginTop: 8 },
  label: { fontSize: 12, color: "#666", marginBottom: 4 },
  track: { background: "#eee", borderRadius: 999, height: 6, overflow: "hidden" },
  fill: { background: "#c77700", height: "100%", borderRadius: 999, transition: "width 0.4s ease" },
};

// {current, total} chunk progress, rendered as a label + a filled bar. Shared by
// Dashboard.jsx (per-episode row) and RenderJob.jsx (render detail page). Plain
// createElement, not JSX — this file isn't run through the JSX transform.
export function ProgressBar({ current, total }) {
  if (!total) return null;
  const pct = Math.min(100, Math.round((current / total) * 100));
  return createElement(
    "div",
    { style: progressBarStyles.wrap },
    createElement("div", { style: progressBarStyles.label }, `Chunk ${current} of ${total}`),
    createElement(
      "div",
      { style: progressBarStyles.track },
      createElement("div", { style: { ...progressBarStyles.fill, width: `${pct}%` } })
    )
  );
}
