import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getFindings, getPhases, getReview } from "../api/client";
import { FindingCard } from "../components/FindingCard";
import { PipelinePhaseTimeline } from "../components/PipelinePhaseTimeline";
import type { Finding, PhaseLog, ReviewRun } from "../types";

export function ReviewDetailPage() {
  const { reviewRunId } = useParams<{ reviewRunId: string }>();
  const [run, setRun] = useState<ReviewRun | null>(null);
  const [phases, setPhases] = useState<PhaseLog[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reviewRunId) return;
    const id = reviewRunId;
    let cancelled = false;

    async function load() {
      try {
        const [runData, phaseData, findingData] = await Promise.all([
          getReview(id),
          getPhases(id),
          getFindings(id),
        ]);
        if (cancelled) return;
        setRun(runData);
        setPhases(phaseData);
        setFindings(findingData);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    }

    load();
    const interval = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [reviewRunId]);

  if (error) return <p style={{ color: "#cf222e" }}>Failed to load review: {error}</p>;
  if (!run) return <p>Loading...</p>;

  return (
    <div>
      <Link to="/">&larr; All reviews</Link>
      <h1>
        #{run.pr_number} {run.title}
      </h1>
      <p>
        <a href={run.pr_url} target="_blank" rel="noreferrer">
          {run.repo_full_name}
        </a>{" "}
        · status: {run.status} · risk: {run.risk_level ?? "-"}
      </p>
      {run.error && <p style={{ color: "#cf222e" }}>Error: {run.error}</p>}

      <PipelinePhaseTimeline phases={phases} />

      <h2>Findings ({findings.length})</h2>
      {findings.length === 0 && <p>No findings yet.</p>}
      {findings.map((finding) => (
        <FindingCard key={finding.id} finding={finding} />
      ))}
    </div>
  );
}
