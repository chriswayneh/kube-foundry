FROM python:3.13.15-alpine3.24 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.lock .
RUN python -m pip wheel --wheel-dir /wheels -r requirements.lock

FROM python:3.13.15-alpine3.24 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN addgroup -S -g 10001 app \
    && adduser -S -D -u 10001 -G app -h /home/app -s /sbin/nologin app
COPY --from=builder /wheels /wheels
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.lock \
    && python -m pip uninstall --yes pip \
    && rm -rf /wheels /tmp/requirements.lock /usr/local/lib/python3.13/ensurepip
WORKDIR /app
COPY --chown=10001:10001 worker.py .
USER 10001:10001
CMD ["python", "worker.py"]
