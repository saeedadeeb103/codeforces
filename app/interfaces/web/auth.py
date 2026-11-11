"""Single-user password gate. Everything except login, health and static files needs a session."""

from __future__ import annotations

import hmac
import time
from urllib.parse import quote

from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = {"/login", "/healthz"}
PUBLIC_PREFIXES = ("/static/",)


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def safe_next(target: str | None) -> str:
    """Only allow local redirects (blocks //evil.com and /\\evil.com)."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return "/"
    return target


def password_matches(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())


class RequireLogin:
    """ASGI middleware; must sit inside SessionMiddleware so ``scope['session']`` exists."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_public(scope["path"]):
            await self.app(scope, receive, send)
            return
        if scope.get("session", {}).get("auth") is True:
            await self.app(scope, receive, send)
            return
        target = "/login"
        if scope["method"] == "GET" and scope["path"] != "/":
            qs = scope.get("query_string", b"").decode()
            target += "?next=" + quote(scope["path"] + (f"?{qs}" if qs else ""), safe="")
        await RedirectResponse(target, status_code=303)(scope, receive, send)


class LoginThrottle:
    """At most ``limit`` failed attempts per client per ``window`` seconds (in-memory, one process)."""

    def __init__(self, limit: int = 5, window: float = 15 * 60) -> None:
        self.limit = limit
        self.window = window
        self._failures: dict[str, list[float]] = {}

    def blocked(self, client: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._failures.get(client, []) if now - t < self.window]
        self._failures[client] = recent
        return len(recent) >= self.limit

    def fail(self, client: str) -> None:
        self._failures.setdefault(client, []).append(time.monotonic())

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)
