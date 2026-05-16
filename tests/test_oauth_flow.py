"""Tests for OAuth login flows."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from strava_cli.auth import (
    build_auth_url,
    interactive_login_remote,
    wait_for_remote_callback,
)
from strava_cli.cli import app


def test_build_auth_url_includes_redirect_uri() -> None:
    url = build_auth_url("12345", "https://auth.example.com/callback", "state-abc")
    assert "client_id=12345" in url
    assert "redirect_uri=https%3A%2F%2Fauth.example.com%2Fcallback" in url
    assert "state=state-abc" in url


def test_wait_for_remote_callback_returns_code() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": "abc123", "state": "s1"})
    )
    mock_client = httpx.Client(transport=transport)
    ctx = MagicMock(
        __enter__=MagicMock(return_value=mock_client),
        __exit__=MagicMock(return_value=False),
    )
    mock_client_class = MagicMock(return_value=ctx)

    with patch("strava_cli.auth.httpx.Client", mock_client_class):
        code, error = wait_for_remote_callback("https://auth.example.com", "s1", timeout=5)
    assert code == "abc123"
    assert error is None


def test_wait_for_remote_callback_retries_on_pending() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(404, json={"detail": "pending"})
        return httpx.Response(200, json={"code": "late-code", "state": "s2"})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(transport=transport)
    ctx = MagicMock(
        __enter__=MagicMock(return_value=mock_client),
        __exit__=MagicMock(return_value=False),
    )
    mock_client_class = MagicMock(return_value=ctx)

    with (
        patch("strava_cli.auth.httpx.Client", mock_client_class),
        patch("strava_cli.auth.time.sleep"),
    ):
        code, error = wait_for_remote_callback(
            "https://auth.example.com",
            "s2",
            timeout=5,
            poll_interval=0,
        )
    assert code == "late-code"
    assert error is None
    assert calls["n"] == 2


def test_interactive_login_remote_success(
    monkeypatch: pytest.MonkeyPatch,
    env_credentials: None,
) -> None:
    monkeypatch.setenv("STRAVA_OAUTH_CALLBACK_URL", "https://auth.example.com")

    with (
        patch("strava_cli.auth.webbrowser.open"),
        patch(
            "strava_cli.auth.wait_for_remote_callback",
            return_value=("auth-code", None),
        ),
        patch("strava_cli.auth.exchange_code_for_token") as mock_exchange,
    ):
        mock_exchange.return_value = MagicMock(
            access_token="at",
            refresh_token="rt",
            expires_at=9999999999,
            athlete_id=42,
            scopes=["read"],
        )
        result = interactive_login_remote("1", "secret", "https://auth.example.com")

    assert result is not None
    assert result.access_token == "at"
    mock_exchange.assert_called_once_with("1", "secret", "auth-code")


def test_auth_login_remote(
    cli_runner: CliRunner,
    tmp_config_dir: Path,
    env_credentials: None,
    mock_httpx_oauth: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRAVA_OAUTH_CALLBACK_URL", "https://auth.example.com")

    with (
        patch("strava_cli.auth.webbrowser.open"),
        patch(
            "strava_cli.auth.wait_for_remote_callback",
            return_value=("test_code", None),
        ),
    ):
        result = cli_runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["athlete_id"] == 12345
