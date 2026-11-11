from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    app_password: str
    secret_key: str
    database_url: str
    timezone: ZoneInfo
    production: bool
    cf_sync_minutes: int = 30  # background Codeforces sync interval; 0 turns it off

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        production = env.get("APP_ENV", "").lower() == "production" or any(
            k.startswith("RAILWAY_") for k in env
        )

        missing = [k for k in ("APP_PASSWORD", "SECRET_KEY") if not env.get(k)]
        if production and not env.get("DATABASE_URL"):
            # Railway's disk is wiped on every deploy: SQLite there would silently lose your data.
            missing.append("DATABASE_URL")
        if missing:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")

        if production and len(env["SECRET_KEY"]) < 32:
            raise ConfigError("SECRET_KEY must be at least 32 characters in production")

        tz_name = env.get("APP_TIMEZONE", "Europe/Berlin")
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unknown APP_TIMEZONE '{tz_name}'") from exc

        try:
            sync_minutes = int(env.get("CF_SYNC_MINUTES", "30"))
        except ValueError as exc:
            raise ConfigError("CF_SYNC_MINUTES must be a whole number") from exc
        if sync_minutes < 0 or 0 < sync_minutes < 5:
            raise ConfigError("CF_SYNC_MINUTES must be 0 (off) or at least 5")

        return cls(
            app_password=env["APP_PASSWORD"],
            secret_key=env["SECRET_KEY"],
            database_url=env.get("DATABASE_URL") or "sqlite:///./cf_tracker.db",
            timezone=tz,
            production=production,
            cf_sync_minutes=sync_minutes,
        )
