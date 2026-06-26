import type { PhaseLog, PhaseStatus } from "../types";
import { colors } from "../theme";

const PHASES = [
  { key: "ingestion",        label: "Ingest"    },
  { key: "diff_analysis",    label: "Diff"      },
  { key: "blast_radius",     label: "Blast"     },
  { key: "context_retrieval",label: "Context"   },
  { key: "synthesis",        label: "Synthesize"},
  { key: "review",           label: "Review"    },
  { key: "critic",           label: "Critic"    },
  { key: "publish",          label: "Publish"   },
] as const;

function statusColor(s: PhaseStatus) {
  if (s === "done")    return colors.status.done;
  if (s === "running") return colors.status.running;
  if (s === "failed")  return colors.status.failed;
  return colors.status.pending;
}

function PhaseNode({ label, status, index }: { label: string; status: PhaseStatus; index: number }) {
  const isRunning = status === "running";
  const isDone    = status === "done";
  const isFailed  = status === "failed";
  const col = statusColor(status);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, minWidth: 56 }}>
      {/* Circle */}
      <div
        className={isRunning ? "pulse-dot" : ""}
        style={{
          width: 28,
          height: 28,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
          fontWeight: 700,
          fontFamily: "monospace",
          transition: "all 0.3s ease",
          background: isDone || isFailed ? col : "transparent",
          border: `2px solid ${col}`,
          color: isDone || isFailed ? "#fff" : col,
          boxShadow: isRunning ? `0 0 12px ${col}` : isDone ? `0 0 8px ${col}40` : "none",
        }}
      >
        {isFailed ? "✕" : isDone ? "✓" : isRunning ? (
          <span className="spin" style={{ display: "inline-block", fontSize: 10 }}>◎</span>
        ) : (index + 1)}
      </div>
      {/* Label */}
      <span style={{
        fontSize: 10,
        color: status === "pending" ? colors.muted : col,
        fontWeight: isRunning ? 600 : 400,
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}>
        {label}
      </span>
    </div>
  );
}

function Connector({ leftDone }: { leftDone: boolean }) {
  return (
    <div style={{ flex: 1, height: 2, marginBottom: 20, position: "relative", background: colors.surface3 }}>
      <div style={{
        position: "absolute",
        inset: 0,
        background: colors.status.done,
        transform: `scaleX(${leftDone ? 1 : 0})`,
        transformOrigin: "left",
        transition: "transform 0.4s ease",
        boxShadow: leftDone ? `0 0 6px ${colors.status.done}60` : "none",
      }} />
    </div>
  );
}

export function PhaseTracker({ phases }: { phases: PhaseLog[] }) {
  const statusMap = Object.fromEntries(phases.map(p => [p.phase, p.status])) as Record<string, PhaseStatus>;

  return (
    <div style={{
      background: colors.surface,
      border: `1px solid ${colors.border}`,
      borderRadius: 12,
      padding: "16px 20px",
      marginBottom: 24,
    }}>
      <p style={{ fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14, fontWeight: 600 }}>
        Pipeline Progress
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 0, overflowX: "auto", paddingBottom: 2 }}>
        {PHASES.map((phase, i) => {
          const status: PhaseStatus = statusMap[phase.key] ?? "pending";
          const prevDone = i > 0 && (statusMap[PHASES[i - 1].key] ?? "pending") === "done";
          return (
            <div key={phase.key} style={{ display: "flex", alignItems: "center", flex: i < PHASES.length - 1 ? "1 1 auto" : "0 0 auto" }}>
              <PhaseNode label={phase.label} status={status} index={i} />
              {i < PHASES.length - 1 && <Connector leftDone={prevDone} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
