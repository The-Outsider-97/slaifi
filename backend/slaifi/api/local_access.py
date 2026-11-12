"""Who may talk to the local server: the same rules every SLAI application follows.

* **Who**: a random token, shown only in the link printed at start-up, is exchanged once for an
  HttpOnly, SameSite=Strict cookie. Every other request needs that cookie.
* **Which page**: the ``Host`` header must be this server (defeats DNS rebinding); changes
  (POST/PUT/PATCH/DELETE) must not come from another origin.
* **What the page may do**: security headers (and the shared Content-Security-Policy) on every
  response.

This mirrors ``applications/tools/server/http.py`` (which serves the other SLAI applications). That
server is built on ``http.server`` and cannot host FastAPI, so the same rules are applied here as
ASGI middleware. The host-supplied CSP and header set are passed in by the launcher so this module
stays independent of the SLAI host.
"""

from __future__ import annotations

import hmac
import http.cookies
import json
from collections.abc import Mapping
from urllib.parse import parse_qsl

from starlette.types import ASGIApp, Message, Receive, Scope, Send

COOKIE_NAME = "slai_slaifi_token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_LOCKED_PAGE = (
    b"<!doctype html><meta charset=utf-8><title>SLAI SLAIFI</title>"
    b'<body style="font:16px system-ui;margin:3rem"><h1>SLAI SLAIFI</h1>'
    b"<p>This page needs the link that SLAIFI printed when it started (it contains a one-time "
    b"access token). Open that link, or start SLAIFI again.</p></body>"
)


class LocalAccessMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str,
        port: int,
        security_headers: Mapping[str, str] | None = None,
    ) -> None:
        if not token:
            raise ValueError("An access token is required")
        self._app = app
        self._token = token.encode()
        self._hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        self._origins = {f"http://{host}" for host in self._hosts}
        self._security_headers = [
            (k.lower().encode(), v.encode()) for k, v in (security_headers or {}).items()
        ]

    # -- helpers -------------------------------------------------------------------------------
    def _authorised(self, headers: Mapping[str, str]) -> bool:
        raw = headers.get("cookie")
        if not raw:
            return False
        jar: http.cookies.SimpleCookie = http.cookies.SimpleCookie()
        try:
            jar.load(raw)
        except http.cookies.CookieError:
            return False
        morsel = jar.get(COOKIE_NAME)
        return morsel is not None and hmac.compare_digest(morsel.value.encode(), self._token)

    async def _respond(
        self,
        send: Send,
        status: int,
        body: bytes,
        content_type: str,
        extra: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        headers = [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store"),
            *self._security_headers,
            *(extra or []),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def _json_error(self, send: Send, status: int, message: str) -> None:
        body = json.dumps({"detail": message}).encode()
        await self._respond(send, status, body, "application/json")

    # -- ASGI ----------------------------------------------------------------------------------
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._app(scope, receive, send)
            return
        if scope["type"] != "http":  # no websockets are served
            await send({"type": "websocket.close", "code": 1008})
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        path = scope["path"]
        method = scope["method"]

        if headers.get("host", "").lower() not in self._hosts:
            await self._json_error(send, 401, "This address is not allowed")
            return

        if path == "/" and b"token=" in scope.get("query_string", b""):
            query = dict(parse_qsl(scope["query_string"].decode("latin-1"), keep_blank_values=True))
            if hmac.compare_digest(query.get("token", "").encode(), self._token):
                cookie = f"{COOKIE_NAME}={self._token.decode()}; Path=/; HttpOnly; SameSite=Strict"
                await self._respond(
                    send,
                    302,
                    b"",
                    "text/plain",
                    [(b"location", b"/"), (b"set-cookie", cookie.encode())],
                )
            else:
                await self._respond(send, 403, _LOCKED_PAGE, "text/html; charset=utf-8")
            return

        if not self._authorised(headers):
            if path.startswith("/api/"):
                await self._json_error(
                    send, 401, "Not signed in. Open SLAIFI from the link it printed at start-up."
                )
            else:
                await self._respond(send, 403, _LOCKED_PAGE, "text/html; charset=utf-8")
            return

        origin = headers.get("origin")
        if (
            method not in _SAFE_METHODS
            and origin is not None
            and origin.lower() not in self._origins
        ):
            await self._json_error(send, 403, "This origin is not allowed")
            return

        extra = self._security_headers

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message["headers"]}
                merged = list(message["headers"])
                merged += [(k, v) for k, v in extra if k not in present]
                if b"cache-control" not in present:
                    merged.append((b"cache-control", b"no-store"))
                message["headers"] = merged
            await send(message)

        await self._app(scope, receive, send_with_headers)
