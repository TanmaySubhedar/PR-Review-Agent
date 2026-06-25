export interface ReviewRun {
  id: string;
  repo_full_name: string;
  pr_number: number;
  pr_url: string;
  title: string;
  head_sha: string;
  base_sha: string;
  status: "received" | "analyzing" | "done" | "failed";
  risk_level: "low" | "medium" | "high" | null;
  error: string | null;
  change_summary: string | null;
  suggested_pr_description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Finding {
  id: string;
  review_run_id: string;
  file: string;
  line: number | null;
  dimension:
    | "correctness"
    | "architecture"
    | "testing"
    | "maintainability"
    | "security"
    | "performance"
    | "logging";
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
