import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getRepo, getRepoGraph } from "../api/client";
import { RepoChatPanel } from "../components/RepoChatPanel";
import { colors } from "../theme";
import type { ChatMessage, GraphResponse, Repo } from "../types";

// ── Layout via dagre ──────────────────────────────────────────────────────────

const NODE_W = 180;
const NODE_H = 40;

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const connectedIds = new Set<string>();
  edges.forEach(e => { connectedIds.add(e.source); connectedIds.add(e.target); });

  const connected = nodes.filter(n => connectedIds.has(n.id));
  const isolated  = nodes.filter(n => !connectedIds.has(n.id));

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

// ── Custom node with hover tooltip ────────────────────────────────────────────

function RepoNode({ data }: NodeProps) {
  const isModule = data.kind === "module";
  return (
    <>
      <Handle type="target" position={Position.Top}
        style={{ opacity: 0, pointerEvents: "none", width: 4, height: 4 }} />
      <div
        title={String(data.fullLabel)}
        style={{
          fontSize: 12, fontFamily: "monospace",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          color: isModule ? colors.text : "#c4b5fd",
          maxWidth: NODE_W - 24,
        }}
      >
        {String(data.label)}
      </div>
      <Handle type="source" position={Position.Bottom}
        style={{ opacity: 0, pointerEvents: "none", width: 4, height: 4 }} />
    </>
  );
}

const NODE_TYPES = { repo: RepoNode };

// ── API → React Flow conversion ───────────────────────────────────────────────

function toFlowGraph(data: GraphResponse): { nodes: Node[]; edges: Edge[] } {
  const edgeColor: Record<string, string> = {
    imports: colors.accent,
    calls: "#8b5cf6",
    contains: colors.muted,
  };

  const rawNodes: Node[] = data.nodes.map(n => {
    // Module nodes: show just the filename.  Symbol nodes: show the symbol name.
    const label = n.kind === "module"
      ? (n.file?.split("/").pop() ?? n.id)
      : (n.name ?? n.file?.split("/").pop() ?? n.id);
    // Full tooltip: file path for modules, "file → symbol" for symbols.
    const fullLabel = n.kind === "module"
      ? (n.file ?? n.id)
      : (n.name && n.file ? `${n.file} → ${n.name}` : n.id);

    return {
      id: n.id,
      type: "repo",
      data: { label, fullLabel, kind: n.kind, name: n.name, file: n.file },
      position: { x: 0, y: 0 },
      style: {
        background: n.kind === "module" ? colors.surface2 : "#1e1b2e",
        border: `1px solid ${n.kind === "module" ? `${colors.accent}60` : "#8b5cf660"}`,
        borderRadius: 8,
        padding: "6px 12px",
        width: NODE_W,
        cursor: "pointer",
      },
    };
  });

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

  // chat state
  const [chatOpen, setChatOpen]         = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput]       = useState("");

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

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    const isModule = node.data.kind === "module";
    const question = isModule
      ? `Explain the ${node.data.fullLabel} file`
      : `What does the ${String(node.data.name)} function do in ${String(node.data.file)}?`;
    setChatInput(question);
    setChatOpen(true);
  }, []);

  const openChat = () => {
    setChatInput("");
    setChatOpen(true);
  };

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

          {/* Ask AI button */}
          <button
            onClick={openChat}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: chatOpen ? "rgba(16,185,129,0.2)" : "rgba(16,185,129,0.1)",
              border: `1px solid ${chatOpen ? "#10b981" : "rgba(16,185,129,0.3)"}`,
              borderRadius: 8, padding: "6px 14px",
              color: "#10b981", fontSize: 12, fontWeight: 600, cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(16,185,129,0.2)"; }}
            onMouseLeave={e => {
              if (!chatOpen) (e.currentTarget as HTMLElement).style.background = "rgba(16,185,129,0.1)";
            }}
          >
            ⬡ Ask AI
          </button>
        </div>
      </div>

      {/* Hint banner when graph is loaded */}
      {!loading && !error && nodes.length > 0 && (
        <div style={{
          padding: "6px 24px", fontSize: 11, color: colors.muted,
          borderBottom: `1px solid ${colors.border}`, background: colors.surface,
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <span style={{ color: "#10b981" }}>⬡</span>
          Click any node to ask Repo AI about that file
        </div>
      )}

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
            nodeTypes={NODE_TYPES}
            onNodeClick={onNodeClick}
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

      {/* Chat panel */}
      {chatOpen && repo && (
        <RepoChatPanel
          repoId={repo.id}
          repoName={repo.full_name}
          onClose={() => setChatOpen(false)}
          messages={chatMessages}
          onMessages={setChatMessages}
          initialInput={chatInput}
        />
      )}
    </div>
  );
}
