import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getRepo, getRepoGraph } from "../api/client";
import { colors } from "../theme";
import type { GraphResponse, Repo } from "../types";

// ── Layout via dagre ──────────────────────────────────────────────────────────

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", ranksep: 80, nodesep: 40 });

  nodes.forEach(n => g.setNode(n.id, { width: 160, height: 36 }));
  edges.forEach(e => g.setEdge(e.source, e.target));
  dagre.layout(g);

  return nodes.map(n => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - 80, y: pos.y - 18 } };
  });
}

// ── API → React Flow conversion ───────────────────────────────────────────────

function toFlowGraph(
  data: GraphResponse
): { nodes: Node[]; edges: Edge[] } {
  const edgeColor: Record<string, string> = {
    imports: colors.accent,
    calls: "#8b5cf6",
    contains: colors.muted,
  };

  const rawNodes: Node[] = data.nodes.map(n => ({
    id: n.id,
    data: {
      label: n.file ? n.file.split("/").pop() ?? n.id : (n.name ?? n.id),
      fullLabel: n.file ?? n.name ?? n.id,
      kind: n.kind,
    },
    position: { x: 0, y: 0 },
    style: {
      background: n.kind === "module" ? colors.surface2 : "#1e1b2e",
      border: `1px solid ${n.kind === "module" ? `${colors.accent}60` : "#8b5cf660"}`,
      borderRadius: 8,
      color: colors.text,
      fontSize: 11,
      fontFamily: "monospace",
      padding: "4px 10px",
      maxWidth: 160,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
    },
  }));

  const rawEdges: Edge[] = data.links.map((l, i) => ({
    id: `e-${i}`,
    source: l.source,
    target: l.target,
    label: l.kind,
    type: "smoothstep",
    animated: l.kind === "calls",
    style: { stroke: edgeColor[l.kind] ?? colors.muted, strokeWidth: 1.5 },
    labelStyle: { fill: colors.muted, fontSize: 9 },
  }));

  const laidOut = applyDagreLayout(rawNodes, rawEdges);
  return { nodes: laidOut, edges: rawEdges };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function RepoGraphPage() {
  const { repoId } = useParams<{ repoId: string }>();
  const [repo, setRepo]         = useState<Repo | null>(null);
  const [graph, setGraph]       = useState<GraphResponse | null>(null);
  const [moduleOnly, setModuleOnly] = useState(true);
  const [search, setSearch]     = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);

  const loadGraph = useCallback(async (mo: boolean) => {
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      const [r, g] = await Promise.all([getRepo(repoId), getRepoGraph(repoId, mo)]);
      setRepo(r);
      setGraph(g);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [repoId]);

  useEffect(() => { loadGraph(moduleOnly); }, [loadGraph, moduleOnly]);

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    return toFlowGraph(graph);
  }, [graph]);

  const highlightedNodes = useMemo(() => {
    if (!search.trim()) return nodes;
    const q = search.toLowerCase();
    return nodes.map(n => ({
      ...n,
      style: {
        ...n.style,
        opacity: (n.data.fullLabel as string).toLowerCase().includes(q) ? 1 : 0.2,
      },
    }));
  }, [nodes, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 56px)" }}>
      {/* Header */}
      <div style={{
        padding: "16px 24px", borderBottom: `1px solid ${colors.border}`,
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        background: colors.surface,
      }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: colors.text, fontFamily: "monospace" }}>
            {repo?.full_name ?? "…"}
          </div>
          {graph && (
            <div style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>
              {graph.node_count.toLocaleString()} nodes · {graph.edge_count.toLocaleString()} edges
              {graph.truncated && (
                <span style={{ color: colors.risk.medium, marginLeft: 10 }}>
                  ⚠ Graph capped — some dependencies hidden
                </span>
              )}
            </div>
          )}
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          {/* Search */}
          <input
            placeholder="Search file…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              background: colors.surface2, border: `1px solid ${colors.border}`,
              borderRadius: 6, padding: "6px 10px", color: colors.text, fontSize: 12,
              fontFamily: "monospace", outline: "none", width: 180,
            }}
          />

          {/* View toggle */}
          <div style={{ display: "flex", borderRadius: 8, overflow: "hidden", border: `1px solid ${colors.border}` }}>
            {[true, false].map(mo => (
              <button
                key={String(mo)}
                onClick={() => { setModuleOnly(mo); }}
                style={{
                  fontSize: 12, padding: "6px 12px", cursor: "pointer",
                  border: "none",
                  background: moduleOnly === mo ? colors.accent : colors.surface2,
                  color: moduleOnly === mo ? "#fff" : colors.muted,
                  fontWeight: moduleOnly === mo ? 600 : 400,
                }}
              >
                {mo ? "Module view" : "Symbol view"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Graph canvas */}
      <div style={{ flex: 1, position: "relative" }}>
        {loading && (
          <div style={{
            position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
            background: `${colors.bg}cc`, zIndex: 10, fontSize: 14, color: colors.muted,
          }}>
            Building graph layout…
          </div>
        )}

        {error && (
          <div style={{
            position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
            flexDirection: "column", gap: 12,
          }}>
            <div style={{ fontSize: 14, color: colors.status.failed }}>{error}</div>
          </div>
        )}

        {!loading && !error && (
          <ReactFlow
            nodes={highlightedNodes}
            edges={edges}
            fitView
            minZoom={0.05}
            maxZoom={3}
            style={{ background: colors.bg }}
          >
            <Background color={colors.border} variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls style={{ background: colors.surface, border: `1px solid ${colors.border}` }} />
            <MiniMap
              style={{ background: colors.surface2 }}
              nodeColor={n => (n.data?.kind === "module" ? `${colors.accent}80` : "#8b5cf680")}
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
