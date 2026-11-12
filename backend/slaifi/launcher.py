"""Start SLAIFI the way every SLAI application starts: ``python -m applications.slaifi``.

Same shape as SPlanner, Reader and SPADRA: the shared ``applications/tools`` kit supplies the command
line options, the loopback rule, the start-up banner, the per-user data folder, the typed
``configs/config.yaml`` and clean shutdown. SLAIFI's FastAPI application is served by uvicorn on a
socket bound here, and reached through a link that carries a one-time access token.

This module is the SLAI host launcher: it needs ``applications.tools`` (it is not used standalone).
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
from pathlib import Path
from typing import Any

import uvicorn
from applications.tools import slai
from applications.tools.config import Field, load_section
from applications.tools.errors import AppError
from applications.tools.server import add_server_arguments, refuse_remote_host, serve
from applications.tools.server.http import SECURITY_HEADERS
from applications.tools.storage import default_data_dir
from dotenv import dotenv_values
from logs.logger import LoggingSettings, configure_logging, shutdown_logging

from slaifi import __version__
from slaifi.core.config import Settings
from slaifi.core.utils.errors import SlaifiError

SLUG, TITLE, DEFAULT_PORT = "slaifi", "SLAIFI", 8777
HERE = Path(__file__).resolve().parents[2]  # <SLAI>/applications/slaifi

SETTINGS_FIELDS: dict[str, Field] = {
    "port": Field(DEFAULT_PORT, 1, 65535),
    "log_level": Field("INFO", kind=str),
    "market_provider_order": Field("twelvedata,tiingo,fmp,finnhub,alphavantage", kind=str),
    "market_quote_cache_ttl_seconds": Field(60, 0, 300, kind=float),
    "market_history_cache_ttl_seconds": Field(300, 0, 3600, kind=float),
}
# config.yaml name -> Settings field
_SETTINGS_NAME = {"port": "api_port"}


class UvicornServer:
    """The small interface ``tools.server.serve`` expects, backed by uvicorn on a socket we bound."""

    def __init__(self, app: Any, sock: socket.socket) -> None:
        self._sock = sock
        config = uvicorn.Config(app, log_config=None, access_log=False, server_header=False)
        self._server = uvicorn.Server(config)
        self.port: int = sock.getsockname()[1]

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        self._server.run(sockets=[self._sock])

    def shutdown(self) -> None:
        self._server.should_exit = True

    def server_close(self) -> None:
        self._sock.close()


def bind(host: str, port: int) -> socket.socket:
    """Listen on ``host:port`` or raise ``OSError`` when it is taken (no silent port sharing)."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


def load_settings(
    *,
    config: str | None,
    data_dir: str | None,
    client_dir: str | None,
    port: int | None,
    env_file: Path | None,
) -> tuple[Settings, Path | None, str | None]:
    """Settings from ``configs/config.yaml`` < ``.env`` / environment < command line."""

    config_path = Path(config) if config else HERE / "configs" / "config.yaml"
    values, note = load_section(
        config_path, "app", SETTINGS_FIELDS, label="SLAIFI configuration", overrides={"port": port}
    )
    explicit: set[str] = {k.upper() for k in os.environ}
    if env_file is not None and env_file.is_file():
        explicit |= {k.upper() for k in dotenv_values(env_file)}
    init: dict[str, Any] = {}
    for name, value in values.items():
        target = _SETTINGS_NAME.get(name, name)
        from_command_line = name == "port" and port is not None
        if from_command_line or f"SLAIFI_{target.upper()}" not in explicit:
            init[target] = value
    if data_dir:
        init["data_dir"] = Path(data_dir)
    init["frontend_dist_dir"] = Path(client_dir) if client_dir else HERE / "dist"
    kwargs: dict[str, Any] = {"_env_file": env_file} if env_file and env_file.is_file() else {}
    return Settings(**kwargs, **init), config_path, note


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m applications.slaifi",
        description=f"{TITLE}: paper-trading decision support on real market data.",
    )
    add_server_arguments(parser, title=TITLE, default_port=DEFAULT_PORT)
    args = parser.parse_args(argv)
    if refuse_remote_host(args.host, TITLE, "your portfolio"):
        return 2

    root = slai.activate(slai.find_slai_root(args.slai_root))
    try:
        return _run(args, root)
    finally:
        shutdown_logging()


def _run(args: argparse.Namespace, root: Path | None) -> int:
    try:
        settings, config_path, note = load_settings(
            config=args.config,
            data_dir=args.data_dir,
            client_dir=args.client_dir,
            port=args.port,
            env_file=(root / ".env") if root else None,
        )
        client_dir = Path(str(settings.frontend_dist_dir))
        if not (client_dir / "index.html").is_file():
            print(
                f"The web client is not built ({client_dir / 'index.html'} is missing). "
                f"Run `npm install` and `npm run build` in {HERE}.",
                file=sys.stderr,
            )
            return 2

        configure_logging(LoggingSettings(level=getattr(logging, settings.log_level, logging.INFO)))

        sock = bind(args.host, settings.api_port)
        port = sock.getsockname()[1]
        settings = settings.model_copy(update={"api_port": port})

        from slaifi.main import create_app  # builds the ledger and market gateway

        token = args.token or secrets.token_urlsafe(32)
        app = create_app(settings, access_token=token, security_headers=dict(SECURITY_HEADERS))
        server = UvicornServer(app, sock)
    except ValueError as exc:  # invalid configuration (names the setting)
        print(exc, file=sys.stderr)
        return 2
    except (AppError, SlaifiError) as exc:
        print(
            f"{getattr(exc, 'message', exc)} {getattr(exc, 'hint', None) or ''}".strip(),
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            f"{TITLE} could not start: {exc.strerror or exc}. Is another copy already running? Try --port.",
            file=sys.stderr,
        )
        return 1

    configured = [s.name for s in app.state.market_data_provider.provider_status() if s.configured]
    notes = [note] if note else []
    if not configured:
        notes.append(
            "No market-data key is set, so prices show NOT AVAILABLE. Add SLAIFI_TWELVEDATA_API_KEY, "
            "SLAIFI_TIINGO_API_KEY and SLAIFI_FMP_API_KEY (free keys) to "
            f"{(root / '.env') if root else 'the .env file in the SLAI root'} and restart."
        )
    elif len(configured) < 3:
        notes.append(
            f"Only {len(configured)} market-data source(s) set; three or more are recommended for failover."
        )
    details = [
        (
            "Data",
            str(Path(settings.data_dir) if settings.data_dir else default_data_dir(SLUG, TITLE)),
        ),
        ("SLAI", str(root) if root else "not found"),
        ("Config", str(config_path)),
        ("Market data", ", ".join(configured) if configured else "no source configured"),
    ]
    return int(
        serve(
            server,
            title=TITLE,
            version=__version__,
            url=f"http://127.0.0.1:{port}/?token={token}",
            details=details,
            notes=notes,
            open_browser=not args.no_browser,
        )
    )
