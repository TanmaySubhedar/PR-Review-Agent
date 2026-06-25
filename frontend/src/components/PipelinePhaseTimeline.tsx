import { colors } from "../theme";
import type { PhaseLog } from "../types";

export function PipelinePhaseTimeline({ phases }: { phases: PhaseLog[] }) {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
      {phases.map((phase) => (
        <div
          key={phase.id}
          title={phase.detail ?? phase.phase}
          style={{
            border: `1px solid ${colors.status[phase.status]}`,
            color: colors.status[phase.status],
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
