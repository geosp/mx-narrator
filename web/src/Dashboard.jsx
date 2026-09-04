import { useState, useEffect } from "react";
import { API_BASE, styles, renderStatusBadge, videoStatusBadge, ProgressBar } from "./lib.js";

const REFRESH_INTERVAL_MS = 3000;

const localStyles = {
  newButton: {
    display: "inline-block",
    marginBottom: 24,
    ...styles.button,
    textDecoration: "none",
  },
  seriesHeading: { fontSize: 15, fontWeight: 700, margin: "28px 0 10px" },
  episodeRow: {
    background: "#fff",
    border: "1px solid #e2e2df",
    borderRadius: 8,
    padding: 16,
    marginBottom: 12,
  },
  episodeTop: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
  unitId: { fontWeight: 600, fontSize: 14 },
  meta: { fontSize: 12, color: "#888" },
  links: { display: "flex", gap: 14, marginTop: 10, fontSize: 13, alignItems: "center" },
  deleteLink: { color: "#b3261e", marginLeft: "auto", background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: 0, fontFamily: "inherit" },
  audio: { width: "100%", marginTop: 10 },
  empty: { color: "#888", fontSize: 14, marginTop: 24 },
};

const NO_SERIES = "￿No series"; // sorts after any real series name; unwrapped for display

function groupBySeries(episodes) {
  const groups = new Map();
  for (const ep of episodes) {
    const key = ep.series_name || NO_SERIES;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(ep);
  }
  for (const list of groups.values()) {
    list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  const entries = [...groups.entries()];
  entries.sort((a, b) => {
    const aLatest = new Date(a[1][0].created_at);
    const bLatest = new Date(b[1][0].created_at);
    return bLatest - aLatest;
  });
  return entries;
}

function timeAgo(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function EpisodeRow({ episode, onDelete }) {
  const { unit_id, lang, created_at, render_job, video_job } = episode;
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!window.confirm(`Delete "${unit_id}"? This removes the script, render, and video review, and cannot be undone.`)) {
      return;
    }
    setDeleting(true);
    try {
      await onDelete(episode.script_id);
    } catch (err) {
      setDeleting(false);
      window.alert(`Failed to delete: ${err.message}`);
    }
  }

  return (
    <div style={localStyles.episodeRow}>
      <div style={localStyles.episodeTop}>
        <span style={localStyles.unitId}>{unit_id}</span>
        <span style={localStyles.meta}>{lang}</span>
        <span style={localStyles.meta}>{timeAgo(created_at)}</span>
        {render_job && <span style={renderStatusBadge(render_job.status)}>{render_job.status}</span>}
        {video_job && <span style={videoStatusBadge(video_job.status)}>{video_job.status}</span>}
      </div>
      {render_job?.status === "rendering" && render_job.progress && (
        <ProgressBar current={render_job.progress.current} total={render_job.progress.total} />
      )}
      {render_job?.audio_url && (
        <audio style={localStyles.audio} controls src={`${API_BASE}${render_job.audio_url}`} />
      )}
      <div style={localStyles.links}>
        {render_job && (
          <a style={styles.link} href={`?render_job_id=${render_job.id}`}>
            View render
          </a>
        )}
        {video_job && (
          <a style={styles.link} href={`?video_job_id=${video_job.id}`}>
            Review video
          </a>
        )}
        <a style={styles.link} href={`?edit_script_id=${episode.script_id}`}>
          Edit &amp; regenerate
        </a>
        <button style={localStyles.deleteLink} onClick={handleDelete} disabled={deleting}>
          {deleting ? "Deleting…" : "Delete"}
        </button>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [episodes, setEpisodes] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    function refresh() {
      fetch(`${API_BASE}/dashboard`)
        .then((res) => res.json())
        .then((data) => {
          if (!cancelled) setEpisodes(data.episodes);
        })
        .catch((err) => {
          if (!cancelled) setError(err.message);
        });
    }

    refresh();
    // Plain polling, not SSE — the dashboard spans multiple collections (scripts,
    // render_jobs, video_jobs) rather than watching one document, and at this
    // scale (a personal tool, a handful of episodes at a time) a few requests
    // every few seconds is a non-issue.
    const interval = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  async function handleDelete(scriptId) {
    const res = await fetch(`${API_BASE}/scripts/${scriptId}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
    }
    setEpisodes((prev) => prev.filter((e) => e.script_id !== scriptId));
  }

  return (
    <div style={styles.page}>
      <h1 style={styles.h1}>Mx Narrator Studio</h1>
      <div style={styles.subtitle}>Scripts, renders, and video reviews, grouped by series.</div>

      <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 24 }}>
        <a href="?view=upload" style={{ ...localStyles.newButton, marginBottom: 0 }}>
          + New script
        </a>
        <a href="?view=voices" style={styles.link}>
          Manage voices
        </a>
      </div>

      {error && <div style={styles.error}>{error}</div>}
      {episodes === null && !error && <div style={localStyles.empty}>Loading…</div>}
      {episodes !== null && episodes.length === 0 && (
        <div style={localStyles.empty}>Nothing here yet — upload a script to get started.</div>
      )}

      {episodes &&
        groupBySeries(episodes).map(([seriesName, group]) => (
          <div key={seriesName}>
            <div style={localStyles.seriesHeading}>
              {seriesName === NO_SERIES ? "No series" : seriesName}
            </div>
            {group.map((ep) => (
              <EpisodeRow key={ep.script_id} episode={ep} onDelete={handleDelete} />
            ))}
          </div>
        ))}
    </div>
  );
}
