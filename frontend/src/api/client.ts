import type { Finding, PhaseLog, ReviewRun } from "../types";

const REVIEWS_URL = "/api/reviews";
const CHAT_URL = "/api/chat";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const listReviews = (): Promise<ReviewRun[]> => getJSON(REVIEWS_URL);
export const getReview = (id: string): Promise<ReviewRun> => getJSON(`${REVIEWS_URL}/${id}`);
export const getFindings = (id: string): Promise<Finding[]> => getJSON(`${REVIEWS_URL}/${id}/findings`);
export const getPhases = (id: string): Promise<PhaseLog[]> => getJSON(`${REVIEWS_URL}/${id}/phases`);

export const sendChat = (message: string, reviewRunId?: string): Promise<{ response: string }> =>
  postJSON(CHAT_URL, { message, review_run_id: reviewRunId ?? null });
