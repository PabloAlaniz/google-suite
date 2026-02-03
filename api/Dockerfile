FROM python:3.12-slim

WORKDIR /app

# Copy all packages
COPY packages/core packages/core
COPY packages/gmail packages/gmail
COPY packages/calendar packages/calendar
COPY api api

# Install packages
RUN pip install --no-cache-dir \
    ./packages/core[cloudrun] \
    ./packages/gmail \
    ./packages/calendar \
    ./api

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "gsuite_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
