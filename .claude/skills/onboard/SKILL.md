---
name: onboard
description: Use when the user asks to "set up the project", "get started", "onboard", "configure the app", "help me configure", or wants step-by-step guided setup of the PR-Review-Agent — covering prerequisites, GitHub PAT creation, smee.io webhook tunnel, GitHub webhook registration, .env configuration, Docker stack launch, and first repository registration. Detects what is already done and picks up from where setup left off.
---

# Onboard — PR-Review-Agent Setup Guide

This skill walks you through every step needed to get PR-Review-Agent running, from creating GitHub credentials to seeing your first automated PR review land. It checks the state of each step before doing anything, so it picks up from wherever you already are.

**Everything runs in Docker.** No local Python venv, no local Node — just Docker Compose bringing up the backend (FastAPI on :8001) and frontend (nginx-served React on :5173).

The steps in order:

1. Prerequisites — Docker, Git, Node (for the smee webhook relay)
2. GitHub Fine-Grained PAT — the token the agent uses to read PRs and post reviews
3. smee.io channel — a public URL that relays GitHub webhook events to localhost
4. GitHub webhook registration — tell GitHub to send PR events to smee
5. `.env` file — fill in credentials; validate with a script (values never shown)
6. Docker stack — `docker compose up --build -d` + health check
7. smee tunnel — start the local relay process
8. Register a repository — the app needs to know which repo to watch

---

## How to use this skill

Work through each step in order. For each step:
- Run the relevant check to see if it is already done
- If done: confirm it and move on
- If not done: give the user precise instructions, then verify before proceeding

Be conversational. This is a guided walk, not a command dump. Adjust commands for the user's OS (detect it in Step 0).

---

## Step 0: Detect OS and note the repo root

Check the platform before doing anything else. The key difference is command syntax and path separators.

```
Windows (PowerShell): $env:OS  →  "Windows_NT"
Unix/macOS (Bash):    uname -s  →  "Linux" or "Darwin"
```

Note the absolute path to the repo root — every subsequent relative path (`deployment/`, `.env`, scripts/) is relative to it. All commands assume you are in the repo root unless stated otherwise.

---

## Step 1: Prerequisites

Run the check script from the repo root:

```
python .claude/skills/onboard/scripts/check_prereqs.py
```

This checks: Docker installed, Docker daemon running, Docker Compose plugin, Git, Node 18+, npx.

### If Docker is not installed

> Install Docker Desktop from https://www.docker.com/products/docker-desktop/
> After installing, start it and wait for the whale icon in the system tray to show "Docker Desktop is running" before continuing.

### If Docker is installed but daemon is not running

> Open Docker Desktop. Wait for it to finish starting (the status bar at the bottom should say "Running"). Then re-run the check.

### If Docker Compose is missing

Docker Desktop bundles Compose as a plugin (`docker compose`). If it is missing, update Docker Desktop to the latest version.

### If Git is missing

> Install Git from https://git-scm.com/downloads.
> On Windows, use the default installer options. Make sure "Git from the command line" is selected so git ends up on your PATH.
> Restart your terminal after installing.

### If Node is missing or too old

> Install Node 18 or later from https://nodejs.org/en/download/
> On Windows, run the installer; on macOS/Linux, prefer nvm for version management.
> Restart your terminal after installing.

Once all checks pass, move on.

---

## Step 2: GitHub Fine-Grained PAT

The backend uses a Personal Access Token to:
- Clone repository code for call-graph analysis
- Read pull request diffs
- Post inline review comments back to GitHub

**The user must generate this token themselves.** Walk them through it:

1. Go to **GitHub → (your profile) → Settings** (at the bottom of the left sidebar)
2. Click **Developer settings** (very bottom of the left sidebar)
3. Click **Personal access tokens → Fine-grained tokens**
4. Click **Generate new token**
5. Fill in:
   - **Token name**: something descriptive like `pr-review-agent-local`
   - **Expiration**: choose a reasonable duration (90 days is fine for development)
   - **Resource owner**: your account (or the org that owns the repo)
   - **Repository access**: select "Only select repositories" and pick the repo(s) the agent will watch
6. Under **Repository permissions**, set:
   - **Contents**: Read-only ← needed to clone the repo for graph building
   - **Pull requests**: Read and write ← needed to read diffs and post reviews
   - **Webhooks**: Read and write ← needed only if you want the agent to self-register webhooks; optional for now
7. Click **Generate token**
8. **Copy the token immediately** — GitHub shows it only once

Tell the user:

> Save this token somewhere safe for a moment — you will paste it into `.env` as `GITHUB_TOKEN` in Step 5. Do not share it or commit it.

---

## Step 3: smee.io Channel

smee.io is a lightweight webhook relay purpose-built for local development. It creates a permanent public URL that forwards every GitHub webhook payload to your local machine.

**The user must create the channel in their browser** — there is no CLI for this:

> Open this URL in your browser:
> **https://smee.io/new**
>
> You will be immediately redirected to a unique channel URL that looks like:
> `https://smee.io/aBcDeFgHiJkLmNoP`
>
> Copy that URL. You will need it in two places:
> 1. The GitHub webhook configuration (Step 4) as the "Payload URL"
> 2. The smee client command (Step 7)
>
> Bookmark it or keep the tab open — the channel persists as long as you use it.

---

## Step 4: GitHub Webhook Registration

Now register the webhook on the target GitHub repository so GitHub sends PR events to your smee channel.

This is a manual step in the GitHub UI:

1. Go to the target repository on GitHub
2. Click **Settings** (tab at the top, requires admin/owner access on the repo)
3. In the left sidebar, click **Webhooks**
4. Click **Add webhook**
5. Fill in exactly:

   | Field | Value |
   |---|---|
   | **Payload URL** | The smee channel URL from Step 3 (e.g. `https://smee.io/aBcDeFgHiJkLmNoP`) |
   | **Content type** | `application/json` |
   | **Which events** | Select "Let me select individual events", then check **Pull requests** only |
   | **Active** | Checked |

6. Click **Add webhook**

GitHub immediately fires a `ping` event. You will see it appear in the smee channel page (the browser tab you left open). The backend will ignore it (it only processes `pull_request` events) but it confirms the plumbing works.

### Common issues

- **"Settings" tab is missing** — you need admin access to the repository to register webhooks.
- **Payload URL is your local IP** — that will not work from GitHub's servers. It must be the smee.io URL.

---

## Step 5: .env File

Now create the `.env` file and fill in all the credentials you have gathered.

### Create it

```
Windows (PowerShell):  Copy-Item .env.example .env
Unix:                  cp .env.example .env
```

### Fill it in

Open `.env` in any text editor. The fields to fill:

**LLM credentials — choose ONE path:**

_Azure OpenAI (if you have an Azure resource):_
```
AZURE_OPENAI_API_KEY=     ← paste your Azure OpenAI resource API key
AZURE_OPENAI_ENDPOINT=    ← paste your endpoint, e.g. https://myresource.openai.azure.com/
AZURE_OPENAI_MODEL=gpt-4o ← leave as-is unless your deployment name differs
AZURE_OPENAI_API_VERSION=2025-01-01-preview ← leave as-is
```

_Direct OpenAI (if you have an OpenAI API key instead):_
```
# Comment out the AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT lines
OPENAI_API_KEY=           ← uncomment this line and paste your sk-... key
AZURE_OPENAI_MODEL=gpt-4o ← leave as-is (controls model for both paths)
```

**GitHub credentials:**
```
GITHUB_TOKEN=             ← paste the PAT from Step 2
```

**Everything else** (`DATABASE_URL`, `CRITIC_CONFIDENCE_THRESHOLD`, etc.) has sensible defaults — leave them as-is for now.

### Validate it

Once saved, run the check script. **It never reads or displays your credential values** — it only checks that fields are present, non-empty, and not still set to placeholder values:

```
python .claude/skills/onboard/scripts/check_env.py
```

Work through any failures it reports. Common ones:

- **AZURE_OPENAI_ENDPOINT still has placeholder** — the default `https://your-resource.openai.azure.com/` was not replaced. Paste your actual Azure resource endpoint.
- **GITHUB_TOKEN is empty** — paste the PAT from Step 2.
- **No LLM path configured** — if using OpenAI direct, the `OPENAI_API_KEY=` line is commented out in `.env.example`. Uncomment it and fill in the value.

Once the script reports all green, move on.

---

## Step 6: Launch the Docker Stack

From the repo root:

```
docker compose -f deployment/docker-compose.yml up --build -d
```

What this does:
- Builds the backend image (Python 3.11-slim + git + all pip dependencies)
- Builds the frontend image (Node 20 compiles React → static files served by nginx)
- Starts both containers in the background
- Creates a named volume `backend-data` for the SQLite database (survives restarts)

The first build takes several minutes. Subsequent starts (without `--build`) are fast.

### Verify the stack is healthy

```
python .claude/skills/onboard/scripts/check_stack.py
```

This checks that both containers are running and that both HTTP endpoints respond:
- `GET http://localhost:8001/health` → `{"status":"ok"}`
- `GET http://localhost:5173` → HTML (nginx serving the React app)

### Debugging a failing stack

**View logs for both services:**
```
docker compose -f deployment/docker-compose.yml logs --tail=50
```

**View logs for one service:**
```
docker compose -f deployment/docker-compose.yml logs backend --tail=100
docker compose -f deployment/docker-compose.yml logs frontend --tail=50
```

**Common failures and fixes:**

| Symptom | Cause | Fix |
|---|---|---|
| Backend exits immediately | Bad `.env` value (e.g. malformed ENDPOINT URL) | Fix `.env`, then `docker compose -f deployment/docker-compose.yml up -d --force-recreate backend` |
| Backend health returns 500 | Settings crash at startup | Check backend logs for the traceback; usually a missing or malformed env var |
| Frontend container unhealthy | Backend not ready yet | Wait 10s and re-run check — frontend depends on backend starting |
| Port 8001 or 5173 already in use | Something else on the host using that port | `docker compose -f deployment/docker-compose.yml down` then find and stop the conflicting process |
| "image not found" or build error | Docker daemon lost connectivity during build | Restart Docker Desktop and retry |
| `.env` change not taking effect | Docker uses env values baked into the container at start | `docker compose -f deployment/docker-compose.yml up -d --force-recreate` after any `.env` edit |

---

## Step 7: Start the smee Tunnel

The stack is running, but GitHub cannot deliver webhooks to localhost without the relay. Start the smee client — it must stay running in a dedicated terminal for the duration of your session:

```
npx smee-client --url https://smee.io/<your-channel-id> --target http://localhost:8001/webhooks/github
```

Replace `<your-channel-id>` with the channel URL from Step 3.

Note the target path is `/webhooks/github` (not `/api/webhooks/github`, not `/`). That is the exact FastAPI route that handles incoming PR events.

Once running, the smee client logs each forwarded payload. Leave this terminal open.

### Verify the relay

In the GitHub webhook settings for your repo, click **Recent Deliveries**. The `ping` event from Step 4 should show a green checkmark. If it shows red, check:

- The smee client is running (the terminal should show activity)
- The channel URL in the webhook matches the one in your smee command exactly
- The target URL is reachable: `curl http://localhost:8001/health` or the PowerShell equivalent

### Debugging smee failures

- **"npx: command not found"** — Node was not installed correctly. Revisit Step 1.
- **Smee starts but shows no forwarded events** — trigger a ping by going to GitHub → repo → Settings → Webhooks → (your webhook) → Redeliver (ping). If still nothing, the Payload URL in GitHub is wrong.
- **Backend returns 422 or 500** — check backend logs. This is usually a payload parsing issue.

---

## Step 8: Register a Repository

The app needs to know which GitHub repository to analyze. Register it through the UI.

1. Open **http://localhost:5173/repos** in a browser
2. Click **Add repository**
3. Fill in:
   - **Repository full name**: `owner/repo` (e.g. `octocat/hello-world`)
   - **Clone URL**: `https://github.com/owner/repo.git`
   - **Default branch**: `main` (or `master`, or whatever the repo uses)
4. Click **Add**

The backend immediately enqueues an onboarding job. Watch the status update in the UI:

```
pending → cloning → building_graph → ready
```

This process:
- Clones the repository using the `GITHUB_TOKEN` from `.env`
- Runs Tree-sitter on every Python, JavaScript, and TypeScript file
- Builds a NetworkX call graph and stores it compressed in the database

Timing: 30 seconds for a small repo, several minutes for a large one.

### Via the API (if the UI is not accessible)

```
curl -X POST http://localhost:8001/api/repos \
  -H "Content-Type: application/json" \
  -d '{"full_name":"owner/repo","clone_url":"https://github.com/owner/repo.git","default_branch":"main"}'
```

### Debugging onboarding failures

- **Stuck at `cloning`** — the `GITHUB_TOKEN` does not have Contents:Read access to that repo, or `.env` was updated without restarting the backend. Restart: `docker compose -f deployment/docker-compose.yml up -d --force-recreate backend`
- **Fails immediately** — check backend logs: `docker compose -f deployment/docker-compose.yml logs backend --tail=50`. The most common cause is an invalid clone URL or insufficient token permissions.
- **409 "already registered"** — the repo is in the database already. Use the Refresh button in the UI or `POST /api/repos/{repo_id}/refresh` to rebuild its graph.
- **Only Python/JS/TS analyzed** — other languages are reviewed as raw diff text without call-graph context. This is a known limitation documented in `LIMITATIONS.md`.

---

## Completion

Setup is complete when:

1. `python .claude/skills/onboard/scripts/check_stack.py` reports all green
2. At least one repository shows **onboarding_status: ready** in `http://localhost:5173/repos`
3. The smee client is running and the GitHub webhook's Recent Deliveries shows green

### End-to-end test

Open or update a pull request on the registered repository. Within a few seconds:

- The smee terminal logs a forwarded `POST`
- The backend logs `received pull_request event`
- `http://localhost:5173` shows a new review run progressing through phases:
  `ingestion → diff_analysis → blast_radius → context_retrieval → synthesis → review → critic → publish`
- Once `publish` completes, the PR on GitHub has inline review comments and a summary

### What to explore next

- **Dashboard** — `http://localhost:5173` — all review runs, phase timelines, and finding cards with confidence scores
- **API docs** — `http://localhost:8001/docs` — Swagger UI for every endpoint; useful for manually triggering calls during development
- **Repo graph** — `http://localhost:5173/repos` → click Graph on any ready repo to explore the call graph the blast-radius engine built
- **Local pipeline demo** — type `/local-pipeline-demo` to run the full 7-phase pipeline against a fixture diff with no webhook required
- **Manual review checklist** — type `/review-checklist` to run the same 7-category checklist on any diff you point it at

### Stopping the stack

```
docker compose -f deployment/docker-compose.yml down
```

The SQLite database is in a named volume and survives `down`. To wipe the database too:
```
docker compose -f deployment/docker-compose.yml down -v
```
