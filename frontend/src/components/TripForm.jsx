import { useState } from "react";

function defaultDeparture() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(0, 0, 0);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

export default function TripForm({ onSubmit, loading }) {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departure, setDeparture] = useState(defaultDeparture);
  const [loadLb, setLoadLb] = useState("35000");
  const [intervalMi, setIntervalMi] = useState("25");

  function handleSubmit(event) {
    event.preventDefault();
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      // datetime-local is in the browser's timezone; send an unambiguous UTC instant.
      departure: new Date(departure).toISOString(),
      load_lb: Number(loadLb),
      interval_mi: Number(intervalMi),
    });
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <label>
        Origin
        <input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="e.g. Denver, CO" required />
      </label>
      <label>
        Destination
        <input
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="e.g. Salt Lake City, UT"
          required
        />
      </label>
      <label>
        Departure (local time)
        <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
      </label>
      <div className="form-row">
        <label>
          Load weight (lb)
          <input
            type="number"
            min="1"
            max="200000"
            step="1"
            value={loadLb}
            onChange={(e) => setLoadLb(e.target.value)}
            required
          />
        </label>
        <label>
          Weather sample every
          <select value={intervalMi} onChange={(e) => setIntervalMi(e.target.value)}>
            <option value="10">10 miles</option>
            <option value="25">25 miles</option>
            <option value="50">50 miles</option>
          </select>
        </label>
      </div>
      <button type="submit" disabled={loading}>
        {loading ? "Planning… (fetching routes and forecasts)" : "Plan routes"}
      </button>
    </form>
  );
}
