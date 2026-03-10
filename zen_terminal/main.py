"""
main.py
-------
Entry point for the Zen Terminal daemon.

Responsibilities
~~~~~~~~~~~~~~~~
1. Configure rotating file and console logging before any other module
   is imported (so every module's ``getLogger`` call sees handlers).
2. Validate that the meditation audio file exists (warn but do not abort).
3. Instantiate ``ZenDaemon`` and call ``run()``.

Usage
~~~~~
    python -m zen_terminal.main          # direct invocation
    zen-terminal                         # if installed via pip
"""

import logging
import logging.handlers
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure the package root is on sys.path when run directly.
# ---------------------------------------------------------------------------
_PACKAGE_ROOT = Path(__file__).parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from zen_terminal.config import ZenConfig  # noqa: E402
from zen_terminal.daemon import ZenDaemon  # noqa: E402


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _configure_logging(config: ZenConfig) -> None:
    """
    Set up a rotating file handler plus a stderr stream handler.

    The file handler writes up to ``LOG_MAX_BYTES`` before rotating and
    keeps ``LOG_BACKUP_COUNT`` backup files.  The console handler is
    deliberately less verbose (WARNING+) so daemon stdout stays quiet
    when running under launchd / systemd.
    """
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(config.LOG_LEVEL)

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename=config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(config.LOG_LEVEL)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    # Console handler (warnings and above only)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def _validate_environment(config: ZenConfig) -> None:
    """
    Emit warnings for configuration issues that will not prevent startup
    but may degrade functionality (e.g. missing audio file).
    """
    logger = logging.getLogger(__name__)

    if not config.AUDIO_FILE.exists():
        logger.warning(
            "Meditation audio file not found: %s\n"
            "The penalty phase will run silently.  Place a file named\n"
            "'meditation.mp3' in the project root to enable audio.",
            config.AUDIO_FILE,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Configure logging, validate the environment, and start the daemon."""
    config = ZenConfig()
    _configure_logging(config)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Zen Terminal starting up.")
    logger.info("=" * 60)

    _validate_environment(config)

    daemon = ZenDaemon(config)
    daemon.run()


if __name__ == "__main__":
    main()
