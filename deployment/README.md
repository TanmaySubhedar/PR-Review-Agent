# Deployment (local Docker)

Brings up the backend and frontend together in containers. Uses local
Docker rather than Azure for this submission (explicitly allowed - "Azure
OR local Docker" - and faster to demo reliably).

## Prerequisites

- Docker + Docker Compose
- `.env` populated at the **repo root** (not inside `backend/` or
  `deployment/`) with real Azure OpenAI credentials, `GITHUB_TOKEN`, and
  `GITHUB_WEBHOOK_SECRET` - see `.env.example`.

## Run it

```
cd deployment
docker compose up --build
```

- Dashboard: http://localhost:5173
- Backend health check: http://localhost:8001/health
- Backend API docs (Swagger UI): http://localhost:8001/docs

The SQLite database persists in a named Docker volume (`backend-data`), not
inside the container's writable layer, so `docker compose down` (without
`-v`) keeps your review history across restarts.

## What this does and doesn't solve

Docker solves "run both services together with one command, the same way
every time." It does **not** solve GitHub needing a public URL to deliver
webhooks to - that's a separate, orthogonal problem. To receive real PR
events against a containerized backend, point a tunnel (smee.io
recommended - see the root `README.md`'s troubleshooting notes on why we
moved off ngrok) at `http://localhost:8001/webhooks/github`, same as you
would for the non-containerized backend.

## Stopping

```
docker compose down
```

Add `-v` to also delete the persisted SQLite volume.
