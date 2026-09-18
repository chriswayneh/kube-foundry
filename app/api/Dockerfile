FROM python:3.13.13-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.lock .
RUN python -m pip wheel --wheel-dir /wheels -r requirements.lock

FROM python:3.13.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app
COPY --from=builder /wheels /wheels
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.lock \
    && rm -rf /wheels /tmp/requirements.lock
WORKDIR /app
COPY --chown=10001:10001 main.py .
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--no-access-log"]

