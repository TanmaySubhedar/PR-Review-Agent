export interface ReviewRun {
  id: string;
  repo_full_name: string;
  pr_number: number;
  pr_url: string;
  title: string;
  head_sha: string;
  base_sha: string;
  status: "received" | "queued" | "analyzing" | "done" | "failed";
  risk_level: "low" | "medium" | "high" | null;
  error: string | null;
  change_summary: string | null;
  suggested_pr_description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Repo {
  id: string;
  full_name: string;
  clone_url: string;
  default_branch: string;
  onboarding_status: "pending" | "cloning" | "building_graph" | "ready" | "failed";
  onboarding_error: string | null;
  graph_node_count: number | null;
  graph_edge_count: number | null;
  graph_truncated: boolean;
  created_at: string;
  updated_at: string;
}

export interface RepoRegisterRequest {
  full_name: string;
  clone_url: string;
  default_branch: string;
}

export interface GraphNode {
  id: string;
  kind: "module" | "symbol";
  file?: string;
  name?: string;
  symbol_type?: string;
  start_line?: number;
}

export interface GraphLink {
  source: string;
  target: string;
  kind: "imports" | "contains" | "calls" | string;
}

export interface GraphResponse {
  repo_id: string;
  full_name: string;
  node_count: number;
  edge_count: number;
  truncated: boolean;
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface Finding {
  id: string;
  review_run_id: string;
  file: string;
  line: number | null;
  dimension: "correctness" | "architecture" | "testing" | "maintainability" | "security" | "performance" | "logging";
  finding: string;
  evidence: string;
  severity: "info" | "minor" | "major" | "blocking";
  confidence: number;
  published: boolean;
  discarded: boolean;
}

export type PhaseStatus = "pending" | "running" | "done" | "failed";

export interface PhaseLog {
  id: string;
  review_run_id: string;
  phase:
    | "ingestion"
    | "diff_analysis"
    | "blast_radius"
    | "context_retrieval"
    | "synthesis"
    | "review"
    | "critic"
    | "publish";
  status: PhaseStatus;
  detail: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}
