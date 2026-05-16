FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY strava_oauth_server ./strava_oauth_server

RUN pip install --no-cache-dir .

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "strava_oauth_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
