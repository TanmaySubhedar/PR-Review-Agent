import { useContext, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getFindings, getPhases, getReview } from "../api/client";
import { ChatContext } from "../App";
import { FindingCard } from "../components/FindingCard";
import { PhaseTracker } from "../components/PhaseTracker";
import { colors } from "../theme";
import type { Finding, PhaseLog, ReviewRun } from "../types";

function riskBadge(r: string | null) {
  if (r === "high")   return { fg: colors.risk.high,   bg: colors.risk.highDim,   glow: `0 0 16px ${colors.risk.high}40` };
  if (r === "medium") return { fg: colors.risk.medium, bg: colors.risk.mediumDim, glow: `0 0 16px ${colors.risk.medium}40` };
  if (r === "low")    return { fg: colors.risk.low,    bg: colors.risk.lowDim,    glow: `0 0 16px ${colors.risk.low}40` };
  return null;
}

export function ReviewDetailPage() {
  const { reviewRunId } = useParams<{ reviewRunId: string }>();
  const { openChat }    = useContext(ChatContext);
  const [run,      setRun]      = useState<ReviewRun | null>(null);
  const [phases,   setPhases]   = useState<PhaseLog[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [showDesc, setShowDesc] = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  useEffect(() => {
    if (!reviewRunId) return;
    const id = reviewRunId;
    let cancelled = false;

    const load = async () => {
      try {
        const [r, p, f] = await Promise.all([getReview(id), getPhases(id), getFindings(id)]);
        if (cancelled) return;
        setRun(r); setPhases(p); setFindings(f);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };

    load();
    const t = setInterval(load, 3000);
    return () => { cancelled = true; clearInterval(t); };
  }, [reviewRunId]);

  if (error) return (
    <div style={{ background: colors.risk.highDim, border: `1px solid ${colors.risk.high}`,
      borderRadius: 8, padding: 16, color: colors.risk.high }}>
      Error: {error}
    </div>
  );

  if (!run) return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, color: colors.muted, padding: 32 }}>
      <span className="spin" style={{ display: "inline-block", fontSize: 20 }}>◎</span> Loading…
    </div>
  );

  const rb = riskBadge(run.risk_level);
  const published  = findings.filter(f => f.published);
  const summarized = findings.filter(f => !f.published && !f.discarded);
  const filtered   = findings.filter(f => f.discarded);

  return (
    <div className="fade-in">
      {/* Back */}
      <Link to="/" style={{ display: "inline-flex", alignItems: "center", gap: 6,
        color: colors.muted, fontSize: 13, marginBottom: 20, transition: "color 0.15s" }}
        onMouseEnter={e => { (e.target as HTMLElement).closest("a")!.style.color = colors.accent; }}
        onMouseLeave={e => { (e.target as HTMLElement).closest("a")!.style.color = colors.muted; }}
      >
        ← All reviews
      </Link>

      {/* PR header */}
      <div style={{
        background: colors.surface, border: `1px solid ${colors.border}`,
        borderRadius: 14, padding: 24, marginBottom: 20,
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 13, color: colors.muted, fontFamily: "monospace" }}>#{run.pr_number}</span>
              {rb && (
                <span style={{
                  fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 20,
                  background: rb.bg, color: rb.fg, boxShadow: rb.glow,
                  textTransform: "uppercase", letterSpacing: "0.07em",
                }}>
                  ● {run.risk_level} risk
                </span>
              )}
              <span style={{
                fontSize: 11, padding: "3px 10px", borderRadius: 20,
                background: colors.surface2, color: colors.muted,
                textTransform: "uppercase", letterSpacing: "0.05em",
              }}>
                {run.status}
              </span>
            </div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: colors.text, lineHeight: 1.3, marginBottom: 8 }}>
              {run.title}
            </h1>
            <a href={run.pr_url} target="_blank" rel="noreferrer" style={{
              fontSize: 13, color: colors.accent, fontFamily: "monospace",
            }}>
              {run.repo_full_name} ↗
            </a>
          </div>

          {/* Ask AI button */}
          <button
            onClick={() => openChat(run)}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              background: `linear-gradient(135deg, ${colors.accent}, #8b5cf6)`,
              border: "none", borderRadius: 10, padding: "10px 16px",
              color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
              boxShadow: `0 4px 16px ${colors.accentDim}`,
              transition: "opacity 0.15s",
              flexShrink: 0,
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = "0.85"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = "1"; }}
          >
            ✦ Ask AI about this PR
          </button>
        </div>

        {run.error && (
          <div style={{ marginTop: 12, background: colors.risk.highDim, border: `1px solid ${colors.risk.high}`,
            borderRadius: 8, padding: "8px 12px", color: colors.risk.high, fontSize: 13 }}>
            Pipeline error: {run.error}
          </div>
        )}
      </div>

      {/* Phase tracker */}
      <PhaseTracker phases={phases} />

      {/* Summary + Suggested desc */}
      {(run.change_summary || run.suggested_pr_description) && (
        <div style={{ display: "grid", gridTemplateColumns: run.suggested_pr_description ? "1fr 1fr" : "1fr",
          gap: 14, marginBottom: 20 }}>
          {run.change_summary && (
            <div style={{ background: colors.surface, border: `1px solid ${colors.border}`,
              borderRadius: 12, padding: 18 }}>
              <p style={{ fontSize: 11, color: colors.muted, textTransform: "uppercase",
                letterSpacing: "0.08em", fontWeight: 600, marginBottom: 8 }}>Change Summary</p>
              <p style={{ color: colors.text, lineHeight: 1.6, fontSize: 13 }}>{run.change_summary}</p>
            </div>
          )}
          {run.suggested_pr_description && (
            <div style={{ background: colors.surface, border: `1px solid ${colors.border}`,
              borderRadius: 12, padding: 18 }}>
              <button
                onClick={() => setShowDesc(v => !v)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0,
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  width: "100%", marginBottom: showDesc ? 10 : 0 }}
              >
                <span style={{ fontSize: 11, color: colors.muted, textTransform: "uppercase",
                  letterSpacing: "0.08em", fontWeight: 600 }}>Suggested PR Description</span>
                <span style={{ color: colors.muted, fontSize: 14, transform: showDesc ? "rotate(180deg)" : "none",
                  transition: "transform 0.2s" }}>▾</span>
              </button>
              {showDesc && (
                <pre style={{ background: colors.surface2, border: `1px solid ${colors.border}`,
                  borderRadius: 6, padding: 10, fontSize: 12, overflowX: "auto",
                  color: colors.muted, whiteSpace: "pre-wrap", fontFamily: "monospace", margin: 0 }}>
                  {run.suggested_pr_description}
                </pre>
              )}
            </div>
          )}
        </div>
      )}

      {/* Findings */}
      <div style={{ marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: colors.text, textTransform: "uppercase",
          letterSpacing: "0.08em" }}>
          Findings
        </h2>
        <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
          <span style={{ color: colors.status.done }}>✓ {published.length} posted</span>
          <span style={{ color: colors.medium }}>→ {summarized.length} summary</span>
          <span style={{ color: colors.muted }}>✕ {filtered.length} filtered</span>
        </div>
      </div>

      {findings.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px 24px", color: colors.muted, fontSize: 13 }}>
          {run.status === "done" ? "No findings — clean PR!" : "Waiting for analysis to complete…"}
        </div>
      ) : (
        findings.map((f, i) => <FindingCard key={f.id} finding={f} index={i} />)
      )}
    </div>
  );
}
