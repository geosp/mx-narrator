import { useState, useEffect } from "react";
import { API_BASE, styles } from "./lib.js";

const NEW_SERIES = "__new_series__";

export const LANGS = [
  { value: "es", label: "Español" },
  { value: "en", label: "English" },
  { value: "pt", label: "Português" },
];

const formStyles = {
  row: { display: "flex", gap: 16, marginBottom: 16 },
  field: { flex: 1, display: "flex", flexDirection: "column", gap: 4 },
  label: { fontSize: 13, color: "#444", fontWeight: 500 },
  input: {
    padding: "8px 10px",
    border: "1px solid #d0d0cd",
    borderRadius: 6,
    fontSize: 14,
  },
  textarea: {
    padding: "8px 10px",
    border: "1px solid #d0d0cd",
    borderRadius: 6,
    fontSize: 14,
    minHeight: 120,
    fontFamily: "inherit",
    resize: "vertical",
  },
  hint: { fontSize: 12, color: "#888", marginTop: 4 },
};

export function Id3Fields({ id3, onChange }) {
  const set = (key) => (e) => onChange({ ...id3, [key]: e.target.value });
  return (
    <>
      <div style={formStyles.row}>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-artist">Artist</label>
          <input id="id3-artist" style={formStyles.input} value={id3.artist} onChange={set("artist")} required />
        </div>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-title">Track Title</label>
          <input id="id3-title" style={formStyles.input} value={id3.title} onChange={set("title")} required />
        </div>
      </div>
      <div style={formStyles.row}>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-album">Album Title</label>
          <input id="id3-album" style={formStyles.input} value={id3.album} onChange={set("album")} required />
        </div>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-track">Track Number</label>
          <input id="id3-track" style={formStyles.input} type="number" min="1" value={id3.track} onChange={set("track")} />
        </div>
      </div>
      <div style={formStyles.row}>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-year">Year</label>
          <input id="id3-year" style={formStyles.input} value={id3.year} onChange={set("year")} />
        </div>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-genre">Genre</label>
          <input id="id3-genre" style={formStyles.input} value={id3.genre} onChange={set("genre")} />
        </div>
      </div>
      <div style={formStyles.row}>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="id3-comments">Comments</label>
          <input id="id3-comments" style={formStyles.input} value={id3.comments} onChange={set("comments")} />
        </div>
      </div>
    </>
  );
}

export const initialForm = {
  unit_id: "",
  lang: "es",
  series_name: "",
  script_text: "",
  engine_name: "chatterbox",
  speed: 0.95,
  exaggeration: 0.6,
  cfg_weight: 0.4,
  seed: 0,
  series_album: "",
  title: "",
  voice_id: "",
  id3: {
    artist: "",
    title: "",
    album: "",
    track: 1,
    year: "",
    genre: "",
    comments: "",
  },
};

// Coerces the string-valued form fields (numbers come out of <input> as strings)
// into the shape ScriptIn (api/main.py) expects. Shared by App.jsx (POST /scripts)
// and EditScript.jsx (PUT /scripts/{id}/regenerate) — same body shape either way.
export function toScriptInBody(form) {
  return {
    ...form,
    speed: Number(form.speed),
    exaggeration: Number(form.exaggeration),
    cfg_weight: Number(form.cfg_weight),
    seed: Number(form.seed),
    title: form.title || null,
    voice_id: form.voice_id || null,
    id3: { ...form.id3, track: Number(form.id3.track) },
  };
}

export default function ScriptForm({ initialValues, onSubmit, submitLabel, submitting, error, warning }) {
  const [form, setForm] = useState(initialValues);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const [seriesOptions, setSeriesOptions] = useState([]);
  const [seriesChoice, setSeriesChoice] = useState(initialValues.series_name || "");
  const [newSeriesName, setNewSeriesName] = useState("");
  const [voiceOptions, setVoiceOptions] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/series`)
      .then((res) => res.json())
      .then((data) => setSeriesOptions(data.series || []))
      .catch(() => {});
    fetch(`${API_BASE}/voices`)
      .then((res) => res.json())
      .then((data) => setVoiceOptions(data.voices || []))
      .catch(() => {});
  }, []);

  // The form's own current series (e.g. when editing an existing episode) might not
  // be in the fetched list yet on first render — show it anyway rather than having
  // the dropdown briefly look like it reset to "(No series)".
  const visibleSeriesOptions =
    seriesChoice && seriesChoice !== NEW_SERIES && !seriesOptions.includes(seriesChoice)
      ? [seriesChoice, ...seriesOptions]
      : seriesOptions;

  function handleSeriesSelect(e) {
    const value = e.target.value;
    setSeriesChoice(value);
    setForm({ ...form, series_name: value === NEW_SERIES ? newSeriesName : value });
  }

  function handleNewSeriesNameChange(e) {
    setNewSeriesName(e.target.value);
    setForm({ ...form, series_name: e.target.value });
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit(form);
  }

  return (
    <form onSubmit={handleSubmit}>
      {warning}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>Script</div>
        <div style={formStyles.row}>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="unit-id">Unit ID</label>
            <input id="unit-id" style={formStyles.input} value={form.unit_id} onChange={set("unit_id")} required />
          </div>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="lang">Language</label>
            <select id="lang" style={formStyles.input} value={form.lang} onChange={set("lang")}>
              {LANGS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={formStyles.row}>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="voice-select">Voice</label>
            <select id="voice-select" style={formStyles.input} value={form.voice_id || ""} onChange={set("voice_id")}>
              <option value="">(Engine default)</option>
              {voiceOptions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ ...formStyles.field, justifyContent: "flex-end" }}>
            <a href="?view=voices" style={styles.link}>
              Manage voices
            </a>
          </div>
        </div>
        <div style={formStyles.row}>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="series-select">Series</label>
            <select id="series-select" style={formStyles.input} value={seriesChoice} onChange={handleSeriesSelect}>
              <option value="">(No series)</option>
              {visibleSeriesOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
              <option value={NEW_SERIES}>+ New series…</option>
            </select>
          </div>
          {seriesChoice === NEW_SERIES && (
            <div style={formStyles.field}>
              <label style={formStyles.label} htmlFor="series-new-name">New series name</label>
              <input
                id="series-new-name"
                style={formStyles.input}
                value={newSeriesName}
                onChange={handleNewSeriesNameChange}
                placeholder="e.g. 1 John"
                required
              />
            </div>
          )}
        </div>
        <div style={formStyles.field}>
          <label style={formStyles.label} htmlFor="script-text">Script text</label>
          <textarea id="script-text" style={formStyles.textarea} value={form.script_text} onChange={set("script_text")} required />
        </div>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>Voice settings</div>
        <div style={formStyles.row}>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="speed">Speed</label>
            <input
              id="speed"
              style={formStyles.input}
              type="number"
              min="0.5"
              max="2"
              step="0.05"
              value={form.speed}
              onChange={set("speed")}
            />
            <div style={formStyles.hint}>Playback speed multiplier.</div>
          </div>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="exaggeration">Expressiveness</label>
            <input
              id="exaggeration"
              style={formStyles.input}
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={form.exaggeration}
              onChange={set("exaggeration")}
            />
            <div style={formStyles.hint}>Chatterbox "exaggeration" — low for devotional material.</div>
          </div>
          <div style={formStyles.field}>
            <label style={formStyles.label} htmlFor="cfg_weight">CFG Weight</label>
            <input
              id="cfg_weight"
              style={formStyles.input}
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={form.cfg_weight}
              onChange={set("cfg_weight")}
            />
            <div style={formStyles.hint}>Pacing — higher reads faster/more rushed, lower is slower/deliberate.</div>
          </div>
        </div>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>MP3 tags</div>
        <Id3Fields id3={form.id3} onChange={(id3) => setForm({ ...form, id3 })} />
      </div>

      <button type="submit" style={{ ...styles.button, ...(submitting ? styles.buttonDisabled : {}) }} disabled={submitting}>
        {submitting ? "Submitting…" : submitLabel}
      </button>
      {error && <div style={styles.error}>{error}</div>}
    </form>
  );
}
