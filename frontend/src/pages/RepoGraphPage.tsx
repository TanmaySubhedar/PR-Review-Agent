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

const NODE_W = 180;
const NODE_H = 40;

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  // Split: nodes that appear in at least one edge vs truly isolated nodes.
  // Dagre stacks all isolated nodes in a single column which looks terrible
  // for sparse graphs (e.g. module view with only a few import edges).
  const connectedIds = new Set<string>();
  edges.forEach(e => { connectedIds.add(e.source); connectedIds.add(e.target); });

  const connected = nodes.filter(n => connectedIds.has(n.id));
  const isolated  = nodes.filter(n => !connectedIds.has(n.id));

  // Dagre layout for connected subgraph
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", ranksep: 100, nodesep: 60, marginx: 40, marginy: 40 });

  connected.forEach(n => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach(e => {
    if (connectedIds.has(e.source) && connectedIds.has(e.target)) {
      g.setEdge(e.source, e.target);
    }
  });
  if (connected.length > 0) dagre.layout(g);

  const laidOutConnected = connected.map(n => {
    const pos = g.node(n.id);
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } };
  });

  // Grid layout for isolated nodes — placed to the right of the connected graph
  const graphRight = laidOutConnected.length > 0
    ? Math.max(...laidOutConnected.map(n => n.position.x)) + NODE_W + 80
    : 0;
  const COLS = Math.max(1, Math.ceil(Math.sqrt(isolated.length)));
  const CELL_W = NODE_W + 24;
  const CELL_H = NODE_H + 20;

  const laidOutIsolated = isolated.map((n, i) => ({
    ...n,
    position: {
      x: graphRight + (i % COLS) * CELL_W,
      y: Math.floor(i / COLS) * CELL_H + 40,
    },
  }));

  return [...laidOutConnected, ...laidOutIsolated];
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
      fontSize: 12,
      fontFamily: "monospace",
      padding: "6px 12px",
      width: NODE_W,
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
