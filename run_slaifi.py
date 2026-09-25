"""Root launcher for SLAIFI inside the wider SLAI repository.

Final target location:
    SLAI/run_slaifi.py

The file is delivered from the SLAIFI repository for reference and should be
moved to the SLAI root without modification. It intentionally contains no
working-directory assumptions or ``sys.path`` mutation.
"""

from __future__ import annotations

import logging

import uvicorn
from logs.logger import LoggingSettings, configure_logging, get_logger, shutdown_logging

from slaifi.core.config import get_settings
from slaifi.core.utils.errors import SlaifiError

logger = get_logger("SLAIFI Launcher")


def main() -> int:
    """Configure SLAI-owned logging and run the SLAIFI FastAPI application."""

    logging_configured = False
    try:
        settings = get_settings()
        level = getattr(logging, settings.log_level)
        configure_logging(LoggingSettings(level=level))
        logging_configured = True

        logger.info(
            "Starting SLAIFI on %s:%s (environment=%s)",
            settings.api_host,
            settings.api_port,
            settings.environment,
        )

        # Import only after SLAI logging is configured. ``slaifi.main`` owns
        # application composition; this launcher owns only process startup.
        from slaifi.main import app

        uvicorn.run(
            app,
            host=settings.api_host,
            port=settings.api_port,
            log_config=None,
        )
        return 0
    except SlaifiError:
        logger.exception("SLAIFI startup failed with an expected application error")
        return 2
    except (ImportError, OSError, RuntimeError, ValueError):
        logger.exception("SLAIFI startup failed")
        return 1
    finally:
        if logging_configured:
            shutdown_logging()


if __name__ == "__main__":
    raise SystemExit(main())
