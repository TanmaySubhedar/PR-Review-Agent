import type { PhaseLog } from "../types";

const STATUS_COLOR: Record<string, string> = {
  pending: "#d0d7de",
  running: "#0969da",
  done: "#1a7f37",
  failed: "#cf222e",
};

export function PipelinePhaseTimeline({ phases }: { phases: PhaseLog[] }) {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
      {phases.map((phase) => (
        <div
          key={phase.id}
          title={phase.detail ?? phase.phase}
          style={{
            border: `1px solid ${STATUS_COLOR[phase.status]}`,
            color: STATUS_COLOR[phase.status],
            borderRadius: 999,
            padding: "4px 10px",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {phase.phase}
        </div>
      ))}
    </div>
  );
}
