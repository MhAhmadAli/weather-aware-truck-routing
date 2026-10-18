export default function Recommendation({ plan }) {
  const { reason, warning } = plan.recommendation;
  return (
    <section className="recommendation">
      <h2>Recommended: Route {plan.recommended}</h2>
      <p>{reason}</p>
      {warning && (
        <p className="warning" role="alert">
          {warning}
        </p>
      )}
      <p className="muted small">
        Ranked by fewest No Travel miles, then Severe miles, High miles, lowest average risk, and shortest travel time.
      </p>
    </section>
  );
}
