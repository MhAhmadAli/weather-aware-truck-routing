import { riskColor, riskLabel } from "../risk";

export default function RiskBadge({ level }) {
  return (
    <span className="risk-badge" style={{ background: riskColor(level) }}>
      {riskLabel(level)}
    </span>
  );
}
