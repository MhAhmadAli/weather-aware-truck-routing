import { useState } from "react";
import { planTrip } from "./api";
import CheckpointTable from "./components/CheckpointTable";
import Recommendation from "./components/Recommendation";
import RouteCards from "./components/RouteCards";
import RouteMap from "./components/RouteMap";
import TripForm from "./components/TripForm";

export default function App() {
  const [plan, setPlan] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(request) {
    setLoading(true);
    setError(null);
    try {
      const result = await planTrip(request);
      setPlan(result);
      setSelected(result.recommended);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const selectedRoute = plan?.routes.find((route) => route.label === selected);

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Weather-Aware Truck Routing</h1>
        <TripForm onSubmit={handleSubmit} loading={loading} />
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {plan && (
          <>
            <Recommendation plan={plan} />
            <RouteCards routes={plan.routes} recommended={plan.recommended} selected={selected} onSelect={setSelected} />
            {selectedRoute && <CheckpointTable route={selectedRoute} />}
          </>
        )}
      </aside>
      <main className="map-pane">
        <RouteMap plan={plan} selected={selected} onSelect={setSelected} />
      </main>
    </div>
  );
}
