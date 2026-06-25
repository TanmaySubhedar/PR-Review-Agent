interface ConfidenceBadgeProps {
  confidence: number;
  published: boolean;
  discarded: boolean;
}

export function ConfidenceBadge({ confidence, published, discarded }: ConfidenceBadgeProps) {
  const label = published ? "published" : discarded ? "discarded" : "summary-only";
  const color = published ? "#1a7f37" : discarded ? "#999" : "#9a6700";

  return (
    <span
      style={{
        border: `1px solid ${color}`,
        color,
        borderRadius: 4,
        padding: "2px 6px",
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {label} · {confidence.toFixed(2)}
    </span>
  );
}
