import type { Finding, PhaseLog, ReviewRun } from "../types";

const BASE_URL = "/api/reviews";

async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listReviews(): Promise<ReviewRun[]> {
  return getJSON(BASE_URL);
}

export function getReview(reviewRunId: string): Promise<ReviewRun> {
  return getJSON(`${BASE_URL}/${reviewRunId}`);
}

export function getFindings(reviewRunId: string): Promise<Finding[]> {
  return getJSON(`${BASE_URL}/${reviewRunId}/findings`);
}

export function getPhases(reviewRunId: string): Promise<PhaseLog[]> {
  return getJSON(`${BASE_URL}/${reviewRunId}/phases`);
}
