import type { Finding, GraphResponse, PhaseLog, Repo, RepoRegisterRequest, ReviewRun } from "../types";

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

const REPOS_URL = "/api/repos";

export const listRepos = (): Promise<Repo[]> => getJSON(REPOS_URL);
export const getRepo = (id: string): Promise<Repo> => getJSON(`${REPOS_URL}/${id}`);
export const registerRepo = (body: RepoRegisterRequest): Promise<Repo> => postJSON(REPOS_URL, body);
export const refreshRepo = (id: string): Promise<Repo> => postJSON(`${REPOS_URL}/${id}/refresh`, {});
export const getRepoGraph = (id: string, moduleOnly = true): Promise<GraphResponse> =>
  getJSON(`${REPOS_URL}/${id}/graph?module_only=${moduleOnly}`);

async function deleteJSON(url: string): Promise<void> {
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`${url} → ${res.status}`);
}
export const deleteRepo = (id: string): Promise<void> => deleteJSON(`${REPOS_URL}/${id}`);

export const sendRepoChat = (repoId: string, message: string): Promise<{ response: string }> =>
  postJSON(`${REPOS_URL}/${repoId}/chat`, { message });
