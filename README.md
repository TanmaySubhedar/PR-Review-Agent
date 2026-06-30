# Sentinel PR — Automated PR Review Agent

An autonomous, repository-aware PR review agent. On every GitHub pull request
event it: analyzes the diff, maps the blast radius of the change across the
whole repo (callers, callees, tests, docs), synthesizes that into repository
context, asks Azure OpenAI to review the diff across a 7-category checklist
(security, correctness, performance, logging, tests, readability, breaking
changes), critiques each finding before trusting it, and posts the surviving
findings — plus a structured "What changed" + "Issues found" summary and a
suggested PR description — back to the PR as a GitHub review.

Beyond PR review, the system also builds and persists a full call-graph diagram
for every registered repository, visualizes it interactively, and lets you ask
a two-step LLM chatbot questions grounded in the actual source code.

See [DESIGN.md](DESIGN.md) for the design rationale, [ARCHITECTURE.md](ARCHITECTURE.md)
for the exact execution trace, and [LIMITATIONS.md](LIMITATIONS.md) for known
gaps. Three Claude Code Skills ship with this repo:
- `.claude/skills/review-checklist` — run the 7-category checklist manually on any diff
- `.claude/skills/local-pipeline-demo` — run the full pipeline against a fixture diff with no webhook
- `.claude/skills/onboard` — guided 8-step setup from zero to first automated review

```
backend/      FastAPI app + review pipeline + repo onboarding (Python)
frontend/     React + Vite dashboard (reviews, graph, repo chatbot)
prompts/      LLM system prompts (review agent, critic agent)
deployment/   Docker Compose + nginx config
evals/        Eval fixtures and test datasets
```

---

## Quickstart — Docker (recommended)

The fastest way to run everything with no local Python/Node setup:

```
cp .env.example .env
# fill in .env (see "Configure secrets" below)
docker compose -f deployment/docker-compose.yml up --build -d
```

- Frontend dashboard: `http://localhost:5173`
- Backend API + Swagger: `http://localhost:8001/docs`
- Health check: `http://localhost:8001/health` → `{"status":"ok"}`

The first build takes a few minutes. Subsequent starts (without `--build`) are fast.
The SQLite database is in a named volume (`backend-data`) and survives restarts.

Or use the guided setup skill from Claude Code:

```
/onboard
```

---

## Configure secrets

Copy `.env.example` to `.env` and fill it in:

| Variable | Where to get it |
|---|---|
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_MODEL` / `AZURE_OPENAI_API_VERSION` | Your Azure OpenAI resource |
| `GITHUB_TOKEN` | A GitHub fine-grained personal access token (see below) |
| `GITHUB_WEBHOOK_SECRET` | Any random string — e.g. `python -c "import secrets; print(secrets.token_hex(20))"` |

`.env` is gitignored — never commit it.

**OpenAI direct** (instead of Azure): comment out the `AZURE_OPENAI_*` lines and set `OPENAI_API_KEY`.

### GitHub token permissions

Fine-grained PAT (GitHub → Settings → Developer settings → Fine-grained personal access tokens),
scoped to the repo(s) you want reviewed:

- **Contents**: Read-only (clone + file fetch for graph and chatbot)
- **Pull requests**: Read and write (read diffs, post reviews)
- **Webhooks**: Read and write (optional — only if you register webhooks via the API)

---

## Register a repository

After the stack is running, open `http://localhost:5173/repos` and click
**+ Register Repository**. Enter:

- **Repository** (`owner/repo` format — e.g. `TanmaySubhedar/PR-Review-Agent`)
- **Clone URL** (`https://github.com/owner/repo.git`)
- **Default branch** (`main`)

The backend clones the repo, runs Tree-sitter on every Python/JS/TS file, builds
a NetworkX call graph, and stores it compressed in the database. Status progresses
`pending → cloning → building_graph → ready` (live in the UI). Once ready:

- **View Graph** — interactive React Flow visualization of the call graph
- **Ask AI** — two-step LLM chatbot grounded in the actual repo source code
- Click any graph node to pre-fill the chatbot with a question about that file or function

---

## Get GitHub webhook events to your machine

GitHub needs a public URL to deliver webhook events to. For local development, use
**smee.io** (purpose-built for relaying GitHub webhooks):

1. Open `https://smee.io/new` in a browser and copy the channel URL
2. Run the relay (keep this terminal open):
   ```
   npx smee-client --url https://smee.io/<your-channel-id> --target http://localhost:8001/webhooks/github
   ```

Then register the webhook: GitHub repo → **Settings → Webhooks → Add webhook**:
- **Payload URL**: your smee channel URL
- **Content type**: `application/json`
- **Secret**: your `GITHUB_WEBHOOK_SECRET`
- **Events**: Pull requests only

---

## Try it

Open or update a pull request on the registered repo. You should see:

- The run appear at `http://localhost:5173` progressing through phases:
  `ingestion → diff_analysis → blast_radius → context_retrieval → synthesis → review → critic → publish`
- A real review posted on the PR with a **"What changed"** section (features introduced + file-by-file bullets), an **"Issues found"** section with severity icons, and a collapsible blast-radius summary

---

## Manual / local development setup

If you prefer running without Docker:

**Backend:**
```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
uvicorn app.main:app --port 8001
```

Run tests (no live credentials needed — everything mocked/fixtured):
```
pytest
```

**Frontend:**
```
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`. It proxies `/api/*` to `http://127.0.0.1:8001`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No webhook deliveries | Webhook not configured or wrong repo | Webhooks are per-repo; check Settings → Webhooks |
| Non-200 delivery response | smee client not running or wrong port | Restart smee client; confirm `--target` port matches backend |
| Run fails with "repository not found" | Token missing access or `.env` not reloaded | Token needs Contents:Read on that repo; restart backend after `.env` changes |
| Clone step fails for private repo | `GITHUB_TOKEN` not set or insufficient | Set token with Contents:Read; backend auto-injects it into the clone URL |
| Repo chatbot: "could not retrieve" | Wrong `owner/repo` format registered | Use `owner/repo` (not just `owner`); re-register if needed |
| Only Python/JS/TS understood | Tree-sitter grammar limitation | Other languages still get reviewed from raw diff; no call-graph context |
| Chat/review slow in Docker | Two LLM calls take 30–60 s | nginx has 120 s read timeout; both calls should complete within that |
