"""
config.py
---------
Central configuration for the Zen Terminal daemon.

All timing constants live here so behaviour can be tuned in a single place
without touching business logic.
"""

import logging
from pathlib import Path


# ---------------------------------------------------------------------------
# Project root (one level above this file)
# ---------------------------------------------------------------------------
ROOT_DIR: Path = Path(__file__).parent.parent


class ZenConfig:
    """
    Immutable namespace of configuration constants.

    Timing values are expressed in seconds throughout the codebase so that
    arithmetic with ``time.monotonic()`` is straightforward.
    """

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    #: Continuous work seconds before the lock sequence fires (3 h).
    WORK_LIMIT: int = 3 * 3600

    #: Idle seconds required to reset the work timer (15 min).
    GRACE_PERIOD: int = 15 * 60

    #: Penalty-box duration; any input restarts this timer (10 min).
    PENALTY_DURATION: int = 10 * 60

    #: Seconds after each OS lock during which input events are ignored.
    #: Prevents the lock-screen login UI from immediately re-triggering.
    LOCK_COOLDOWN: float = 3.0

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    #: Main-loop sleep interval (seconds).  1 s gives 1-second resolution
    #: on all timers without burning CPU.
    TICK_INTERVAL: float = 1.0

    #: Minimum seconds between consecutive mouse-move event dispatches.
    #: Mouse-move fires hundreds of times per second; debouncing prevents
    #: unnecessary callback overhead.
    MOUSE_DEBOUNCE: float = 0.5

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    #: Meditation audio played during the penalty phase.
    AUDIO_FILE: Path = ROOT_DIR / "meditation.mp3"

    #: Directory where rotating log files are written.
    LOG_DIR: Path = ROOT_DIR / "logs"

    #: Main log file path.
    LOG_FILE: Path = LOG_DIR / "zen_terminal.log"

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    LOG_LEVEL: int = logging.INFO

    #: Maximum log-file size before rotation (10 MB).
    LOG_MAX_BYTES: int = 10 * 1024 * 1024

    #: Number of rotated backup files to retain.
    LOG_BACKUP_COUNT: int = 3
