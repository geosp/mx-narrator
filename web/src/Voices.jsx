import { useState, useEffect } from "react";
import { API_BASE, styles } from "./lib.js";
import { LANGS } from "./ScriptForm.jsx";

const DEFAULT_SAMPLE_KEY = "default";
const SAMPLE_LANG_OPTIONS = [{ value: DEFAULT_SAMPLE_KEY, label: "Default (fallback)" }, ...LANGS];

function langLabel(lang) {
  return SAMPLE_LANG_OPTIONS.find((l) => l.value === lang)?.label || lang;
}

// Mirrors worker/voice_storage.py's naming convention — the only place besides the
// server itself that needs to know it, purely to build a playable <audio> src.
function sampleUrl(voiceId, lang) {
  const suffix = lang === DEFAULT_SAMPLE_KEY ? "" : `.${lang}`;
  return `${API_BASE}/media/voices/${voiceId}/voice${suffix}.wav`;
}

const localStyles = {
  voiceCard: {
    background: "#fff",
    border: "1px solid #e2e2df",
    borderRadius: 8,
    padding: 16,
    marginBottom: 16,
  },
  voiceTop: { display: "flex", alignItems: "center", gap: 10, marginBottom: 10 },
  voiceName: { fontWeight: 600, fontSize: 15 },
  sampleRow: { display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid #f0f0ee" },
  sampleLabel: { fontSize: 13, color: "#444", width: 130, flexShrink: 0 },
  audio: { height: 32, flex: 1 },
  removeLink: {
    color: "#b3261e",
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    padding: 0,
    fontFamily: "inherit",
  },
  deleteVoiceLink: { ...styles.link, color: "#b3261e", marginLeft: "auto" },
  addSampleForm: { display: "flex", gap: 8, alignItems: "center", marginTop: 10, flexWrap: "wrap" },
  smallInput: { padding: "6px 8px", border: "1px solid #d0d0cd", borderRadius: 6, fontSize: 13 },
  empty: { color: "#888", fontSize: 14, marginTop: 12 },
};

function AddSampleForm({ voiceId, existingLanguages, onAdded }) {
  const [lang, setLang] = useState(
    SAMPLE_LANG_OPTIONS.find((l) => !existingLanguages.includes(l.value))?.value || DEFAULT_SAMPLE_KEY
  );
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
      formData.append("lang", lang);
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/voices/${voiceId}/samples`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      setFile(null);
      onAdded(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={localStyles.addSampleForm}>
      <select style={localStyles.smallInput} value={lang} onChange={(e) => setLang(e.target.value)}>
        {SAMPLE_LANG_OPTIONS.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>
      <input type="file" accept="audio/wav,.wav" onChange={(e) => setFile(e.target.files[0])} required />
      <button
        type="submit"
        style={{ ...styles.button, ...(submitting ? styles.buttonDisabled : {}) }}
        disabled={submitting}
      >
        {submitting ? "Adding…" : "Add sample"}
      </button>
      {error && <span style={styles.error}>{error}</span>}
    </form>
  );
}

function VoiceCard({ voice, onChanged }) {
  const [busy, setBusy] = useState(false);

  async function handleRemoveSample(lang) {
    if (!window.confirm(`Remove the ${langLabel(lang)} sample from "${voice.name}"?`)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/voices/${voice.id}/samples/${lang}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
      onChanged();
    } catch (err) {
      window.alert(`Failed to remove sample: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteVoice() {
    if (!window.confirm(`Delete the voice "${voice.name}" and all its samples? This cannot be undone.`)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/voices/${voice.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onChanged();
    } catch (err) {
      window.alert(`Failed to delete voice: ${err.message}`);
      setBusy(false);
    }
  }

  return (
    <div style={localStyles.voiceCard}>
      <div style={localStyles.voiceTop}>
        <span style={localStyles.voiceName}>{voice.name}</span>
        <button style={localStyles.deleteVoiceLink} onClick={handleDeleteVoice} disabled={busy}>
          Delete voice
        </button>
      </div>

      {voice.languages.map((lang) => (
        <div key={lang} style={localStyles.sampleRow}>
          <span style={localStyles.sampleLabel}>{langLabel(lang)}</span>
          <audio style={localStyles.audio} controls src={sampleUrl(voice.id, lang)} />
          <button style={localStyles.removeLink} onClick={() => handleRemoveSample(lang)} disabled={busy}>
            Remove
          </button>
        </div>
      ))}

      <AddSampleForm voiceId={voice.id} existingLanguages={voice.languages} onAdded={onChanged} />
    </div>
  );
}

function CreateVoiceForm({ onCreated }) {
  const [name, setName] = useState("");
  const [lang, setLang] = useState(DEFAULT_SAMPLE_KEY);
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
      formData.append("name", name);
      formData.append("lang", lang);
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/voices`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      setName("");
      setFile(null);
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>Add a voice</div>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <input
          style={localStyles.smallInput}
          placeholder="Voice name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select style={localStyles.smallInput} value={lang} onChange={(e) => setLang(e.target.value)}>
          {SAMPLE_LANG_OPTIONS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
        <input type="file" accept="audio/wav,.wav" onChange={(e) => setFile(e.target.files[0])} required />
        <button
          type="submit"
          style={{ ...styles.button, ...(submitting ? styles.buttonDisabled : {}) }}
          disabled={submitting}
        >
          {submitting ? "Uploading…" : "Create voice"}
        </button>
      </form>
      {error && <div style={styles.error}>{error}</div>}
    </div>
  );
}

export default function Voices() {
  const [voices, setVoices] = useState(null);
  const [error, setError] = useState("");

  function refresh() {
    fetch(`${API_BASE}/voices`)
      .then((res) => res.json())
      .then((data) => setVoices(data.voices))
      .catch((err) => setError(err.message));
  }

  useEffect(refresh, []);

  return (
    <div style={styles.page}>
      <a href="/" style={styles.breadcrumb}>&larr; Dashboard</a>
      <h1 style={styles.h1}>Voices</h1>
      <div style={styles.subtitle}>
        Reference samples for Chatterbox voice cloning. Upload a WAV per language, or a single
        "Default" sample used as a fallback for languages with no specific sample.
      </div>

      <CreateVoiceForm onCreated={refresh} />

      {error && <div style={styles.error}>{error}</div>}
      {voices === null && !error && <div style={localStyles.empty}>Loading…</div>}
      {voices !== null && voices.length === 0 && <div style={localStyles.empty}>No voices yet.</div>}

      {voices && voices.map((v) => <VoiceCard key={v.id} voice={v} onChanged={refresh} />)}
    </div>
  );
}
