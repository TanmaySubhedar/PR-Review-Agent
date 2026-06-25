import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReviews } from "../api/client";
import { colors } from "../theme";
import type { ReviewRun } from "../types";

export function ReviewListPage() {
  const [reviews, setReviews] = useState<ReviewRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await listReviews();
        if (!cancelled) setReviews(data);
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
  }, []);

  if (error) return <p style={{ color: "#cf222e" }}>Failed to load reviews: {error}</p>;

  return (
    <div>
      <h1>PR Reviews</h1>
      {reviews.length === 0 && <p>No review runs yet - they appear here as PR webhooks arrive.</p>}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #d0d7de" }}>
            <th style={{ padding: 8 }}>PR</th>
            <th style={{ padding: 8 }}>Repo</th>
            <th style={{ padding: 8 }}>Status</th>
            <th style={{ padding: 8 }}>Risk</th>
            <th style={{ padding: 8 }}>Updated</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((run) => (
            <tr key={run.id} style={{ borderBottom: "1px solid #eaeef2" }}>
              <td style={{ padding: 8 }}>
                <Link to={`/reviews/${run.id}`}>
                  #{run.pr_number} {run.title}
                </Link>
              </td>
              <td style={{ padding: 8 }}>{run.repo_full_name}</td>
              <td style={{ padding: 8 }}>{run.status}</td>
              <td style={{ padding: 8, color: run.risk_level ? colors.risk[run.risk_level] : undefined }}>
                {run.risk_level ?? "-"}
              </td>
              <td style={{ padding: 8 }}>{new Date(run.updated_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
