FROM python:3.12-slim

WORKDIR /app

# Coolify deployment healthcheck requires curl or wget in the image
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY strava_oauth_server ./strava_oauth_server

RUN pip install --no-cache-dir .

HEALTHCHECK --interval=5s --timeout=5s --retries=10 --start-period=5s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "strava_oauth_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
