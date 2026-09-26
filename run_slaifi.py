"""SLAI-root process launcher for SLAIFI.

Location
--------
SLAI/run_slaifi.py

SLAIFI itself lives at::

    SLAI/applications/slaifi/

The launcher owns process startup only. Package resolution belongs to
``applications.slaifi`` and requires no ``sys.path`` mutation.
"""

from __future__ import annotations

import logging

import uvicorn

# Import the integrated application package first. Its package root exposes
# the current backend implementation as one coherent SLAIFI package.
import applications.slaifi  # noqa: F401

from logs.logger import (
    LoggingSettings,
    configure_logging,
    get_logger,
    shutdown_logging,
)
from slaifi.core.config import get_settings
from slaifi.core.utils.errors import SlaifiError


logger = get_logger("SLAIFI Launcher")


def main() -> int:
    """Configure SLAI-owned logging and start the SLAIFI API."""

    logging_configured = False

    try:
        settings = get_settings()
        level = getattr(logging, settings.log_level, logging.INFO)

        configure_logging(LoggingSettings(level=level))
        logging_configured = True

        logger.info(
            "Starting SLAIFI on http://%s:%s (environment=%s)",
            settings.api_host,
            settings.api_port,
            settings.environment,
        )

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
