"""
locker.py
---------
Cross-platform OS screen-lock implementation.

``ScreenLocker.lock()`` detects the current platform at call time and
delegates to the appropriate OS-specific method.  All methods are non-
blocking: the lock command is dispatched and control returns immediately
so the daemon can continue monitoring.

Platform strategies
~~~~~~~~~~~~~~~~~~~
macOS
    Primary:  ``CGSession -suspend`` — the canonical programmatic lock
              available since macOS 10.5.
    Fallback: ``osascript`` sending the ⌃⌘Q keyboard shortcut (macOS 10.13+).

Linux
    Tries the following lock utilities in order, stopping at the first
    that succeeds: ``loginctl lock-session``, ``gnome-screensaver-command``,
    ``xdg-screensaver``, ``xscreensaver-command``, ``i3lock``.

Windows
    Calls ``LockWorkStation()`` directly via ``ctypes`` — no subprocess
    required, instant and reliable.
"""

import logging
import platform
import subprocess
from typing import NoReturn


class ScreenLocker:
    """Locks the workstation screen using OS-native mechanisms."""

    #: macOS path to CGSession binary.
    _CGSESSION_PATH: str = (
        "/System/Library/CoreServices/Menu Extras/"
        "User.menu/Contents/Resources/CGSession"
    )

    #: Ordered list of Linux lock commands to attempt.
    _LINUX_LOCK_COMMANDS: list[list[str]] = [
        ["loginctl", "lock-session"],
        ["gnome-screensaver-command", "--lock"],
        ["xdg-screensaver", "lock"],
        ["xscreensaver-command", "-lock"],
        ["i3lock"],
    ]

    def __init__(self) -> None:
        self._os: str = platform.system()
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def lock(self) -> None:
        """
        Lock the screen on the current platform.

        Dispatches to the appropriate OS implementation and logs the
        outcome.  Never raises; errors are logged instead so the daemon
        loop remains uninterrupted.
        """
        self._logger.info("Locking screen (OS: %s).", self._os)
        try:
            if self._os == "Darwin":
                self._lock_macos()
            elif self._os == "Windows":
                self._lock_windows()
            elif self._os == "Linux":
                self._lock_linux()
            else:
                self._logger.error("Unsupported OS: %s — cannot lock screen.", self._os)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Screen lock failed: %s", exc)

    # ------------------------------------------------------------------
    # OS-specific implementations
    # ------------------------------------------------------------------

    def _lock_macos(self) -> None:
        """
        Lock macOS using CGSession, falling back to the ⌃⌘Q shortcut.

        ``CGSession -suspend`` is the fastest and most reliable method.
        The AppleScript fallback handles edge cases where the CGSession
        binary has moved (e.g. certain sandboxed environments).
        """
        import shutil

        if shutil.which("CGSession") or self._run_command(
            [self._CGSESSION_PATH, "-suspend"], log_errors=False
        ):
            return

        self._logger.debug("CGSession not found; falling back to osascript ⌃⌘Q.")
        self._run_command(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "q" '
                "using {command down, control down}",
            ]
        )

    def _lock_windows(self) -> None:
        """Lock Windows by calling ``LockWorkStation`` via ctypes."""
        import ctypes  # noqa: PLC0415 — Windows-only import

        result: int = ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
        if result == 0:
            self._logger.error(
                "LockWorkStation() returned 0 — lock may have failed."
            )

    def _lock_linux(self) -> None:
        """
        Lock Linux by trying known screen-lock utilities in order.

        Iterates ``_LINUX_LOCK_COMMANDS`` and stops after the first
        successful invocation.  Logs an error if none succeed.
        """
        for cmd in self._LINUX_LOCK_COMMANDS:
            if self._run_command(cmd, log_errors=False):
                self._logger.debug("Screen locked via: %s", cmd[0])
                return

        self._logger.error(
            "No suitable lock command found on this Linux system. "
            "Install one of: %s",
            ", ".join(c[0] for c in self._LINUX_LOCK_COMMANDS),
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _run_command(
        self, cmd: list[str], *, log_errors: bool = True
    ) -> bool:
        """
        Run *cmd* as a subprocess.

        Returns
        -------
        bool
            ``True`` if the command was found and exited with code 0,
            ``False`` otherwise.
        """
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return True
        except FileNotFoundError:
            if log_errors:
                self._logger.debug("Command not found: %s", cmd[0])
            return False
        except subprocess.CalledProcessError as exc:
            if log_errors:
                self._logger.debug("Command %s exited with %d.", cmd[0], exc.returncode)
            return False
        except subprocess.TimeoutExpired:
            self._logger.warning("Lock command timed out: %s", cmd[0])
            return False
