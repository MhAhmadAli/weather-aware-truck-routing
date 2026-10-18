import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Pane, Polyline, Popup, Rectangle, TileLayer, Tooltip, useMap } from "react-leaflet";
import { RISK_LEVELS, formatDuration, formatTime, riskColor, riskLabel, scoreColor, scoreOpacity } from "../risk";
import RiskBadge from "./RiskBadge";

const ROUTE_COLOR = "#1d4ed8";
const ROUTE_COLOR_MUTED = "#64748b";
const US_CENTER = [39.5, -98.35];

export default function RouteMap({ plan, selected, onSelect }) {
  const [hour, setHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);

  useEffect(() => setHour(0), [plan]);

  // Draw the selected route last so it sits on top.
  const routes = plan ? [...plan.routes].sort((a, b) => (a.label === selected) - (b.label === selected)) : [];

  return (
    <div className="map-wrap">
      <MapContainer center={US_CENTER} zoom={4} className="map">
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        <Pane name="heatmap" style={{ zIndex: 350 }}>
          {plan && showHeatmap && <HeatmapCells heatmap={plan.heatmap} hour={hour} />}
        </Pane>
        {routes.map((route) => (
          <RouteLayer
            // Remount on selection change so Leaflet re-adds the layer in draw order.
            key={`${route.label}-${route.label === selected}`}
            route={route}
            isSelected={route.label === selected}
            isRecommended={route.label === plan.recommended}
            onSelect={onSelect}
          />
        ))}
        {plan && <Endpoints plan={plan} />}
        <FitBounds plan={plan} />
      </MapContainer>
      {plan && (
        <HeatmapControls
          heatmap={plan.heatmap}
          hour={hour}
          onHourChange={setHour}
          show={showHeatmap}
          onShowChange={setShowHeatmap}
        />
      )}
      <Legend />
    </div>
  );
}

function RouteLayer({ route, isSelected, isRecommended, onSelect }) {
  return (
    <>
      <Polyline
        positions={route.geometry}
        pathOptions={{
          color: isSelected ? ROUTE_COLOR : ROUTE_COLOR_MUTED,
          weight: isSelected ? 6 : 4,
          opacity: isSelected ? 0.9 : 0.55,
        }}
        eventHandlers={{ click: () => onSelect(route.label) }}
      >
        <Tooltip sticky>
          Route {route.label}
          {isRecommended ? " (recommended)" : ""} · {route.distance_mi} mi · {formatDuration(route.duration_s)}
        </Tooltip>
      </Polyline>
      {route.checkpoints.map((cp, index) => (
        <CircleMarker
          key={index}
          center={[cp.lat, cp.lon]}
          radius={isSelected ? 7 : 4}
          pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: riskColor(cp.risk), fillOpacity: isSelected ? 1 : 0.75 }}
        >
          <Popup>
            <strong>
              Route {route.label} · mile {cp.mile}
            </strong>
            <div>ETA {formatTime(cp.eta)}</div>
            <div>
              Wind {cp.wind_mph} mph · Rain {cp.rain_in_hr} in/hr · Snow {cp.snow_in_hr} in/hr
            </div>
            <div>
              <RiskBadge level={cp.risk} /> {cp.factors.join(", ")}
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}

function HeatmapCells({ heatmap, hour }) {
  const half = heatmap.step_deg / 2;
  return heatmap.cells.map((cell) => {
    const risk = cell.risk[hour];
    const score = cell.score[hour];
    return (
      <Rectangle
        key={`${cell.lat},${cell.lon}`}
        bounds={[
          [cell.lat - half, cell.lon - half],
          [cell.lat + half, cell.lon + half],
        ]}
        pathOptions={{ stroke: false, fillColor: scoreColor(score), fillOpacity: scoreOpacity(score) }}
      >
        <Tooltip sticky>
          {riskLabel(risk)} · wind {cell.wind_mph[hour]} mph · rain {cell.rain_in_hr[hour]} in/hr · snow{" "}
          {cell.snow_in_hr[hour]} in/hr
        </Tooltip>
      </Rectangle>
    );
  });
}

function HeatmapControls({ heatmap, hour, onHourChange, show, onShowChange }) {
  const time = new Date(new Date(heatmap.start).getTime() + hour * 60 * 60 * 1000);
  return (
    <div className="map-panel heatmap-controls">
      <label className="checkbox">
        <input type="checkbox" checked={show} onChange={(e) => onShowChange(e.target.checked)} />
        Weather risk heatmap
      </label>
      <input
        type="range"
        min="0"
        max={heatmap.hours}
        value={hour}
        disabled={!show}
        onChange={(e) => onHourChange(Number(e.target.value))}
        aria-label="Forecast hour"
      />
      <div className="small">
        Departure +{hour}h · {formatTime(time)}
      </div>
      <div className="small muted">Shading deepens as wind, rain or snow approach the next risk band.</div>
    </div>
  );
}

function Legend() {
  return (
    <div className="map-panel legend">
      {RISK_LEVELS.map(({ label, color }) => (
        <div key={label} className="legend-item">
          <span className="swatch" style={{ background: color }} />
          {label}
        </div>
      ))}
    </div>
  );
}

function Endpoints({ plan }) {
  return [
    ["Origin", plan.origin],
    ["Destination", plan.destination],
  ].map(([kind, place]) => (
    <CircleMarker
      key={kind}
      center={[place.lat, place.lon]}
      radius={9}
      pathOptions={{ color: "#111827", weight: 3, fillColor: "#ffffff", fillOpacity: 1 }}
    >
      <Tooltip>
        {kind}: {place.name}
      </Tooltip>
    </CircleMarker>
  ));
}

function FitBounds({ plan }) {
  const map = useMap();
  useEffect(() => {
    if (plan) {
      map.fitBounds(plan.routes.flatMap((route) => route.geometry), { padding: [30, 30] });
    }
  }, [plan, map]);
  return null;
}
