import { RISK_LEVELS, formatDuration, formatTime } from "../risk";
import RiskBadge from "./RiskBadge";

export default function RouteCards({ routes, recommended, selected, onSelect }) {
  return (
    <section>
      <h2>Routes</h2>
      <ul className="route-cards">
        {routes.map((route) => (
          <li key={route.label}>
            <button
              type="button"
              className={`route-card${route.label === selected ? " selected" : ""}`}
              aria-pressed={route.label === selected}
              onClick={() => onSelect(route.label)}
            >
              <div className="route-card-head">
                <strong>Route {route.label}</strong>
                {route.label === recommended && <span className="badge">Recommended</span>}
                <span className="rank">Rank {route.rank}</span>
              </div>
              {route.summary && <div className="muted small">via {route.summary}</div>}
              <div className="stats">
                {route.distance_mi} mi · {formatDuration(route.duration_s)} · arrives {formatTime(route.arrival)}
              </div>
              <RiskBar milesByRisk={route.miles_by_risk} total={route.distance_mi} />
              <div className="risk-miles small">
                <span>No Travel {route.miles_by_risk["No Travel"]} mi</span>
                <span>Severe {route.miles_by_risk.Severe} mi</span>
                <span>High {route.miles_by_risk.High} mi</span>
                <span>Avg risk {route.avg_risk.toFixed(2)}</span>
                <span>
                  Worst <RiskBadge level={route.max_risk} />
                </span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RiskBar({ milesByRisk, total }) {
  return (
    <div className="risk-bar" aria-hidden="true">
      {RISK_LEVELS.map(({ label, color }) => {
        const miles = milesByRisk[label];
        if (!miles) return null;
        return <span key={label} title={`${label}: ${miles} mi`} style={{ width: `${(miles / total) * 100}%`, background: color }} />;
      })}
    </div>
  );
}
