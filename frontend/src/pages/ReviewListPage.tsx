import { useContext, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReviews } from "../api/client";
import { ChatContext } from "../App";
import { colors } from "../theme";
import type { ReviewRun } from "../types";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function riskColor(r: string | null) {
  if (r === "high")   return { fg: colors.risk.high,   bg: colors.risk.highDim };
  if (r === "medium") return { fg: colors.risk.medium, bg: colors.risk.mediumDim };
  if (r === "low")    return { fg: colors.risk.low,    bg: colors.risk.lowDim };
  return { fg: colors.muted, bg: colors.surface3 };
}

function statusInfo(s: ReviewRun["status"]) {
  if (s === "done")      return { label: "Done",       col: colors.status.done };
  if (s === "analyzing") return { label: "Analyzing",  col: colors.status.running };
  if (s === "failed")    return { label: "Failed",     col: colors.status.failed };
  return                        { label: "Received",   col: colors.muted };
}

function ReviewCard({ run, index }: { run: ReviewRun; index: number }) {
  const { openChat } = useContext(ChatContext);
  const analyzing = run.status === "analyzing" || run.status === "received";
  const risk = riskColor(run.risk_level);
  const st   = statusInfo(run.status);

  return (
    <div
      className={`fade-up stagger-${Math.min(index + 1, 6)}`}
      style={{
        position: "relative", overflow: "hidden",
        background: colors.surface, border: `1px solid ${colors.border}`,
        borderRadius: 14, padding: 20,
        transition: "border-color 0.2s, box-shadow 0.2s",
        cursor: "default",
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLElement;
        el.style.borderColor = colors.borderStrong;
        el.style.boxShadow = "0 4px 24px rgba(0,0,0,0.3)";
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLElement;
        el.style.borderColor = colors.border;
        el.style.boxShadow = "none";
      }}
    >
      {/* Scanning overlay for analyzing state */}
      {analyzing && (
        <div style={{ position: "absolute", inset: 0, overflow: "hidden", borderRadius: 14, pointerEvents: "none" }}>
          <div style={{
            position: "absolute", left: 0, right: 0, height: "30%",
            background: "linear-gradient(to bottom, transparent, rgba(139,92,246,0.06), transparent)",
            animation: "scan 2s linear infinite",
          }} />
        </div>
      )}

      {/* Top row: repo + status */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: colors.muted, fontFamily: "monospace" }}>
          {run.repo_full_name}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            className={analyzing ? "pulse-dot" : ""}
            style={{
              width: 7, height: 7, borderRadius: "50%",
              background: st.col, display: "inline-block",
              boxShadow: analyzing ? `0 0 8px ${st.col}` : "none",
            }}
          />
          <span style={{ fontSize: 11, color: st.col, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {st.label}
          </span>
        </div>
      </div>

      {/* PR title */}
      <Link
        to={`/reviews/${run.id}`}
        style={{ display: "block", marginBottom: 12 }}
      >
        <span style={{ fontSize: 12, color: colors.muted }}>#{run.pr_number}</span>{" "}
        <span style={{ fontSize: 14, fontWeight: 600, color: colors.text, lineHeight: 1.4 }}>
          {run.title.length > 60 ? run.title.slice(0, 57) + "…" : run.title}
        </span>
      </Link>

      {/* Bottom row: risk + time + ask button */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {run.risk_level ? (
          <span style={{
            fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 20,
            background: risk.bg, color: risk.fg,
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            ● {run.risk_level}
          </span>
        ) : analyzing ? (
          <span style={{ fontSize: 11, color: colors.muted }}>assessing…</span>
        ) : null}

        <span style={{ fontSize: 12, color: colors.muted, marginLeft: "auto" }}>
          {timeAgo(run.updated_at)}
        </span>

        <button
          onClick={() => openChat(run)}
          style={{
            background: "none", border: `1px solid ${colors.border}`,
            borderRadius: 6, padding: "3px 8px", cursor: "pointer",
            fontSize: 11, color: colors.muted, transition: "all 0.15s",
          }}
          onMouseEnter={e => {
            const el = e.currentTarget as HTMLElement;
            el.style.borderColor = colors.accent;
            el.style.color = colors.accent;
          }}
          onMouseLeave={e => {
            const el = e.currentTarget as HTMLElement;
            el.style.borderColor = colors.border;
            el.style.color = colors.muted;
          }}
        >
          ✦ Ask AI
        </button>
      </div>
    </div>
  );
}

function StatPill({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div style={{
      background: colors.surface, border: `1px solid ${colors.border}`,
      borderRadius: 10, padding: "10px 16px", textAlign: "center", minWidth: 80,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: color ?? colors.text }}>{value}</div>
      <div style={{ fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
    </div>
  );
}

export function ReviewListPage() {
  const [reviews, setReviews] = useState<ReviewRun[]>([]);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await listReviews();
        if (!cancelled) setReviews(data);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    load();
    const t = setInterval(load, 3000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const done      = reviews.filter(r => r.status === "done").length;
  const analyzing = reviews.filter(r => r.status === "analyzing" || r.status === "received").length;
  const failed    = reviews.filter(r => r.status === "failed").length;
  const highRisk  = reviews.filter(r => r.risk_level === "high").length;

  return (
    <div>
      {error && (
        <div style={{ background: colors.risk.highDim, border: `1px solid ${colors.risk.high}`,
          borderRadius: 8, padding: 12, marginBottom: 16, color: colors.risk.high, fontSize: 13 }}>
          Failed to load reviews: {error}
        </div>
      )}

      {/* Stats */}
      {reviews.length > 0 && (
        <div className="fade-in" style={{ display: "flex", gap: 10, marginBottom: 24, flexWrap: "wrap" }}>
          <StatPill label="Total"     value={reviews.length} />
          <StatPill label="Done"      value={done}      color={colors.status.done} />
          <StatPill label="Analyzing" value={analyzing} color={analyzing > 0 ? colors.status.running : undefined} />
          <StatPill label="Failed"    value={failed}    color={failed > 0 ? colors.status.failed : undefined} />
          <StatPill label="High Risk" value={highRisk}  color={highRisk > 0 ? colors.risk.high : undefined} />
        </div>
      )}

      {/* Grid */}
      {reviews.length === 0 && !error ? (
        <div style={{ textAlign: "center", padding: "80px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⬡</div>
          <p style={{ color: colors.text, fontWeight: 600, marginBottom: 8 }}>No reviews yet</p>
          <p style={{ color: colors.muted, fontSize: 13 }}>
            Configure a GitHub webhook and open a pull request to see reviews here.
          </p>
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: 14,
        }}>
          {reviews.map((run, i) => <ReviewCard key={run.id} run={run} index={i} />)}
        </div>
      )}
    </div>
  );
}
