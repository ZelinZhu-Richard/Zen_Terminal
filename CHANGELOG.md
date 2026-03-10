# Changelog

All notable changes to Zen Terminal are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2026-03-09

### Added
- `InputMonitor`: global keyboard and mouse listener via pynput, with
  configurable mouse-move debounce.
- `AudioPlayer`: meditation MP3 playback via pygame.mixer; lazy init,
  headless-safe (`SDL_VIDEODRIVER=dummy`).
- `ScreenLocker`: cross-platform screen lock — macOS (`CGSession` +
  `osascript` fallback), Linux (loginctl → gnome-screensaver → xdg →
  xscreensaver → i3lock), Windows (`LockWorkStation` via ctypes).
- `ZenDaemon`: three-state machine (WORKING → IDLE → PENALTY) with a
  thread-safe activity timestamp and a post-lock cooldown window.
- `ZenConfig`: single-file configuration for all timing constants.
- Rotating log files via `logging.handlers.RotatingFileHandler`.
- macOS launchd agent template + one-shot `install_macos.sh`.
- Linux systemd user-service template.
- `pyproject.toml` with `zen-terminal` console entry point.
