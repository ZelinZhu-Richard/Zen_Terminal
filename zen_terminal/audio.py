"""
audio.py
--------
Meditation audio playback backed by pygame.mixer.

``AudioPlayer`` wraps the pygame mixer so the rest of the codebase never
touches pygame directly.  The mixer is initialised lazily on first use and
runs entirely in pygame's internal audio thread — no extra threads needed.

Design notes
~~~~~~~~~~~~
* ``SDL_VIDEODRIVER=dummy`` is set before pygame initialises so that no
  display window is created when the daemon runs headless.
* The audio is looped indefinitely (``loops=-1``) and must be stopped
  explicitly by calling ``stop()`` or ``cleanup()``.
* ``restart()`` is an atomic stop → play so the penalty logic can call it
  in a single line.
"""

import logging
import os
from pathlib import Path


class AudioPlayer:
    """
    Plays, stops, and restarts a single MP3 file via pygame.mixer.

    Parameters
    ----------
    audio_file:
        Absolute path to the meditation audio file.
    """

    def __init__(self, audio_file: Path) -> None:
        self._audio_file = audio_file
        self._initialized = False
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def play(self) -> None:
        """
        Load and play the audio file, looping indefinitely.

        If the mixer is not yet initialised, initialises it first.
        Logs an error (does not raise) if initialisation or playback fails.
        """
        if not self._ensure_initialized():
            return

        if not self._audio_file.exists():
            self._logger.error(
                "Audio file not found: %s — penalty will run silently.",
                self._audio_file,
            )
            return

        try:
            import pygame  # noqa: PLC0415 — deferred to avoid top-level SDL init

            pygame.mixer.music.load(str(self._audio_file))
            pygame.mixer.music.play(loops=-1)
            self._logger.info("Audio started: %s", self._audio_file.name)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Audio playback failed: %s", exc)

    def stop(self) -> None:
        """
        Stop playback immediately.

        Safe to call even if nothing is playing or the mixer has not been
        initialised.
        """
        if not self._initialized:
            return
        try:
            import pygame  # noqa: PLC0415

            pygame.mixer.music.stop()
            self._logger.info("Audio stopped.")
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Failed to stop audio: %s", exc)

    def restart(self) -> None:
        """Stop current playback and immediately start from the beginning."""
        self._logger.info("Audio restarting.")
        self.stop()
        self.play()

    def cleanup(self) -> None:
        """Stop playback and release mixer resources."""
        if not self._initialized:
            return
        try:
            import pygame  # noqa: PLC0415

            self.stop()
            pygame.mixer.quit()
            self._initialized = False
            self._logger.info("Audio mixer released.")
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Failed to release audio mixer: %s", exc)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> bool:
        """
        Initialise pygame.mixer if not already done.

        Returns ``True`` on success, ``False`` if initialisation failed.
        """
        if self._initialized:
            return True

        try:
            import pygame  # noqa: PLC0415

            # Prevent SDL from attempting to open a display — audio only.
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.init()
            self._initialized = True
            self._logger.info("pygame.mixer initialised.")
            return True
        except Exception as exc:  # noqa: BLE001
            self._logger.error("pygame.mixer initialisation failed: %s", exc)
            return False
