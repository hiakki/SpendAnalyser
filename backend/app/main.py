from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    accounts,
    admin,
    analytics,
    anomalies,
    budgets,
    categories,
    export,
    recurring,
    rules,
    transactions,
    upload,
)
from .categorize.seed import seed_categories_and_rules
from .config import get_settings
from .db import SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(title="Spend Analyser", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cfg.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        with SessionLocal() as db:
            seed_categories_and_rules(db)
        log.info("ready. db=%s llm=%s provider=%s", cfg.db_url, cfg.llm_enabled, cfg.llm_provider)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    app.include_router(accounts.router)
    app.include_router(categories.router)
    app.include_router(rules.router)
    app.include_router(upload.router)
    app.include_router(transactions.router)
    app.include_router(analytics.router)
    app.include_router(budgets.router)
    app.include_router(recurring.router)
    app.include_router(anomalies.router)
    app.include_router(export.router)
    app.include_router(admin.router)
    return app


app = create_app()
