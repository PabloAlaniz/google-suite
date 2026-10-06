# Build from the repo root so the whole SDK is in context:
#   docker build -f api/Dockerfile -t gsuite-api .
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv

WORKDIR /app

# Dependencies first (pinned by uv.lock) so code changes don't bust this layer
COPY pyproject.toml uv.lock README.md ./
RUN uv export --locked --extra api --extra cloudrun --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

COPY packages packages
COPY api/src api/src
COPY cli/src cli/src
RUN uv pip install --system --no-cache --no-deps . && rm -rf packages api cli

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "gsuite_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
