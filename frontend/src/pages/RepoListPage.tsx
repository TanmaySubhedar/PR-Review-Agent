import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteRepo, listRepos, refreshRepo, registerRepo } from "../api/client";
import { colors } from "../theme";
import type { Repo } from "../types";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_STYLES: Record<Repo["onboarding_status"], { label: string; col: string; pulse: boolean }> = {
  pending:        { label: "Pending",        col: colors.muted,           pulse: false },
  cloning:        { label: "Cloning…",       col: colors.status.running,  pulse: true },
  building_graph: { label: "Building graph…",col: colors.status.running,  pulse: true },
  ready:          { label: "Ready",          col: colors.status.done,     pulse: false },
  failed:         { label: "Failed",         col: colors.status.failed,   pulse: false },
};

function RepoCard({ repo, onDelete, onRefresh }: {
  repo: Repo;
  onDelete: (id: string) => void;
  onRefresh: (id: string) => void;
}) {
  const st = STATUS_STYLES[repo.onboarding_status] ?? STATUS_STYLES.pending;
  const busy = repo.onboarding_status === "cloning" || repo.onboarding_status === "building_graph";

  return (
    <div style={{
      position: "relative", overflow: "hidden",
      background: colors.surface, border: `1px solid ${colors.border}`,
      borderRadius: 14, padding: 20,
    }}>
      {busy && (
        <div style={{ position: "absolute", inset: 0, overflow: "hidden", borderRadius: 14, pointerEvents: "none" }}>
          <div style={{
            position: "absolute", left: 0, right: 0, height: "30%",
            background: "linear-gradient(to bottom, transparent, rgba(139,92,246,0.06), transparent)",
            animation: "scan 2s linear infinite",
          }} />
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: colors.text, fontFamily: "monospace" }}>
          {repo.full_name}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            className={st.pulse ? "pulse-dot" : ""}
            style={{
              width: 7, height: 7, borderRadius: "50%", background: st.col,
              display: "inline-block",
              boxShadow: st.pulse ? `0 0 8px ${st.col}` : "none",
            }}
          />
          <span style={{ fontSize: 11, color: st.col, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {st.label}
          </span>
        </div>
      </div>

      <div style={{ fontSize: 12, color: colors.muted, marginBottom: 12 }}>
        Branch: <code style={{ color: colors.text }}>{repo.default_branch}</code>
        {" · "}Updated {timeAgo(repo.updated_at)}
      </div>

      {repo.onboarding_status === "ready" && repo.graph_node_count != null && (
        <div style={{
          display: "flex", gap: 12, marginBottom: 14,
          fontSize: 12, color: colors.muted,
        }}>
          <span><strong style={{ color: colors.text }}>{repo.graph_node_count.toLocaleString()}</strong> nodes</span>
          <span><strong style={{ color: colors.text }}>{(repo.graph_edge_count ?? 0).toLocaleString()}</strong> edges</span>
          {repo.graph_truncated && (
            <span style={{ color: colors.risk.medium }}>⚠ graph truncated</span>
          )}
        </div>
      )}

      {repo.onboarding_status === "failed" && repo.onboarding_error && (
        <div style={{
          fontSize: 11, color: colors.status.failed,
          background: colors.risk.highDim,
          borderRadius: 6, padding: "6px 10px", marginBottom: 12,
          whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}>
          {repo.onboarding_error}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link
          to={`/repos/${repo.id}/graph`}
          style={{
            fontSize: 12, fontWeight: 600, padding: "5px 12px",
            borderRadius: 6, textDecoration: "none",
            background: repo.onboarding_status === "ready" ? `${colors.accent}22` : colors.surface3,
            color: repo.onboarding_status === "ready" ? colors.accent : colors.muted,
            border: `1px solid ${repo.onboarding_status === "ready" ? `${colors.accent}40` : colors.border}`,
            pointerEvents: repo.onboarding_status === "ready" ? "auto" : "none",
          }}
        >
          View Graph
        </Link>
        <button
          onClick={() => onRefresh(repo.id)}
          disabled={busy}
          style={{
            fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: busy ? "not-allowed" : "pointer",
            background: "none", border: `1px solid ${colors.border}`, color: colors.muted,
          }}
        >
          Rebuild
        </button>
        <button
          onClick={() => onDelete(repo.id)}
          style={{
            fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: "pointer",
            background: "none", border: `1px solid ${colors.border}`, color: colors.muted,
            marginLeft: "auto",
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function RegisterForm({ onRegistered }: { onRegistered: () => void }) {
  const [open, setOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [cloneUrl, setCloneUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const inputStyle = {
    width: "100%", boxSizing: "border-box" as const,
    background: colors.surface2, border: `1px solid ${colors.border}`,
    borderRadius: 6, padding: "8px 10px",
    color: colors.text, fontSize: 13, fontFamily: "monospace",
    outline: "none",
  };
  const labelStyle = { fontSize: 11, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: "0.06em", display: "block", marginBottom: 4 };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^[^/\s]+\/[^/\s]+$/.test(fullName.trim())) {
      setError("Must be in owner/repo format — e.g. TanmaySubhedar/PR-Review-Agent");
      return;
    }
    setLoading(true);
    try {
      await registerRepo({ full_name: fullName.trim(), clone_url: cloneUrl.trim(), default_branch: branch.trim() || "main" });
      setFullName(""); setCloneUrl(""); setBranch("main"); setOpen(false);
      onRegistered();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          fontSize: 13, fontWeight: 600, padding: "8px 16px", borderRadius: 8, cursor: "pointer",
          background: `${colors.accent}22`, border: `1px solid ${colors.accent}40`, color: colors.accent,
        }}
      >
        {open ? "✕ Cancel" : "+ Register Repository"}
      </button>

      {open && (
        <form onSubmit={handleSubmit} style={{
          marginTop: 14, background: colors.surface, border: `1px solid ${colors.border}`,
          borderRadius: 12, padding: 20, display: "flex", flexDirection: "column", gap: 14,
        }}>
          <div>
            <label style={labelStyle}>Repository (owner/name)</label>
            <input style={inputStyle} placeholder="owner/repo-name  (e.g. TanmaySubhedar/PR-Review-Agent)" value={fullName} onChange={e => setFullName(e.target.value)} required />
          </div>
          <div>
            <label style={labelStyle}>Clone URL</label>
            <input style={inputStyle} placeholder="https://github.com/octocat/Hello-World.git" value={cloneUrl} onChange={e => setCloneUrl(e.target.value)} required />
          </div>
          <div>
            <label style={labelStyle}>Default branch</label>
            <input style={inputStyle} value={branch} onChange={e => setBranch(e.target.value)} />
          </div>
          {error && <div style={{ fontSize: 12, color: colors.status.failed }}>{error}</div>}
          <button
            type="submit" disabled={loading}
            style={{
              fontSize: 13, fontWeight: 700, padding: "9px 20px", borderRadius: 8, cursor: loading ? "not-allowed" : "pointer",
              background: colors.accent, border: "none", color: "#fff", alignSelf: "flex-start",
            }}
          >
            {loading ? "Registering…" : "Register & Build Graph"}
          </button>
        </form>
      )}
    </div>
  );
}

export function RepoListPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [error, setError]  = useState<string | null>(null);

  const load = async () => {
    try {
      setRepos(await listRepos());
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const poll = async () => { if (!cancelled) await load(); };
    poll();
    const t = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const handleDelete = async (id: string) => {
    try { await deleteRepo(id); await load(); } catch { /* ignore */ }
  };

  const handleRefresh = async (id: string) => {
    try { await refreshRepo(id); await load(); } catch { /* ignore */ }
  };

  return (
    <div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: colors.text, marginBottom: 20 }}>
        Repositories
      </h2>

      <RegisterForm onRegistered={load} />

      {error && (
        <div style={{
          background: colors.risk.highDim, border: `1px solid ${colors.risk.high}`,
          borderRadius: 8, padding: 12, marginBottom: 16, color: colors.risk.high, fontSize: 13,
        }}>
          Failed to load repos: {error}
        </div>
      )}

      {repos.length === 0 && !error ? (
        <div style={{ textAlign: "center", padding: "80px 24px" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⬡</div>
          <p style={{ color: colors.text, fontWeight: 600, marginBottom: 8 }}>No repositories yet</p>
          <p style={{ color: colors.muted, fontSize: 13 }}>
            Register a repository above to build its call graph.
          </p>
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
          gap: 14,
        }}>
          {repos.map(r => (
            <RepoCard key={r.id} repo={r} onDelete={handleDelete} onRefresh={handleRefresh} />
          ))}
        </div>
      )}
    </div>
  );
}
