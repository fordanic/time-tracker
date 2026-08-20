"""Secure loopback server and packaged web application shell."""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass
from importlib.resources import files
from typing import Final, cast

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from time_tracker.infrastructure.browser import open_default_browser
from time_tracker.infrastructure.ipc import AgentClient
from time_tracker.web.api import InputError, WebAgent, WebApi, input_error_response

DEFAULT_WEB_PORT: Final = 47831
MAX_JSON_BODY_BYTES: Final = 64 * 1024
TOKEN_HEADER: Final = b"x-time-tracker-token"


@dataclass(frozen=True, slots=True)
class WebServerSettings:
    """Validated same-machine server binding."""

    port: int = DEFAULT_WEB_PORT
    host: str = "127.0.0.1"

    def __post_init__(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("the web interface may bind only to 127.0.0.1")
        if isinstance(self.port, bool) or not 1 <= self.port <= 65535:
            raise ValueError("the web interface port must be between 1 and 65535")

    @property
    def origin(self) -> str:
        """Return the exact stable browser origin."""
        return f"http://{self.host}:{self.port}"

    @property
    def host_header(self) -> str:
        """Return the only accepted HTTP Host header."""
        return f"{self.host}:{self.port}"


class SessionSecurityMiddleware:
    """Apply same-origin, launch-token, body-size, and response defenses."""

    def __init__(self, app: ASGIApp, settings: WebServerSettings, token: str) -> None:
        self.app = app
        self.settings = settings
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = cast(list[tuple[bytes, bytes]], scope["headers"])
        hosts = _header_values(headers, b"host")
        if len(hosts) != 1 or hosts[0].decode("latin-1") != self.settings.host_header:
            await self._reject(scope, receive, send, 400, "unexpected Host header")
            return

        method = cast(str, scope["method"]).upper()
        mutating = method in {"POST", "PUT", "PATCH", "DELETE"}
        if mutating:
            origins = _header_values(headers, b"origin")
            if (
                len(origins) != 1
                or origins[0].decode("latin-1") != self.settings.origin
            ):
                await self._reject(scope, receive, send, 403, "unexpected Origin")
                return
            supplied_tokens = _header_values(headers, TOKEN_HEADER)
            if len(supplied_tokens) != 1 or not secrets.compare_digest(
                supplied_tokens[0].decode("latin-1"), self.token
            ):
                await self._reject(scope, receive, send, 403, "invalid launch token")
                return
            content_types = _header_values(headers, b"content-type")
            if (
                len(content_types) != 1
                or content_types[0].decode("latin-1").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                await self._reject(scope, receive, send, 415, "JSON body required")
                return
            content_lengths = _header_values(headers, b"content-length")
            transfer_encodings = _header_values(headers, b"transfer-encoding")
            if transfer_encodings or len(content_lengths) > 1:
                await self._reject(scope, receive, send, 400, "invalid request framing")
                return
            expected_length: int | None = None
            if content_lengths:
                try:
                    expected_length = int(content_lengths[0])
                except ValueError:
                    expected_length = -1
                if expected_length < 0:
                    await self._reject(
                        scope, receive, send, 400, "invalid request framing"
                    )
                    return
                if expected_length > MAX_JSON_BODY_BYTES:
                    await self._reject(
                        scope, receive, send, 413, "JSON body is too large"
                    )
                    return
            body = await _read_limited_body(receive)
            if body is None:
                await self._reject(scope, receive, send, 413, "JSON body is too large")
                return
            if expected_length is not None and expected_length != len(body):
                await self._reject(scope, receive, send, 400, "invalid request framing")
                return
            try:
                decoded_body: object = json.loads(body)
            except UnicodeDecodeError, json.JSONDecodeError:
                await self._reject(scope, receive, send, 400, "invalid JSON body")
                return
            if not isinstance(decoded_body, dict):
                await self._reject(scope, receive, send, 400, "JSON object required")
                return
            receive = _replay_body(body)

        await self.app(scope, receive, self._secure_send(send))

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        message: str,
    ) -> None:
        response = JSONResponse(
            {"error": {"code": "request_rejected", "message": message}},
            status_code=status_code,
        )
        await response(scope, receive, self._secure_send(send))

    def _secure_send(self, send: Send) -> Send:
        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    (
                        (b"cache-control", b"no-store"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; connect-src 'self'; "
                            b"img-src 'self' data:; style-src 'self'; "
                            b"script-src 'self'; frame-ancestors 'none'; "
                            b"base-uri 'none'; form-action 'self'",
                        ),
                        (b"cross-origin-resource-policy", b"same-origin"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                    )
                )
                message["headers"] = response_headers
            await send(message)

        return secure_send


async def _read_limited_body(receive: Receive) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return b""
        chunk = cast(bytes, message.get("body", b""))
        total += len(chunk)
        if total > MAX_JSON_BODY_BYTES:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


def _replay_body(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _header_values(headers: list[tuple[bytes, bytes]], name: bytes) -> list[bytes]:
    return [value for header_name, value in headers if header_name.lower() == name]


def create_web_app(
    client: WebAgent,
    settings: WebServerSettings,
    *,
    token: str | None = None,
) -> ASGIApp:
    """Create one launch-scoped application around the agent client."""
    launch_token = token or secrets.token_urlsafe(32)
    static_root = files("time_tracker.web").joinpath("static")
    index_template = static_root.joinpath("index.html").read_text(encoding="utf-8")

    async def index(_request: Request) -> Response:
        html = index_template.replace("__TIME_TRACKER_TOKEN__", launch_token)
        return HTMLResponse(html)

    app = Starlette(
        routes=[
            Route("/", index),
            *WebApi(client).routes(),
            Mount(
                "/assets",
                app=StaticFiles(directory=str(static_root.joinpath("assets"))),
                name="assets",
            ),
        ],
        exception_handlers={
            InputError: input_error_response,
            ValueError: input_error_response,
        },
    )
    return SessionSecurityMiddleware(app, settings=settings, token=launch_token)


def run_web_server(
    client: AgentClient,
    *,
    port: int = DEFAULT_WEB_PORT,
    open_browser: bool = True,
) -> None:
    """Run Uvicorn on loopback and announce only after it is ready."""
    settings = WebServerSettings(port=port)
    app = create_web_app(client, settings)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            access_log=False,
            server_header=False,
        )
    )
    announcer = threading.Thread(
        target=_announce_ready,
        args=(server, settings.origin, open_browser),
        daemon=True,
    )
    announcer.start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass


def _announce_ready(server: uvicorn.Server, url: str, open_browser: bool) -> None:
    while not server.started and not server.should_exit:
        time.sleep(0.01)
    if not server.started:
        return
    if open_browser and open_default_browser(url):
        return
    print(f"Time Tracker web interface: {url}")
