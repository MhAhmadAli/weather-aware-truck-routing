import { formatTime } from "../risk";
import RiskBadge from "./RiskBadge";

export default function CheckpointTable({ route }) {
  return (
    <section>
      <h2>Route {route.label} checkpoints</h2>
      <p className="muted small">Weather is the forecast at each checkpoint for the truck's estimated arrival time.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp, index) => (
              <tr key={index}>
                <td>{cp.mile}</td>
                <td>{formatTime(cp.eta)}</td>
                <td>{cp.wind_mph} mph</td>
                <td>{cp.rain_in_hr} in/hr</td>
                <td>{cp.snow_in_hr} in/hr</td>
                <td>
                  <RiskBadge level={cp.risk} />
                  {cp.factors.length > 0 && <div className="muted small">{cp.factors.join(", ")}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
