# Multi-stage: the builder owns compilers and pip cache, the runtime owns nothing
# but the files the app actually reads.

# ---------- builder ----------
FROM python:3.13-slim AS builder

WORKDIR /build

# Install into a venv so the runtime stage can copy one directory instead of
# hunting site-packages across image layers.
RUN python -m venv /opt/venv

# requirements-runtime.txt is pinned (== everywhere): the image is reproducible, and a
# transitive release cannot silently change behaviour between two builds. It is the
# lock file minus the test runner -- CI needs pytest, the production image does not.
COPY requirements-runtime.txt .
RUN /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check \
        -r requirements-runtime.txt

# ---------- runtime ----------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PATH="/opt/venv/bin:$PATH" \
    LOG_FORMAT=json

# Never run as root: the app shells out to a stdio MCP subprocess and writes to a
# mounted volume, neither of which needs uid 0.
RUN useradd --uid 10001 --create-home shitu

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Only what the app reads at runtime. data/runtime/ (sqlite + vector index) is
# gitignored state, not source -- it arrives as a volume.
COPY --chown=shitu:shitu app ./app
COPY --chown=shitu:shitu frontend ./frontend
COPY --chown=shitu:shitu data/catalog ./data/catalog
COPY --chown=shitu:shitu data/knowledge ./data/knowledge
COPY --chown=shitu:shitu data/knowledge-sources.json ./data/
COPY --chown=shitu:shitu data/knowledge-sources-shandong.json ./data/
COPY --chown=shitu:shitu data/knowledge-sources-luoyang.json ./data/

# sqlite and the vector index live here; owned by the unprivileged user.
RUN mkdir -p /app/data/runtime && chown -R shitu:shitu /app/data

USER shitu
EXPOSE 8767

# Liveness only. Readiness (/api/readyz) needs the MCP session and a writable DB,
# which is a slower question -- keep it out of the restart decision.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import sys,urllib.request; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8767/api/healthz', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8767"]
