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
    """Failed-login limits per ``window`` seconds (in-memory, one process).

    - ``limit`` failures per client address.
    - ``global_limit`` failures across *all* clients. Client addresses come from proxy headers
      and can be spoofed, so this cap is what actually bounds brute force. The trade-off: an
      attacker can lock the login page for one window, but existing sessions keep working.
    """

    MAX_TRACKED_CLIENTS = 1_000

    def __init__(self, limit: int = 5, global_limit: int = 20, window: float = 15 * 60) -> None:
        self.limit = limit
        self.global_limit = global_limit
        self.window = window
        self._failures: dict[str, list[float]] = {}
        self._all_failures: list[float] = []

    def _prune(self, now: float) -> None:
        self._all_failures = [t for t in self._all_failures if now - t < self.window]
        for client in list(self._failures):
            recent = [t for t in self._failures[client] if now - t < self.window]
            if recent:
                self._failures[client] = recent
            else:
                del self._failures[client]

    def blocked(self, client: str) -> bool:
        self._prune(time.monotonic())
        return (
            len(self._all_failures) >= self.global_limit
            or len(self._failures.get(client, [])) >= self.limit
        )

    def fail(self, client: str) -> None:
        now = time.monotonic()
        self._all_failures.append(now)
        if client not in self._failures and len(self._failures) >= self.MAX_TRACKED_CLIENTS:
            self._prune(now)
            if len(self._failures) >= self.MAX_TRACKED_CLIENTS:
                return  # the global cap still counts this failure
        self._failures.setdefault(client, []).append(now)

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)
