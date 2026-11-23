"""Runtime configuration for the J.A.R.V.I.S. harness.

Everything the harness persists lives under ``data/`` so the whole
installation stays self-contained inside the project directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "tts_cache"
NOTES_FILE = DATA_DIR / "notes.md"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "jarvis.log"

HOST = os.environ.get("JARVIS_HOST", "127.0.0.1")
PORT = int(os.environ.get("JARVIS_PORT", "8765"))

DEFAULTS = {
    "assistant_name": "JARVIS",
    "user_title": "sir",
    "voice": "en-GB-RyanNeural",
    "tts_engine": "piper",
    "piper_model": "tools/piper/voices/en_GB-alan-medium.onnx",
    "piper_length_scale": 1.04,
    "language_mode": "english",
    "listen_language": "en-IN",
    "wake_words": ["jarvis", "jervis", "jarvus", "parvez", "parvis", "javis", "jarvix", "harvis", "charvis", "darvis", "jarvez", "जार्विस"],
    "awake_seconds": 45,
    "confirm_seconds": 45,
    "weather_location": "",
    "llm_enabled": True,
    "llm_model": "deepseek-chat",
}


def ensure_dirs() -> None:
    for directory in (DATA_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    settings = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return settings


SETTINGS = load_settings()


def deepseek_key() -> str | None:
    """Find a DeepSeek key from the environment or the local DSH profile."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    candidates = [
        Path.home() / ".dsh" / ".credentials.yaml",
        Path.home() / ".config" / "dsh" / ".credentials.yaml",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = re.search(r"DEEPSEEK_API_KEY:\s*([A-Za-z0-9_\-]+)", text)
        if match:
            return match.group(1)
    return None


def has_command(*names: str) -> bool:
    return any(shutil.which(name) for name in names)


def capabilities() -> dict:
    """Feature detection surfaced to the interface."""
    return {
        "tts": True,
        "llm": bool(deepseek_key()),
        "audio": has_command("wpctl", "pactl"),
        "media": has_command("busctl") and has_command("gdbus"),
        "wifi": has_command("nmcli"),
        "apps": has_command("gtk-launch", "gio"),
        "shell": True,
        "typing": has_command("wtype", "ydotool", "xdotool"),
        "screenshot": has_command("gdbus", "grim", "gnome-screenshot", "spectacle", "import"),
    }


VOICE_LINES = {
    "wake": [
        "Yes, sir?",
        "At your service, sir.",
        "Standing by.",
        "How may I assist?",
    ],
    "sleep": [
        "Going quiet, sir. Say Jarvis when you need me.",
        "Standing down. I'll be here, sir.",
    ],
    "confirm_cancel": [
        "Cancelled, sir.",
        "As you were, sir.",
    ],
    "unknown": [
        "I didn't quite catch that, sir.",
        "My apologies, sir — say again?",
        "That one slipped past me, sir.",
    ],
    "offline_brain": [
        "My neural core is offline, sir. I can still handle local commands.",
        "The long-range brain is unavailable, sir. Local systems remain online.",
    ],
}
