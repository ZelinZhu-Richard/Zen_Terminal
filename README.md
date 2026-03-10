# Zen Terminal

A strict local background daemon that enforces mandatory breaks.

| Rule | Behaviour |
|---|---|
| Work for **3 continuous hours** | Screen locks + 10-min guided meditation starts |
| Idle for **15 minutes** | 3-hour work timer resets (natural break recognised) |
| Any input during the **10-min penalty** | Audio restarts, screen re-locks, timer resets |

---

## Project structure

```
Zen_Terminal/
├── meditation.mp3              ← you provide this file
├── requirements.txt
├── .gitignore
├── README.md
│
├── zen_terminal/               Python package
│   ├── __init__.py
│   ├── config.py               All timing constants — edit here to tune behaviour
│   ├── monitor.py              Global keyboard + mouse listener (pynput)
│   ├── audio.py                MP3 playback (pygame.mixer)
│   ├── locker.py               Cross-platform OS screen lock
│   ├── daemon.py               State machine + main control loop
│   └── main.py                 Entry point, logging setup
│
├── logs/                       Rotating log files (auto-created at runtime)
│
└── scripts/
    ├── install_macos.sh                One-shot automated macOS installer
    ├── com.zenterminal.daemon.plist    macOS launchd agent template
    └── zenterminal.service            Linux systemd user service template
```

---

## Requirements

- Python 3.10+
- `meditation.mp3` placed in the project root (any guided meditation audio)

---

## Quick start

```bash
# 1. Clone / enter the project
cd /path/to/Zen_Terminal

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your audio file
cp ~/Downloads/meditation.mp3 ./meditation.mp3

# 5. Run (Ctrl-C to stop)
python -m zen_terminal.main
```

Logs are written to `logs/zen_terminal.log`. Warnings also print to stderr.

---

## Running as a persistent daemon

### macOS — automated (recommended)

```bash
./scripts/install_macos.sh
```

The script creates `.venv`, installs dependencies, patches the launchd plist
with your real paths, copies it to `~/Library/LaunchAgents/`, and loads the
agent. The daemon starts at login and auto-restarts on crash.

**Then grant Accessibility permission — this is required:**

> **System Settings → Privacy & Security → Accessibility**
> Add your terminal app (Terminal / iTerm2) **and** `.venv/bin/python`.

Without it, pynput cannot intercept global input events and nothing is tracked.

Useful commands:

```bash
# Status
launchctl list | grep zenterminal

# Live logs
tail -f logs/zen_terminal.log

# Stop
launchctl unload -w ~/Library/LaunchAgents/com.zenterminal.daemon.plist

# Restart
launchctl unload -w ~/Library/LaunchAgents/com.zenterminal.daemon.plist
launchctl load  -w ~/Library/LaunchAgents/com.zenterminal.daemon.plist
```

---

### macOS — manual

```bash
cp scripts/com.zenterminal.daemon.plist ~/Library/LaunchAgents/
# Edit the file — replace every EDIT_ME with real absolute paths
nano ~/Library/LaunchAgents/com.zenterminal.daemon.plist
launchctl load -w ~/Library/LaunchAgents/com.zenterminal.daemon.plist
```

---

### Linux — systemd user service

```bash
cp scripts/zenterminal.service ~/.config/systemd/user/zenterminal.service
# Edit — replace every EDIT_ME with real absolute paths
nano ~/.config/systemd/user/zenterminal.service

systemctl --user daemon-reload
systemctl --user enable --now zenterminal

# Status and logs
systemctl --user status zenterminal
journalctl --user -u zenterminal -f
```

pynput on Linux reads `/dev/input/event*`. Add your user to the `input` group
if events are not captured:

```bash
sudo usermod -aG input $USER
# Log out and back in for the change to take effect
```

---

### Windows — Task Scheduler

1. Open **Task Scheduler → Create Basic Task**
2. Trigger: **At log on** (your user)
3. Action: **Start a program**
   - Program: `C:\path\to\Zen_Terminal\.venv\Scripts\python.exe`
   - Arguments: `C:\path\to\Zen_Terminal\zen_terminal\main.py`
4. Settings tab: *"If the task is already running, do not start a new instance"*
5. General tab: *"Run only when user is logged on"*

---

## Configuration

All constants are in `zen_terminal/config.py`. Edit and relaunch to apply.

| Constant | Default | Description |
|---|---|---|
| `WORK_LIMIT` | 3 h | Continuous work before lock triggers |
| `GRACE_PERIOD` | 15 min | Idle time that resets the work timer |
| `PENALTY_DURATION` | 10 min | Penalty box duration (restarts on any input) |
| `LOCK_COOLDOWN` | 3 s | Input ignored immediately after each lock |
| `TICK_INTERVAL` | 1 s | Main loop resolution |
| `MOUSE_DEBOUNCE` | 0.5 s | Minimum gap between mouse-move callbacks |
| `AUDIO_FILE` | `meditation.mp3` | Path to meditation audio |

---

## Architecture

```
main.py
  └─► ZenDaemon (daemon.py)
        ├─ InputMonitor (monitor.py)   pynput keyboard + mouse listeners
        │    └─ _record_activity() ──► updates _last_activity (thread-safe)
        ├─ ScreenLocker (locker.py)    OS-native screen lock
        └─ AudioPlayer  (audio.py)     pygame.mixer MP3 playback
```

**State machine:**

```
WORKING ──(idle ≥ grace_period)───────► IDLE
IDLE    ──(any input)─────────────────► WORKING
WORKING ──(active ≥ work_limit)───────► PENALTY  → lock() + audio.play()
PENALTY ──(input detected)────────────► PENALTY  → lock() + audio.restart()
PENALTY ──(penalty_duration elapsed)──► WORKING  → audio.stop() + timer reset
```

**Threading:** pynput listeners run on background threads. Only `_last_activity`
is written from those threads (protected by `_activity_lock`). All state
transitions happen on the main thread inside `_tick()`, eliminating races
and deadlocks.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No input detected (macOS) | Missing Accessibility permission | System Settings → Privacy → Accessibility |
| No input detected (Linux) | Not in `input` group | `sudo usermod -aG input $USER` |
| Silent penalty | `meditation.mp3` missing | Copy file to project root |
| Audio init error | No audio device / headless | Check `logs/zen_terminal.log` for pygame error |
| Screen not locking (macOS) | CGSession path changed | Auto-falls back to `osascript ⌃⌘Q` |
| Screen not locking (Linux) | No lock tool installed | `sudo apt install gnome-screensaver` or `i3lock` |
