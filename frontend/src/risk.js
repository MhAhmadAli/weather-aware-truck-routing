export const RISK_LEVELS = [
  { value: 0, label: "Low", color: "#2e7d32" },
  { value: 1, label: "Moderate", color: "#f2b705" },
  { value: 2, label: "High", color: "#ef6c00" },
  { value: 3, label: "Severe", color: "#c62828" },
  { value: 4, label: "No Travel", color: "#6a1b9a" },
];

export const riskColor = (level) => RISK_LEVELS[level].color;
export const riskLabel = (level) => RISK_LEVELS[level].label;

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
