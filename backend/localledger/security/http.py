"""Protects the localhost API from other websites and unauthenticated local processes.

Three independent checks:
1. Host allow-list  - defeats DNS rebinding (a hostile page resolving its own name to 127.0.0.1).
2. Bearer token     - a per-launch secret only the desktop shell knows.
3. CORS allow-list  - configured in app factory; browsers refuse to expose responses elsewhere.
"""

from __future__ import annotations

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def _host_only(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if ":" in value else value


class LocalApiGuard:
    def __init__(self, app: ASGIApp, token: str) -> None:
        if len(token) < 32:
            raise ValueError("API token must be at least 32 characters.")
        self.app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # No websocket/lifespan surface is exposed to clients.
            if scope["type"] == "lifespan":
                await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        host = _host_only(headers.get(b"host", b"").decode("latin-1"))
        if host not in _LOOPBACK_HOSTS:
            await JSONResponse({"detail": "Forbidden host"}, status_code=403)(scope, receive, send)
            return
        if scope["method"] != "OPTIONS":
            supplied = headers.get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self._expected):
                response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
