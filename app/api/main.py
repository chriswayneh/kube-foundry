from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from psycopg.conninfo import make_conninfo
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


def required_env(name: str, fallback: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required when {fallback} is not set")
    return value


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    return make_conninfo(
        host=os.getenv("PGHOST", "postgres"),
        port=os.getenv("PGPORT", "5432"),
        dbname=required_env("POSTGRES_DB", "DATABASE_URL"),
        user=required_env("POSTGRES_USER", "DATABASE_URL"),
        password=required_env("POSTGRES_PASSWORD", "DATABASE_URL"),
    )


def redis_url() -> str:
    value = os.getenv("REDIS_URL")
    if value:
        return value
    password = quote(required_env("REDIS_PASSWORD", "REDIS_URL"), safe="")
    return f"redis://:{password}@{os.getenv('REDIS_HOST', 'redis')}:6379/0"


DEFAULT_PG_OPTIONS = "-c statement_timeout=5000 -c lock_timeout=2000"


def pg_options() -> str:
    """Server options for every connection (statement and lock timeouts)."""
    return os.getenv("PG_OPTIONS", DEFAULT_PG_OPTIONS)


def db_connection() -> psycopg.Connection[Any]:
    return psycopg.connect(
        database_url(), connect_timeout=3, row_factory=dict_row, options=pg_options()
    )


def redis_connection() -> redis.Redis:
    return redis.from_url(redis_url(), socket_connect_timeout=3, socket_timeout=3, decode_responses=True)


def ensure_schema() -> None:
    with db_connection() as connection:
        connection.execute(SCHEMA)
        connection.commit()


DISPATCH_INTERVAL_SECONDS = float(os.getenv("JOB_DISPATCH_INTERVAL_SECONDS", "30"))


async def dispatch_loop(interval: float = DISPATCH_INTERVAL_SECONDS) -> None:
    """Background outbox sweep: re-enqueue jobs whose push failed."""
    while True:
        await asyncio.sleep(interval)
        try:
            count = await asyncio.to_thread(dispatch_pending_jobs)
            if count:
                logger.info("jobs_redispatched", extra={"job_id": f"{count} jobs"})
        except Exception:
            logger.exception("job_dispatch_failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    dispatcher = None
    if dependency_checks_enabled():
        ensure_schema()
        dispatcher = asyncio.create_task(dispatch_loop())
    logger.info("api_started")
    yield
    if dispatcher is not None:
        dispatcher.cancel()
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


UNMATCHED_PATH = "__unmatched__"


def route_label(request: Request) -> str:
    """Route template for metrics labels; one shared label for unmatched paths."""
    return getattr(request.scope.get("route"), "path", UNMATCHED_PATH)


@app.middleware("http")
async def observe_request(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - started
        path = route_label(request)
        REQUESTS.labels(request.method, path, "500").inc()
        LATENCY.labels(request.method, path).observe(duration)
        logger.exception("request_failed", extra={"method": request.method, "path": path, "status_code": 500})
        raise
    duration = time.perf_counter() - started
    path = route_label(request)
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
def list_items(
    after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)
) -> list[dict[str, Any]]:
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, created_at FROM items WHERE id > %s ORDER BY id LIMIT %s",
            (after_id, limit),
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
    # Do NOT mark the job failed on an RPUSH error: the push may have been
    # delivered (ambiguous timeout). The job stays 'pending' and is re-pushed
    # by dispatch_pending_jobs(); the worker's claim is idempotent.
    try:
        redis_connection().rpush("jobs", str(job_id))
        logger.info("job_queued", extra={"job_id": str(job_id)})
    except Exception:
        logger.exception("job_enqueue_deferred", extra={"job_id": str(job_id)})
    if row is None:
        raise HTTPException(status_code=500, detail="job insert returned no row")
    return row


def dispatch_pending_jobs(older_than_seconds: int = 30) -> int:
    """Outbox sweep: re-enqueue jobs stuck in 'pending'. Run periodically
    (e.g. a CronJob or background task)."""
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT id FROM jobs WHERE status = 'pending' "
            "AND updated_at < NOW() - make_interval(secs => %s) LIMIT 500",
            (older_than_seconds,),
        ).fetchall()
        queue = redis_connection()
        for row in rows:
            queue.rpush("jobs", str(row["id"]))
            connection.execute("UPDATE jobs SET updated_at = NOW() WHERE id = %s AND status = 'pending'", (row["id"],))
        connection.commit()
    return len(rows)


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
