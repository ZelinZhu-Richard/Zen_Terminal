"""
monitor.py
----------
Global input monitoring via pynput.

``InputMonitor`` installs system-wide keyboard and mouse listeners.  Every
detected event invokes the caller-supplied ``on_activity`` callback.

Mouse-move events are debounced: the callback fires at most once per
``mouse_debounce`` seconds, keeping CPU load negligible during sustained
pointer movement.
"""

import logging
import threading
import time
from collections.abc import Callable

from pynput import keyboard, mouse


class InputMonitor:
    """
    Listens for any keyboard or mouse activity system-wide.

    Parameters
    ----------
    on_activity:
        Zero-argument callable invoked on every qualifying input event.
        It is called from pynput's internal listener threads, so it must
        be thread-safe.
    mouse_debounce:
        Minimum interval (seconds) between successive mouse-move callbacks.
        Keyboard and click events are never debounced.
    """

    def __init__(
        self,
        on_activity: Callable[[], None],
        mouse_debounce: float = 0.5,
    ) -> None:
        self._on_activity = on_activity
        self._mouse_debounce = mouse_debounce
        self._logger = logging.getLogger(__name__)

        self._active = False
        self._last_mouse_move: float = 0.0
        self._mouse_lock = threading.Lock()

        self._keyboard_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start both keyboard and mouse listeners.

        Safe to call from any thread.  Calling ``start`` on an already-
        running monitor is a no-op.
        """
        if self._active:
            self._logger.warning("InputMonitor.start() called while already running.")
            return

        self._active = True

        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_event,
            on_release=self._on_key_event,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_button,
            on_scroll=self._on_mouse_button,
        )

        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._logger.info("InputMonitor started (keyboard + mouse).")

    def stop(self) -> None:
        """
        Stop listeners and release system-level hooks.

        Safe to call multiple times or when not running.
        """
        self._active = False

        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None

        self._logger.info("InputMonitor stopped.")

    # ------------------------------------------------------------------
    # Private pynput callbacks
    # ------------------------------------------------------------------

    def _on_key_event(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """Fired on every key press or release."""
        if self._active:
            self._dispatch()

    def _on_mouse_move(self, x: int, y: int) -> None:
        """Fired on pointer movement; rate-limited by ``_mouse_debounce``."""
        if not self._active:
            return
        now = time.monotonic()
        with self._mouse_lock:
            if now - self._last_mouse_move < self._mouse_debounce:
                return
            self._last_mouse_move = now
        self._dispatch()

    def _on_mouse_button(self, *_args: object) -> None:
        """Fired on mouse clicks and scroll-wheel events (never debounced)."""
        if self._active:
            self._dispatch()

    def _dispatch(self) -> None:
        """Invoke the activity callback, swallowing any exceptions."""
        try:
            self._on_activity()
        except Exception:  # noqa: BLE001
            self._logger.exception("Unhandled exception in on_activity callback.")
