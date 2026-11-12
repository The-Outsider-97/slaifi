"""Serve the built web UI from the API process, so one command starts everything.

The UI is a static single-page app (``frontend/dist``, produced by ``vite build``). It is mounted
after every API route, so ``/api/...``, ``/health`` and ``/docs`` always win; any other path that is
not a real file falls back to ``index.html``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class _SinglePageApp(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def default_dist_dir() -> Path:
    """``<slaifi root>/frontend/dist`` (this file is ``backend/slaifi/api/static_ui.py``)."""

    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def mount_frontend(app: FastAPI, dist_dir: Path | None = None) -> bool:
    """Mount the built UI at ``/``. Returns False (and mounts nothing) when it is not built."""

    directory = dist_dir or default_dist_dir()
    if not (directory / "index.html").is_file():
        return False
    app.mount("/", _SinglePageApp(directory=directory, html=True), name="ui")
    return True
