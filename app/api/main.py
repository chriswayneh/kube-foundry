from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from psycopg.rows import dict_row


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("method", "path", "status_code", "duration_ms", "job_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
logger = logging.getLogger("kube_foundry.api")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "path"])

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'complete', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def dependency_checks_enabled() -> bool:
    return os.getenv("DEPENDENCY_CHECKS_ENABLED", "false").lower() == "true"


def db_connection() -> psycopg.Connection[Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(database_url, connect_timeout=3, row_factory=dict_row)


def redis_connection() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is required")
    return redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)


def ensure_schema() -> None:
    with db_connection() as connection:
        connection.execute(SCHEMA)
        connection.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if dependency_checks_enabled():
        ensure_schema()
    logger.info("api_started")
    yield
    logger.info("api_stopped")


app = FastAPI(title="kube-foundry API", version="0.1.0", lifespan=lifespan)


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Item(ItemCreate):
    id: int
    created_at: datetime


class Job(BaseModel):
    id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime


@app.middleware("http")
async def observe_request(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    LATENCY.labels(request.method, path).observe(duration)
    logger.info(
        "request_complete",
        extra={
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
        },
    )
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    if os.getenv("APP_CONFIGURED", "false").lower() != "true":
        raise HTTPException(status_code=503, detail={"configuration": "failed"})
    if not dependency_checks_enabled():
        return {"status": "ready", "dependencies": "disabled-for-phase-2"}

    checks: dict[str, str] = {}
    try:
        with db_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        checks["postgres"] = "ok"
    except Exception:
        logger.exception("postgres_readiness_failed")
        checks["postgres"] = "failed"

    try:
        redis_connection().ping()
        checks["redis"] = "ok"
    except Exception:
        logger.exception("redis_readiness_failed")
        checks["redis"] = "failed"

    if "failed" in checks.values():
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "dependencies": checks}


@app.get("/api/items", response_model=list[Item])
def list_items() -> list[dict[str, Any]]:
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, created_at FROM items ORDER BY id"
        ).fetchall()
    return list(rows)


@app.post("/api/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate) -> dict[str, Any]:
    with db_connection() as connection:
        row = connection.execute(
            "INSERT INTO items (name) VALUES (%s) RETURNING id, name, created_at",
            (item.name,),
        ).fetchone()
        connection.commit()
    if row is None:
        raise HTTPException(status_code=500, detail="item insert returned no row")
    return row


@app.post("/api/jobs", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
def create_job() -> dict[str, Any]:
    job_id = uuid.uuid4()
    with db_connection() as connection:
        row = connection.execute(
            "INSERT INTO jobs (id, status) VALUES (%s, 'pending') "
            "RETURNING id, status, created_at, updated_at",
            (job_id,),
        ).fetchone()
        connection.commit()
    try:
        redis_connection().rpush("jobs", str(job_id))
    except Exception as exc:
        with db_connection() as connection:
            connection.execute(
                "UPDATE jobs SET status = 'failed', updated_at = NOW() WHERE id = %s",
                (job_id,),
            )
            connection.commit()
        raise HTTPException(status_code=503, detail="queue unavailable") from exc
    logger.info("job_queued", extra={"job_id": str(job_id)})
    if row is None:
        raise HTTPException(status_code=500, detail="job insert returned no row")
    return row


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: uuid.UUID) -> dict[str, Any]:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT id, status, created_at, updated_at FROM jobs WHERE id = %s",
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
