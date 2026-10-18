export const RISK_LEVELS = [
  { value: 0, label: "Low", color: "#2e7d32" },
  { value: 1, label: "Moderate", color: "#f2b705" },
  { value: 2, label: "High", color: "#ef6c00" },
  { value: 3, label: "Severe", color: "#c62828" },
  { value: 4, label: "No Travel", color: "#6a1b9a" },
];

export const riskColor = (level) => RISK_LEVELS[level].color;
export const riskLabel = (level) => RISK_LEVELS[level].label;

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// Blend between adjacent band colors for a continuous 0–4 score.
export function scoreColor(score) {
  const level = Math.min(Math.floor(score), RISK_LEVELS.length - 1);
  const next = Math.min(level + 1, RISK_LEVELS.length - 1);
  const t = score - level;
  const [a, b] = [hexToRgb(RISK_LEVELS[level].color), hexToRgb(RISK_LEVELS[next].color)];
  const mixed = a.map((channel, i) => Math.round(channel + (b[i] - channel) * t));
  return `rgb(${mixed.join(", ")})`;
}

// Calm cells stay nearly transparent so the map underneath remains readable.
export const scoreOpacity = (score) => Math.min(0.65, 0.05 + 0.18 * score);

export function formatDuration(seconds) {
  const minutes = Math.round(seconds / 60);
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function formatTime(isoOrDate) {
  return new Date(isoOrDate).toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
