"""SLAI-root process launcher for SLAIFI.

Location
--------
SLAI/run_slaifi.py

SLAIFI itself lives at::

    SLAI/applications/slaifi/

The launcher owns process startup only. Package resolution belongs to
``applications.slaifi`` and requires no import-path mutation.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

# Import the integrated application package first. Its package root exposes
# the current backend implementation as one coherent SLAIFI package.
import applications.slaifi  # noqa: F401
import uvicorn
from logs.logger import (
    LoggingSettings,
    configure_logging,
    get_logger,
    shutdown_logging,
)

from slaifi.core.config import get_settings
from slaifi.core.utils.errors import SlaifiError

logger = get_logger("SLAIFI Launcher")

FRONTEND_DIR = Path(__file__).resolve().parent / "applications" / "slaifi" / "frontend"


def _ui_is_stale(frontend: Path) -> bool:
    """True when the built UI is missing or older than its sources."""

    built = frontend / "dist" / "index.html"
    if not built.is_file():
        return True
    built_at = built.stat().st_mtime
    watched = [frontend / "index.html", frontend / "package.json"]
    watched += [p for p in (frontend / "src").rglob("*") if p.is_file()]
    return any(p.stat().st_mtime > built_at for p in watched if p.exists())


def ensure_ui_built() -> None:
    """Build the web UI once (and after UI changes) so the API can serve it: one command to run.

    Needs Node.js. If it is missing or the build fails the API still starts and says what to do.
    Set SLAIFI_SKIP_UI_BUILD=1 to skip this step.
    """

    if os.environ.get("SLAIFI_SKIP_UI_BUILD") or not FRONTEND_DIR.is_dir():
        return
    if not _ui_is_stale(FRONTEND_DIR):
        return
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        logger.warning(
            "Web UI not built and Node.js/npm was not found. Install Node.js LTS, then run "
            "run_slaifi.py again. The API still works at /docs."
        )
        return
    try:
        if not (FRONTEND_DIR / "node_modules").is_dir():
            logger.info("Installing web UI dependencies (first run only)...")
            subprocess.run(
                [npm, "install", "--no-audit", "--no-fund"],
                cwd=FRONTEND_DIR,
                check=True,
                timeout=900,
            )
        logger.info("Building the web UI...")
        subprocess.run([npm, "run", "build:ui"], cwd=FRONTEND_DIR, check=True, timeout=900)
    except (OSError, subprocess.SubprocessError):
        logger.exception(
            "Building the web UI failed. The API still runs. To see the error, run "
            "`npm run build:ui` in %s",
            FRONTEND_DIR,
        )


def main() -> int:
    """Configure SLAI-owned logging and start the SLAIFI API."""

    logging_configured = False

    try:
        settings = get_settings()
        level = getattr(logging, settings.log_level, logging.INFO)

        configure_logging(LoggingSettings(level=level))
        logging_configured = True

        logger.info(
            "Starting SLAIFI on http://%s:%s (environment=%s) - open that address in your browser",
            settings.api_host,
            settings.api_port,
            settings.environment,
        )

        ensure_ui_built()

        # SLAIFI owns application composition.
        from slaifi.main import app

        uvicorn.run(
            app,
            host=settings.api_host,
            port=settings.api_port,
            log_config=None,
        )
        return 0

    except KeyboardInterrupt:
        logger.info("SLAIFI stopped by user")
        return 130
    except SlaifiError:
        logger.exception("SLAIFI startup failed with an application error")
        return 2
    except (ImportError, OSError, RuntimeError, ValueError):
        logger.exception("SLAIFI startup failed")
        return 1
    finally:
        if logging_configured:
            shutdown_logging()


if __name__ == "__main__":
    raise SystemExit(main())
