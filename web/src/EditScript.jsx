import { useState, useEffect } from "react";
import { API_BASE, styles } from "./lib.js";
import ScriptForm, { toScriptInBody } from "./ScriptForm.jsx";

// Mirrors api/main.py's regenerate_script decision (_AUDIO_AFFECTING_*_FIELDS) —
// used only to decide whether to show the destructive-cascade confirm() dialog.
// The server independently makes the same call; this just keeps the UI from
// warning about audio/video being discarded when it actually won't be.
const AUDIO_AFFECTING_EXACT_FIELDS = ["unit_id", "lang", "script_text", "engine_name", "voice_id"];
const AUDIO_AFFECTING_NUMERIC_FIELDS = ["speed", "exaggeration", "cfg_weight", "seed"];

function audioAffectingFieldsChanged(initialValues, form) {
  return (
    AUDIO_AFFECTING_EXACT_FIELDS.some((f) => initialValues[f] !== form[f]) ||
    AUDIO_AFFECTING_NUMERIC_FIELDS.some((f) => Number(initialValues[f]) !== Number(form[f]))
  );
}

const warningBox = {
  background: "#fff4e5",
  border: "1px solid #f0c060",
  borderRadius: 8,
  padding: "12px 16px",
  marginBottom: 24,
  fontSize: 13,
  color: "#663c00",
};

export default function EditScript({ scriptId }) {
  const [initialValues, setInitialValues] = useState(null);
  const [hasVideoJob, setHasVideoJob] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/scripts/${scriptId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setInitialValues({
          unit_id: data.unit_id,
          lang: data.lang,
          series_name: data.series_name,
          script_text: data.script_text,
          engine_name: data.engine_name,
          speed: data.speed,
          exaggeration: data.exaggeration,
          cfg_weight: data.cfg_weight,
          seed: data.seed,
          series_album: data.series_album,
          title: data.title || "",
          voice_id: data.voice_id || "",
          id3: data.id3,
        });
        setHasVideoJob(data.has_video_job);
      })
      .catch((err) => setLoadError(err.message));
  }, [scriptId]);

  async function handleSubmit(form) {
    if (
      hasVideoJob &&
      audioAffectingFieldsChanged(initialValues, form) &&
      !window.confirm(
        "This script has a video review in progress. Saving will regenerate the audio and delete that review — transcription and video review will need to be redone. Continue?"
      )
    ) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/scripts/${scriptId}/regenerate`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(toScriptInBody(form)),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      }
      window.location.href = `${window.location.pathname}?render_job_id=${data.render_job_id}`;
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.page}>
      <a href="/" style={styles.breadcrumb}>&larr; Dashboard</a>
      <h1 style={styles.h1}>Edit script</h1>
      <div style={styles.subtitle}>
        Editing tags alone updates the existing audio in place. Changing the script text or voice
        settings regenerates the audio.
      </div>

      {loadError && <div style={styles.error}>{loadError}</div>}
      {!initialValues && !loadError && <div>Loading…</div>}

      {initialValues && (
        <ScriptForm
          initialValues={initialValues}
          onSubmit={handleSubmit}
          submitLabel="Save and regenerate audio"
          submitting={submitting}
          error={error}
          warning={
            hasVideoJob ? (
              <div style={warningBox}>
                This episode has a video review in progress. Changing the script text or voice
                settings will delete it — transcription and video review will need to be redone
                against the new audio. Editing tags alone is safe and won't affect it.
              </div>
            ) : null
          }
        />
      )}
    </div>
  );
}
