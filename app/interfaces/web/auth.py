"""Single-user password gate. Everything except login, health and static files needs a session."""

from __future__ import annotations

import hmac
import ipaddress
import logging
import time
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

PUBLIC_PATHS = {"/login", "/healthz"}
PUBLIC_PREFIXES = ("/static/",)


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def safe_next(target: str | None) -> str:
    """Only allow local redirects (blocks //evil.com and /\\evil.com)."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return "/"
    return target


def client_id(
    request: Request,
    trusted_header: str | None,
    trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (),
) -> str:
    """Who is trying to log in.

    Behind Railway the socket peer is the proxy, so we read the header its edge sets and
    overwrites on every request (X-Real-IP). The header is used only when it holds exactly one
    valid IP address and, if ``trusted_proxies`` is configured, only when the request came from
    one of them. Otherwise we fall back to the socket peer. X-Forwarded-For is never trusted.
    """
    peer = request.client.host if request.client else "unknown"
    if not trusted_header:
        return peer
    if trusted_proxies:
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer
        if not any(peer_ip in net for net in trusted_proxies):
            return peer
    raw = request.headers.get(trusted_header, "").strip()
    try:
        return str(ipaddress.ip_address(raw))  # rejects lists, garbage and empty values
    except ValueError:
        return peer


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

    - ``limit`` failures per client: the real brute-force guard, keyed by a trusted client IP.
    - ``global_limit`` failures across all clients: a high safety net in case the client IP
      is ever wrong. It is far above anything you'd hit yourself, and with a 12+ character
      password 200 guesses per 15 minutes gets nowhere. When it trips we log a warning.
    """

    MAX_TRACKED_CLIENTS = 1_000

    def __init__(self, limit: int = 5, global_limit: int = 200, window: float = 15 * 60) -> None:
        self.limit = limit
        self.global_limit = global_limit
        self.window = window
        self._failures: dict[str, list[float]] = {}
        self._all_failures: list[float] = []
        self._warned = False

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
        if len(self._all_failures) >= self.global_limit:
            if not self._warned:
                log.warning("Login safety limit reached: %d failed logins in %ds from many clients",
                            len(self._all_failures), int(self.window))
                self._warned = True
            return True
        self._warned = False
        return len(self._failures.get(client, [])) >= self.limit

    def fail(self, client: str) -> None:
        now = time.monotonic()
        self._all_failures.append(now)
        if client not in self._failures and len(self._failures) >= self.MAX_TRACKED_CLIENTS:
            self._prune(now)
            if len(self._failures) >= self.MAX_TRACKED_CLIENTS:
                return  # still counted by the global safety net
        self._failures.setdefault(client, []).append(now)

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)
