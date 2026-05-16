"""OAuth callback broker — receives Strava redirect, lets CLI poll for the code."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

PENDING_TTL_SECONDS = int(os.environ.get("OAUTH_PENDING_TTL", "300"))


@dataclass
class PendingAuth:
    code: str | None = None
    error: str | None = None
    expires_at: float = 0.0


_store: dict[str, PendingAuth] = {}
_lock = threading.Lock()

app = FastAPI(title="strava-cli OAuth", version="0.1.0")


def _cleanup_expired() -> None:
    now = time.time()
    expired = [state for state, entry in _store.items() if entry.expires_at < now]
    for state in expired:
        del _store[state]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/callback", response_class=HTMLResponse)
def oauth_callback(
    state: str = Query(..., min_length=8),
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    """Strava redirects here after user authorizes the app."""
    err = error
    if error_description:
        err = f"{error}: {error_description}" if error else error_description

    with _lock:
        _cleanup_expired()
        _store[state] = PendingAuth(
            code=code,
            error=err,
            expires_at=time.time() + PENDING_TTL_SECONDS,
        )

    if err:
        body = f"""
        <html><body style="font-family: system-ui; max-width: 32rem; margin: 4rem auto;">
        <h1>Authentication failed</h1>
        <p>{err}</p>
        <p>You can close this window and return to the terminal.</p>
        </body></html>
        """
    else:
        body = """
        <html><body style="font-family: system-ui; max-width: 32rem; margin: 4rem auto;">
        <h1>Authentication successful</h1>
        <p>You can close this window and return to the terminal.</p>
        </body></html>
        """

    return HTMLResponse(body)


@app.get("/poll")
def poll(state: str = Query(..., min_length=8)) -> dict[str, str]:
    """CLI polls until the authorization code is available (or an error occurs)."""
    with _lock:
        _cleanup_expired()
        entry = _store.get(state)

    if entry is None:
        raise HTTPException(status_code=404, detail="pending")

    if entry.expires_at < time.time():
        with _lock:
            _store.pop(state, None)
        raise HTTPException(status_code=410, detail="expired")

    if entry.error:
        with _lock:
            _store.pop(state, None)
        raise HTTPException(status_code=400, detail=entry.error)

    if not entry.code:
        raise HTTPException(status_code=404, detail="pending")

    with _lock:
        _store.pop(state, None)

    return {"code": entry.code, "state": state}
