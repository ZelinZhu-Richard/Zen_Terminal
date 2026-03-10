"""
daemon.py
---------
Core orchestration for the Zen Terminal productivity enforcer.

``ZenDaemon`` owns all runtime state, wires together the four sub-systems
(input monitoring, timer logic, audio, screen locking), and drives the
main control loop.

State machine
~~~~~~~~~~~~~

::

    WORKING ──(idle ≥ grace_period)──► IDLE
    IDLE    ──(any input)────────────► WORKING
    WORKING ──(active ≥ work_limit)──► PENALTY  (lock + audio)
    PENALTY ──(any input detected)───► PENALTY  (relock + restart audio)
    PENALTY ──(penalty_duration met)─► WORKING  (audio stop + reset)

Threading model
~~~~~~~~~~~~~~~
* pynput fires ``_record_activity`` from its own listener threads.
* ``_last_activity`` is the only variable written by those threads.  It
  is protected by ``_activity_lock`` (a plain ``threading.Lock``).
* Everything else — state transitions, lock/audio calls — happens
  exclusively on the main thread inside ``_tick()``.

This keeps locking minimal and eliminates any risk of deadlock.
"""

import logging
import signal
import threading
import time
from enum import Enum, auto
from pathlib import Path

from zen_terminal.audio import AudioPlayer
from zen_terminal.config import ZenConfig
from zen_terminal.locker import ScreenLocker
from zen_terminal.monitor import InputMonitor


class DaemonState(Enum):
    """Top-level states of the Zen Terminal daemon."""

    WORKING = auto()
    """User is actively working; the 3-hour work timer is accumulating."""

    IDLE = auto()
    """User has been idle for ≥ grace_period; work timer has been reset."""

    PENALTY = auto()
    """Work limit was hit; screen is locked and audio is playing."""


class ZenDaemon:
    """
    Wires together input monitoring, timer logic, audio, and screen locking.

    Parameters
    ----------
    config:
        A ``ZenConfig`` instance (or subclass) providing all timing and
        file-path constants.
    """

    def __init__(self, config: ZenConfig | None = None) -> None:
        self._config = config or ZenConfig()
        self._logger = logging.getLogger(__name__)

        # Sub-systems
        self._monitor = InputMonitor(
            on_activity=self._record_activity,
            mouse_debounce=self._config.MOUSE_DEBOUNCE,
        )
        self._audio = AudioPlayer(self._config.AUDIO_FILE)
        self._locker = ScreenLocker()

        # ----------------------------------------------------------------
        # Mutable state
        # All variables below are read/written ONLY on the main thread
        # EXCEPT _last_activity, which is also written from pynput threads.
        # ----------------------------------------------------------------
        self._state: DaemonState = DaemonState.WORKING

        now = time.monotonic()
        self._work_session_start: float = now
        self._penalty_start: float = 0.0

        # Suppress input callbacks for LOCK_COOLDOWN seconds after each lock
        # to avoid the login-screen UI triggering an immediate restart.
        self._activity_ignore_until: float = 0.0

        # _last_activity is shared: main thread reads, pynput threads write.
        self._activity_lock = threading.Lock()
        self._last_activity: float = now

        self._running = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start the daemon and block until ``stop()`` is called or a signal
        is received.

        Installs ``SIGTERM`` and ``SIGINT`` handlers so the process can be
        cleanly terminated by the OS or a terminal interrupt.
        """
        self._install_signal_handlers()
        self._running = True
        self._monitor.start()

        self._logger.info(
            "Zen Terminal daemon started. "
            "Work limit: %d min | Grace period: %d min | Penalty: %d min.",
            self._config.WORK_LIMIT // 60,
            self._config.GRACE_PERIOD // 60,
            self._config.PENALTY_DURATION // 60,
        )

        try:
            while self._running:
                time.sleep(self._config.TICK_INTERVAL)
                self._tick()
        except KeyboardInterrupt:
            self._logger.info("KeyboardInterrupt received.")
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Signal the main loop to exit on the next tick."""
        self._logger.info("Stop requested.")
        self._running = False

    # ------------------------------------------------------------------
    # Main-loop tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """
        Called once per ``TICK_INTERVAL`` on the main thread.

        Reads shared state atomically, then performs all state transitions
        and side-effects (lock, audio) without holding any lock.
        """
        now = time.monotonic()
        last_activity = self._get_last_activity()

        if self._state == DaemonState.PENALTY:
            self._tick_penalty(now, last_activity)
        else:
            self._tick_work(now, last_activity)

    def _tick_work(self, now: float, last_activity: float) -> None:
        """Handle WORKING / IDLE state logic."""
        idle_duration = now - last_activity

        if idle_duration >= self._config.GRACE_PERIOD:
            # --------------------------------------------------------
            # Grace period reached: user has been idle long enough to
            # earn a full work-timer reset.
            # --------------------------------------------------------
            if self._state != DaemonState.IDLE:
                self._state = DaemonState.IDLE
                self._work_session_start = now
                self._logger.info(
                    "Grace period reached after %.0f min idle — work timer reset.",
                    idle_duration / 60,
                )
            return

        # ----------------------------------------------------------------
        # User is (or was very recently) active.
        # ----------------------------------------------------------------
        if self._state == DaemonState.IDLE:
            # Transition back to WORKING: new session starts now.
            self._state = DaemonState.WORKING
            self._work_session_start = now
            self._logger.info("Activity resumed — new work session started.")

        active_seconds = now - self._work_session_start
        remaining_seconds = self._config.WORK_LIMIT - active_seconds

        self._logger.debug(
            "State=WORKING | active=%.0f min | break in %.0f min.",
            active_seconds / 60,
            remaining_seconds / 60,
        )

        if active_seconds >= self._config.WORK_LIMIT:
            self._trigger_lock_sequence(now)

    def _tick_penalty(self, now: float, last_activity: float) -> None:
        """Handle PENALTY state logic."""
        # ----------------------------------------------------------------
        # Input-activity check:
        # Skip the cooldown window immediately after each lock — events
        # that originate from the OS login screen UI should not restart
        # the penalty.
        # ----------------------------------------------------------------
        if now > self._activity_ignore_until:
            if last_activity > self._penalty_start:
                self._logger.warning(
                    "Input detected %.1f s into penalty — restarting penalty.",
                    last_activity - self._penalty_start,
                )
                self._restart_penalty(now)
                return

        # ----------------------------------------------------------------
        # Completion check
        # ----------------------------------------------------------------
        elapsed = now - self._penalty_start
        remaining = self._config.PENALTY_DURATION - elapsed

        self._logger.debug(
            "State=PENALTY | elapsed=%.0f s | remaining=%.0f s.",
            elapsed,
            remaining,
        )

        if elapsed >= self._config.PENALTY_DURATION:
            self._end_penalty(now)

    # ------------------------------------------------------------------
    # State-transition actions (main thread only)
    # ------------------------------------------------------------------

    def _trigger_lock_sequence(self, now: float) -> None:
        """
        Transition to PENALTY: lock the screen and start audio.

        Called when the active work timer reaches ``WORK_LIMIT``.
        """
        self._logger.warning(
            "Work limit of %d min reached! Initiating lock sequence.",
            self._config.WORK_LIMIT // 60,
        )
        self._state = DaemonState.PENALTY
        self._penalty_start = now
        self._activity_ignore_until = now + self._config.LOCK_COOLDOWN
        self._locker.lock()
        self._audio.play()

    def _restart_penalty(self, now: float) -> None:
        """
        Input was detected during the penalty box.

        Re-issues the OS lock and restarts the audio from the beginning,
        then resets the 10-minute penalty timer.
        """
        self._penalty_start = now
        self._activity_ignore_until = now + self._config.LOCK_COOLDOWN
        self._locker.lock()
        self._audio.restart()

    def _end_penalty(self, now: float) -> None:
        """
        Penalty complete: stop audio and start a fresh work session.

        Called after ``PENALTY_DURATION`` seconds of zero input.
        """
        self._logger.info(
            "Penalty complete after %d min. Resetting work session.",
            self._config.PENALTY_DURATION // 60,
        )
        self._audio.stop()
        self._state = DaemonState.WORKING
        self._work_session_start = now
        # Treat the end of penalty as the start of a fresh activity burst
        # so the work timer begins from now rather than from stale history.
        self._set_last_activity(now)

    # ------------------------------------------------------------------
    # Thread-safe activity tracking
    # ------------------------------------------------------------------

    def _record_activity(self) -> None:
        """
        Called by ``InputMonitor`` from pynput listener threads.

        Only updates ``_last_activity``; all state transitions happen on
        the main thread in ``_tick()``.
        """
        with self._activity_lock:
            self._last_activity = time.monotonic()

    def _get_last_activity(self) -> float:
        """Thread-safe read of ``_last_activity``."""
        with self._activity_lock:
            return self._last_activity

    def _set_last_activity(self, value: float) -> None:
        """Thread-safe write of ``_last_activity`` from the main thread."""
        with self._activity_lock:
            self._last_activity = value

    # ------------------------------------------------------------------
    # Signal handling and shutdown
    # ------------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        """Register SIGTERM and SIGINT handlers for clean shutdown."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, _frame: object) -> None:
        """Handle termination signals by requesting a graceful stop."""
        self._logger.info("Received signal %d — stopping.", signum)
        self.stop()

    def _shutdown(self) -> None:
        """Stop all sub-systems and release resources."""
        self._logger.info("Shutting down Zen Terminal daemon.")
        self._monitor.stop()
        self._audio.cleanup()
        self._logger.info("Shutdown complete.")
