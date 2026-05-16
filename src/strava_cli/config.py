"""Configuration management with XDG-compliant paths."""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# XDG Base Directory Specification
def get_config_dir() -> Path:
    """Get XDG config directory."""
    if xdg := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg) / "strava-cli"
    return Path.home() / ".config" / "strava-cli"


def get_config_path() -> Path:
    """Get default config file path."""
    return get_config_dir() / "config.toml"


@dataclass
class AuthConfig:
    """Authentication configuration."""

    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: int | None = None
    athlete_id: int | None = None
    scopes: list[str] = field(default_factory=list)

    def is_authenticated(self) -> bool:
        """Check if we have valid auth tokens."""
        return self.access_token is not None

    def is_expired(self) -> bool:
        """Check if access token is expired."""
        if self.expires_at is None:
            return True
        import time

        return time.time() >= self.expires_at


@dataclass
class OAuthConfig:
    """OAuth flow settings."""

    callback_url: str | None = None


@dataclass
class DefaultsConfig:
    """Default settings."""

    format: str = "json"
    limit: int = 30


@dataclass
class Config:
    """Main configuration."""

    auth: AuthConfig = field(default_factory=AuthConfig)
    oauth: OAuthConfig = field(default_factory=OAuthConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    profiles: dict[str, AuthConfig] = field(default_factory=dict)
    client_id: str | None = None
    client_secret: str | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load configuration from file and environment variables."""
        config = cls()

        # Load from file if it exists
        config_path = path or get_config_path()
        if config_path.exists():
            config = cls._load_from_file(config_path)

        # Environment variable overrides
        config._apply_env_overrides()

        return config

    @classmethod
    def _load_from_file(cls, path: Path) -> Config:
        """Load configuration from TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        config = cls()

        # Parse client credentials
        if client_data := data.get("client"):
            config.client_id = client_data.get("id")
            config.client_secret = client_data.get("secret")

        # Parse auth section
        if auth_data := data.get("auth"):
            config.auth = AuthConfig(
                access_token=auth_data.get("access_token"),
                refresh_token=auth_data.get("refresh_token"),
                expires_at=auth_data.get("expires_at"),
                athlete_id=auth_data.get("athlete_id"),
                scopes=auth_data.get("scopes", []),
            )

        # Parse oauth section
        if oauth_data := data.get("oauth"):
            config.oauth = OAuthConfig(
                callback_url=oauth_data.get("callback_url"),
            )

        # Parse defaults section
        if defaults_data := data.get("defaults"):
            config.defaults = DefaultsConfig(
                format=defaults_data.get("format", "json"),
                limit=defaults_data.get("limit", 30),
            )

        # Parse profiles
        if profiles_data := data.get("profiles"):
            for name, profile_data in profiles_data.items():
                config.profiles[name] = AuthConfig(
                    access_token=profile_data.get("access_token"),
                    refresh_token=profile_data.get("refresh_token"),
                    expires_at=profile_data.get("expires_at"),
                    athlete_id=profile_data.get("athlete_id"),
                    scopes=profile_data.get("scopes", []),
                )

        return config

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides."""
        if token := os.environ.get("STRAVA_ACCESS_TOKEN"):
            self.auth.access_token = token
        if refresh := os.environ.get("STRAVA_REFRESH_TOKEN"):
            self.auth.refresh_token = refresh
        if callback_url := os.environ.get("STRAVA_OAUTH_CALLBACK_URL"):
            self.oauth.callback_url = callback_url

    def save(self, path: Path | None = None) -> None:
        """Save configuration to TOML file."""
        config_path = path or get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Set directory permissions to owner-only (0o700) for security
        config_path.parent.chmod(stat.S_IRWXU)

        # Build TOML content
        lines = []

        # Client credentials section
        if self.client_id or self.client_secret:
            lines.append("[client]")
            if self.client_id:
                lines.append(f'id = "{self.client_id}"')
            if self.client_secret:
                lines.append(f'secret = "{self.client_secret}"')
            lines.append("")

        # Auth section
        lines.append("[auth]")
        if self.auth.access_token:
            lines.append(f'access_token = "{self.auth.access_token}"')
        if self.auth.refresh_token:
            lines.append(f'refresh_token = "{self.auth.refresh_token}"')
        if self.auth.expires_at:
            lines.append(f"expires_at = {self.auth.expires_at}")
        if self.auth.athlete_id:
            lines.append(f"athlete_id = {self.auth.athlete_id}")
        if self.auth.scopes:
            scopes_str = ", ".join(f'"{s}"' for s in self.auth.scopes)
            lines.append(f"scopes = [{scopes_str}]")
        lines.append("")

        # Defaults section
        lines.append("[defaults]")
        lines.append(f'format = "{self.defaults.format}"')
        lines.append(f"limit = {self.defaults.limit}")
        lines.append("")

        # Profiles
        for name, profile in self.profiles.items():
            lines.append(f"[profiles.{name}]")
            if profile.access_token:
                lines.append(f'access_token = "{profile.access_token}"')
            if profile.refresh_token:
                lines.append(f'refresh_token = "{profile.refresh_token}"')
            if profile.expires_at:
                lines.append(f"expires_at = {profile.expires_at}")
            if profile.athlete_id:
                lines.append(f"athlete_id = {profile.athlete_id}")
            lines.append("")

        config_path.write_text("\n".join(lines))
        # Set file permissions to owner read/write only (0o600) since it contains tokens
        config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def get_profile(self, name: str | None) -> AuthConfig:
        """Get auth config for a profile, or default auth."""
        if name and name in self.profiles:
            return self.profiles[name]
        return self.auth

    def clear_auth(self, profile: str | None = None) -> None:
        """Clear authentication data."""
        if profile and profile in self.profiles:
            self.profiles[profile] = AuthConfig()
        else:
            self.auth = AuthConfig()


def get_client_credentials(config: Config | None = None) -> tuple[str, str]:
    """Get client ID and secret.

    Priority: environment variables > config file > built-in app credentials
    """
    client_id = os.environ.get("STRAVA_CLIENT_ID")
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET")

    if not client_id or not client_secret:
        if config is None:
            config = Config.load()
        if not client_id:
            client_id = config.client_id
        if not client_secret:
            client_secret = config.client_secret

    if not client_id:
        client_id = DEFAULT_CLIENT_ID
    if not client_secret:
        client_secret = DEFAULT_CLIENT_SECRET

    return client_id, client_secret


# Built-in Strava API app (Mart1M/strava-cli). Override via env or [client] in config.
DEFAULT_CLIENT_ID = "218318"
DEFAULT_CLIENT_SECRET = "45977b77318e9ccf6938c570d7f34129177fcaf6"

# Hosted OAuth broker (Coolify). Override via env or [oauth] callback_url in config.
DEFAULT_OAUTH_CALLBACK_URL = "https://cs44owkwc848kg00444gccks.mart1m.fr"


def get_oauth_callback_url(config: Config | None = None) -> str | None:
    """Get hosted OAuth callback base URL (no trailing path).

    Priority: STRAVA_OAUTH_CALLBACK_URL env > config [oauth] callback_url > default
    """
    if url := os.environ.get("STRAVA_OAUTH_CALLBACK_URL"):
        return url.rstrip("/")

    if config is None:
        config = Config.load()

    if config.oauth.callback_url:
        return config.oauth.callback_url.rstrip("/")

    return DEFAULT_OAUTH_CALLBACK_URL
