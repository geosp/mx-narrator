import { useState } from "react";
import { API_BASE, styles } from "./lib.js";
import ScriptForm, { initialForm, toScriptInBody } from "./ScriptForm.jsx";

export default function App() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(form) {
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/scripts`, {
        method: "POST",
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
      <h1 style={styles.h1}>Mx Narrator Studio</h1>
      <div style={styles.subtitle}>Upload a script, set its tags, generate narrated audio.</div>

      <ScriptForm
        initialValues={initialForm}
        onSubmit={handleSubmit}
        submitLabel="Generate audio"
        submitting={submitting}
        error={error}
      />
    </div>
  );
}
