export default function UsageBar({ usage }) {
  const { input_tokens, output_tokens, estimated_cost_usd } = usage;

  return (
    <div className="usage-bar">
      <span>
        <strong>Tokens:</strong> {input_tokens.toLocaleString()} in / {output_tokens.toLocaleString()} out
      </span>
      <span>
        <strong>Estimated cost:</strong> ${estimated_cost_usd.toFixed(6)}
      </span>
    </div>
  );
}
