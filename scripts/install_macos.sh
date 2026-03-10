#!/usr/bin/env bash
# install_macos.sh
# ----------------
# One-shot installer: creates a venv, installs dependencies, patches the
# launchd plist with real paths, and loads the agent.
#
# Usage:
#   chmod +x scripts/install_macos.sh
#   ./scripts/install_macos.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PLIST_SRC="$PROJECT_DIR/scripts/com.zenterminal.daemon.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.zenterminal.daemon.plist"
PYTHON_BIN="$VENV_DIR/bin/python"

echo "==> Project root: $PROJECT_DIR"

# ── 1. Create virtual environment ──────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtual environment at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "==> Virtual environment already exists at $VENV_DIR"
fi

# ── 2. Install Python dependencies ─────────────────────────────────────────
echo "==> Installing Python dependencies"
"$PYTHON_BIN" -m pip install --quiet --upgrade pip
"$PYTHON_BIN" -m pip install --quiet -r "$PROJECT_DIR/requirements.txt"

# ── 3. Check for meditation.mp3 ────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/meditation.mp3" ]; then
    echo "⚠  WARNING: $PROJECT_DIR/meditation.mp3 not found."
    echo "   Place your meditation audio file there before running the daemon."
fi

# ── 4. Patch and install the launchd plist ─────────────────────────────────
echo "==> Installing launchd agent to $PLIST_DST"

# Replace EDIT_ME placeholders with actual paths
sed \
    -e "s|/Users/EDIT_ME/dev/Zen_Terminal/.venv/bin/python|$PYTHON_BIN|g" \
    -e "s|/Users/EDIT_ME/dev/Zen_Terminal|$PROJECT_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

echo "==> Plist installed."

# ── 5. Grant Accessibility permission reminder ─────────────────────────────
echo ""
echo "IMPORTANT — macOS Accessibility permission required:"
echo "  System Settings → Privacy & Security → Accessibility"
echo "  Add Terminal (or iTerm2) AND Python to the allowed list."
echo "  Without this, pynput cannot capture global keyboard/mouse events."
echo ""

# ── 6. Load the launchd agent ──────────────────────────────────────────────
echo "==> Loading launchd agent"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"

echo ""
echo "✓ Zen Terminal daemon installed and running."
echo "  Logs: $PROJECT_DIR/logs/zen_terminal.log"
echo ""
echo "  To stop:    launchctl unload -w $PLIST_DST"
echo "  To restart: launchctl unload -w $PLIST_DST && launchctl load -w $PLIST_DST"
