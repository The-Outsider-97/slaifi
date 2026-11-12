"""Serve the built web UI from the API process, so one command starts everything.

The UI is a static single-page app (``dist/``, produced by ``npm run build``). It is mounted
after every API route, so ``/api/...``, ``/health`` and ``/docs`` always win; any other path that is
not a real file falls back to ``index.html``.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Vite names built files ``name-<hash>.ext``: the name changes whenever the content does, so a
# browser may keep such a file for good. Everything else (index.html above all) keeps the
# server-wide ``no-store`` default, so a new build is picked up at once.
_HASHED_ASSET = re.compile(r"^assets/.+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")
IMMUTABLE_CACHE = "private, max-age=31536000, immutable"


class _SinglePageApp(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            path = "index.html"
            response = await super().get_response(path, scope)
        if _HASHED_ASSET.match(path.lstrip("/")):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE
        return response


def default_dist_dir() -> Path:
    """``<slaifi root>/dist`` (this file is ``backend/slaifi/api/static_ui.py``)."""

    return Path(__file__).resolve().parents[3] / "dist"


def mount_frontend(app: FastAPI, dist_dir: Path | None = None) -> bool:
    """Mount the built UI at ``/``. Returns False (and mounts nothing) when it is not built."""

    directory = dist_dir or default_dist_dir()
    if not (directory / "index.html").is_file():
        return False
    app.mount("/", _SinglePageApp(directory=directory, html=True), name="ui")
    return True
