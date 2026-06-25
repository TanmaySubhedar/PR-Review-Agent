import type { Finding } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";

export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <div style={{ border: "1px solid #d0d7de", borderRadius: 6, padding: 12, marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <code style={{ fontSize: 13 }}>
          {finding.file}
          {finding.line ? `:${finding.line}` : ""}
        </code>
        <ConfidenceBadge
          confidence={finding.confidence}
          published={finding.published}
          discarded={finding.discarded}
        />
      </div>
      <div style={{ fontSize: 12, color: "#57606a", marginBottom: 6 }}>
        {finding.dimension} · {finding.severity}
      </div>
      <p style={{ margin: "0 0 6px" }}>{finding.finding}</p>
      <pre
        style={{
          background: "#f6f8fa",
          padding: 8,
          borderRadius: 4,
          fontSize: 12,
          overflowX: "auto",
          margin: 0,
        }}
      >
        {finding.evidence}
      </pre>
    </div>
  );
}
