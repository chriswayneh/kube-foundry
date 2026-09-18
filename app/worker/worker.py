from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from typing import Any

import psycopg
import redis


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "job_id"):
            payload["job_id"] = record.job_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
logger = logging.getLogger("kube_foundry.worker")
stopping = False

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


def stop(_: int, __: Any) -> None:
    global stopping
    stopping = True


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    return value


def redis_url() -> str:
    value = os.getenv("REDIS_URL")
    if not value:
        raise RuntimeError("REDIS_URL is required")
    return value


def ensure_schema() -> None:
    with psycopg.connect(database_url(), connect_timeout=3) as connection:
        connection.execute(SCHEMA)
        connection.commit()


def update_status(job_id: str, state: str) -> None:
    with psycopg.connect(database_url(), connect_timeout=3) as connection:
        connection.execute(
            "UPDATE jobs SET status = %s, updated_at = NOW() WHERE id = %s",
            (state, job_id),
        )
        connection.commit()


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    queue = redis.from_url(
        redis_url(), socket_connect_timeout=3, socket_timeout=5, decode_responses=True
    )

    while not stopping:
        try:
            ensure_schema()
            queue.ping()
            break
        except Exception:
            logger.exception("dependency_connect_failed")
            time.sleep(3)

    logger.info("worker_started")
    while not stopping:
        try:
            result = queue.blpop("jobs", timeout=2)
            if result is None:
                continue
            _, job_id = result
            update_status(job_id, "running")
            logger.info("job_started", extra={"job_id": job_id})
            time.sleep(0.25)
            update_status(job_id, "complete")
            logger.info("job_completed", extra={"job_id": job_id})
        except (redis.RedisError, psycopg.Error):
            logger.exception("job_processing_failed")
            time.sleep(2)
    logger.info("worker_stopped")


if __name__ == "__main__":
    run()
