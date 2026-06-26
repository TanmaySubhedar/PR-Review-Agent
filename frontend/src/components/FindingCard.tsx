import type { Finding } from "../types";
import { colors } from "../theme";

const DIM_LABELS: Record<string, string> = {
  correctness:     "Correctness",
  security:        "Security",
  performance:     "Performance",
  logging:         "Logging",
  architecture:    "Architecture",
  testing:         "Testing",
  maintainability: "Maintainability",
};

const DIM_ICONS: Record<string, string> = {
  correctness:     "⚡",
  security:        "🔒",
  performance:     "⚡",
  logging:         "📋",
  architecture:    "🏗",
  testing:         "🧪",
  maintainability: "🔧",
};

export function FindingCard({ finding, index = 0 }: { finding: Finding; index?: number }) {
  const sevColor = colors.severity[finding.severity] ?? colors.accent;
  const sevDim   = colors.dim[finding.severity]      ?? colors.accentDim;

  const statusLabel = finding.published ? "posted" : finding.discarded ? "filtered" : "summary";
  const statusColor = finding.published ? colors.status.done : finding.discarded ? colors.muted : colors.medium;

  return (
    <div
      className={`fade-up stagger-${Math.min(index + 1, 6)}`}
      style={{
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderLeft: `3px solid ${sevColor}`,
        borderRadius: 10,
        padding: 16,
        marginBottom: 10,
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {/* Dimension badge */}
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            background: sevDim, color: sevColor,
            fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
            textTransform: "uppercase", letterSpacing: "0.05em",
          }}>
            {DIM_ICONS[finding.dimension]} {DIM_LABELS[finding.dimension] ?? finding.dimension}
          </span>
          {/* Severity badge */}
          <span style={{
            background: sevDim, color: sevColor,
            fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
            textTransform: "uppercase", letterSpacing: "0.05em",
          }}>
            {finding.severity}
          </span>
          {/* Status */}
          <span style={{ fontSize: 11, color: statusColor, fontWeight: 500 }}>
            {statusLabel === "posted" ? "✓ posted to GitHub" : statusLabel === "filtered" ? "✕ filtered" : "→ summary"}
          </span>
        </div>
        {/* Confidence */}
        <span style={{ fontSize: 11, color: colors.muted, whiteSpace: "nowrap", fontFamily: "monospace" }}>
          {(finding.confidence * 100).toFixed(0)}% conf.
        </span>
      </div>

      {/* File location */}
      <code style={{
        display: "block", fontSize: 12,
        color: colors.accent, background: colors.accentDim,
        padding: "3px 8px", borderRadius: 4, marginBottom: 8,
        fontFamily: "'SF Mono','Fira Code',Consolas,monospace",
      }}>
        {finding.file}{finding.line != null ? `:${finding.line}` : ""}
      </code>

      {/* Finding text */}
      <p style={{ color: colors.text, marginBottom: 8, lineHeight: 1.5 }}>{finding.finding}</p>

      {/* Evidence */}
      {finding.evidence && (
        <pre style={{
          background: colors.surface2,
          border: `1px solid ${colors.border}`,
          borderRadius: 6, padding: "8px 10px",
          fontSize: 12, overflowX: "auto", margin: 0,
          color: colors.muted, lineHeight: 1.5,
          fontFamily: "'SF Mono','Fira Code',Consolas,monospace",
          whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}>
          {finding.evidence}
        </pre>
      )}
    </div>
  );
}
