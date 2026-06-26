# PR Analyzer

An autonomous, repository-aware PR review agent. On every GitHub pull request
event it: analyzes the diff, maps the blast radius of the change across the
whole repo (callers, callees, tests, docs), synthesizes that into repository
context, asks Azure OpenAI to review the diff across a 7-category checklist
(security, correctness, performance, logging, tests, readability, breaking
changes), critiques each finding before trusting it, and posts the surviving
findings - plus a change summary and a suggested PR description - back to
the PR as a GitHub review.

See [DESIGN.md](DESIGN.md) for the design rationale, [ARCHITECTURE.md](ARCHITECTURE.md)
for the exact execution trace, and [LIMITATIONS.md](LIMITATIONS.md) for known
gaps. Two Claude Code Skills ship with this repo: `.claude/skills/review-checklist`
(run the same checklist manually on any diff) and `.claude/skills/local-pipeline-demo`
(run the full pipeline against a fixture diff with no webhook needed).

```
backend/   FastAPI app + the review pipeline (Python)
frontend/  React + Vite dashboard (view runs, findings, phase status)
```

## Prerequisites

- Python 3.11+
- Node 18+
- Git
- A GitHub account with a repo to point this at
- An Azure OpenAI resource (endpoint + API key + a `gpt-4o`-class deployment)

## 1. Configure secrets

Copy the example env file at the project root and fill it in:

```
cp .env.example .env
```

| Variable | Where to get it |
|---|---|
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_MODEL` / `AZURE_OPENAI_API_VERSION` | Your Azure OpenAI resource |
| `GITHUB_TOKEN` | A GitHub fine-grained personal access token (see below) |
| `GITHUB_WEBHOOK_SECRET` | Any random string - e.g. `python -c "import secrets; print(secrets.token_hex(20))"` |

`.env` is gitignored - never commit it.

### GitHub token permissions

Create a fine-grained PAT (GitHub → Settings → Developer settings →
Fine-grained personal access tokens) scoped to the repo(s) you want
reviewed, with:

- **Contents**: Read-only (the agent clones/reads code, never writes it)
- **Pull requests**: Read and write (to read diffs and post reviews)
- **Webhooks**: Read and write (only needed if you want to manage webhooks
  via the GitHub API instead of the web UI)

## 2. Backend setup

```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # macOS/Linux
pip install -e ".[dev]"
```

Run the tests (no live credentials needed - everything is mocked/fixtured):

```
pytest
```

Start the server:

```
uvicorn app.main:app --port 8001
```

- `GET http://127.0.0.1:8001/health` should return `{"status":"ok"}`
- Swagger UI: `http://127.0.0.1:8001/docs`

## 3. Frontend setup

```
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. It proxies `/api/*` to `http://127.0.0.1:8001`
(see `frontend/vite.config.ts` if you change the backend's port).

## 4. Get GitHub webhook events to your machine

GitHub needs a public URL to deliver webhook events to. For local
development, use **smee.io** (purpose-built for relaying GitHub webhooks -
simpler and more reliable for this than a general-purpose tunnel):

1. Get a channel: open `https://smee.io/new` in a browser, or just visit it
   with curl (`curl -s -o /dev/null -w '%{redirect_url}' https://smee.io/new`)
   and copy the channel URL it redirects to.
2. Run the client, pointed at your running backend:
   ```
   npx smee-client --url https://smee.io/<your-channel-id> --target http://127.0.0.1:8001/webhooks/github
   ```
   Leave this running - it forwards every payload GitHub sends to your
   local server.

## 5. Add the webhook on your repo

GitHub repo → **Settings → Webhooks → Add webhook**:

- **Payload URL**: your smee channel URL (e.g. `https://smee.io/<your-channel-id>`)
- **Content type**: `application/json`
- **Secret**: the `GITHUB_WEBHOOK_SECRET` value from your `.env`
- **Which events**: select individual events → **Pull requests** only
- Active → Add webhook

## 6. Try it

Open or update a pull request on that repo. You should see:

- A request logged in the smee client's terminal
- A new run appear at `GET http://127.0.0.1:8001/api/reviews` (or in the dashboard)
- The run progress through phases (`ingestion → diff_analysis → blast_radius
  → context_retrieval → synthesis → review → critic → publish`)
- A real review posted on the PR once `publish` completes

## Troubleshooting

- **Webhook shows no deliveries at all**: the webhook itself isn't
  configured, or you're checking the wrong repo - webhooks are per-repo,
  not granted via the token.
- **Delivery shows a non-200 response**: check the smee client is still
  running and the `--target` port matches your running backend.
- **Run never appears / fails immediately with a 404 "repository not
  found"**: the token doesn't have access to that repo, or you edited
  `.env` without restarting the backend - env vars are loaded once at
  process startup, so any `.env` change requires a restart to take effect.
- **Run fails on the blast-radius/clone step for a private repo**: make
  sure `GITHUB_TOKEN` is set - the clone URL is automatically authenticated
  with it (see `app/pipeline/blast_radius/workspace.py`).
- **Only Python, JS, TS, and TSX are understood** by the diff-analysis and
  blast-radius engine (Tree-sitter based). Other languages still get a
  review of the raw diff, just without repository-context grounding.

## Alternative: run with Docker

`cd deployment && docker compose up --build` brings up both services
together (dashboard on :5173, backend on :8001) without a local Python/Node
setup. See [deployment/README.md](deployment/README.md) - note Docker
doesn't solve the webhook-tunnel requirement in step 4 above, it's
orthogonal.
