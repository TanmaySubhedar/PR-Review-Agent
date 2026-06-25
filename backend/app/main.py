from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, reviews, webhooks
from app.db import init_db

app = FastAPI(title="PR Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(reviews.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
