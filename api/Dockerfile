# Build from the repo root so the whole SDK is in context:
#   docker build -f api/Dockerfile -t gsuite-api .
#
# Two stages: uv builds a virtualenv in the first one, and the runtime image
# gets only that venv (no uv, no build tooling, no source tree).

FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Dependencies first (pinned by uv.lock) so code changes don't bust this layer
COPY pyproject.toml uv.lock README.md ./
# uv.lock references this path dependency (the dev-only "skill" group); uv
# needs its metadata to check the lock even though the image doesn't install it
COPY tools/agent-distribution tools/agent-distribution
RUN uv sync --locked --no-dev --no-install-project --extra api --extra cloudrun

COPY packages packages
COPY api/src api/src
COPY cli/src cli/src
RUN uv sync --locked --no-dev --no-editable --extra api --extra cloudrun

# googleapiclient bundles ~500 discovery documents (~100 MB); keep the ones the
# SDK builds. api/tests/test_dockerfile.py checks this list against the
# build() calls in the code, and CI builds every one inside the image.
ARG DISCOVERY_KEEP="gmail.v1 calendar.v3 drive.v3 sheets.v4 tasks.v1 people.v1 oauth2.v2"
RUN cd /opt/venv/lib/python3.*/site-packages/googleapiclient/discovery_cache/documents \
    && mkdir /tmp/keep \
    && for doc in $DISCOVERY_KEEP; do mv "$doc.json" /tmp/keep/; done \
    && rm -f ./*.json \
    && mv /tmp/keep/*.json .


FROM python:3.14-slim

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 appuser
COPY --from=builder /opt/venv /opt/venv

WORKDIR /home/appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]

# --no-access-log: RequestContextMiddleware already logs each request with its ID
CMD ["uvicorn", "gsuite_api.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
