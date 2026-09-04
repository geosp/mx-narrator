// Plain parse/serialize for the SRT format's simple block structure. No deps —
// mirrors worker/id3.py's "small focused module" convention. Used by
// VideoReview.jsx's SrtReview to render one editable row per caption instead of
// one giant raw-text textarea, so the active row can highlight/scroll in sync
// with audio playback.
//
//   index
//   HH:MM:SS,mmm --> HH:MM:SS,mmm
//   text (one or more lines)
//   <blank line>

const TIMESTAMP_RE = /(\d{2}):(\d{2}):(\d{2}),(\d{3})/;
const TIMESTAMP_LINE_RE = /(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})/;

function parseTimestamp(ts) {
  const m = TIMESTAMP_RE.exec(ts);
  if (!m) return 0;
  const [, hh, mm, ss, ms] = m;
  return Number(hh) * 3600 + Number(mm) * 60 + Number(ss) + Number(ms) / 1000;
}

function formatTimestamp(totalSeconds) {
  const clamped = Math.max(0, totalSeconds);
  const hh = Math.floor(clamped / 3600);
  const mm = Math.floor((clamped % 3600) / 60);
  const ss = Math.floor(clamped % 60);
  const ms = Math.round((clamped - Math.floor(clamped)) * 1000);
  const pad = (n, len = 2) => String(n).padStart(len, "0");
  return `${pad(hh)}:${pad(mm)}:${pad(ss)},${pad(ms, 3)}`;
}

export function parseSrt(text) {
  const blocks = text.replace(/\r\n/g, "\n").trim().split(/\n\n+/);
  const entries = [];
  for (const block of blocks) {
    if (!block.trim()) continue;
    const lines = block.split("\n");
    const indexLine = lines[0]?.trim();
    const timestampLine = lines[1] || "";
    const match = TIMESTAMP_LINE_RE.exec(timestampLine);
    if (!match) continue; // skip malformed blocks rather than throw — best-effort display
    entries.push({
      index: Number(indexLine) || entries.length + 1,
      start: parseTimestamp(match[1]),
      end: parseTimestamp(match[2]),
      text: lines.slice(2).join("\n"),
    });
  }
  return entries;
}

export function serializeSrt(entries) {
  return entries
    .map(
      (e, i) =>
        `${i + 1}\n${formatTimestamp(e.start)} --> ${formatTimestamp(e.end)}\n${e.text}\n`
    )
    .join("\n");
}
