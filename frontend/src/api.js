export async function planTrip(request) {
  const response = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorMessage(data, response.status));
  }
  return data;
}

function errorMessage(data, status) {
  if (data.detail) return data.detail;
  const fieldErrors = Object.entries(data).map(([field, messages]) => `${field}: ${[].concat(messages).join(" ")}`);
  return fieldErrors.length ? fieldErrors.join("; ") : `Request failed (HTTP ${status}).`;
}
