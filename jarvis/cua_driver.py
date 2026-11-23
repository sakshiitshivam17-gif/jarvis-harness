"""Adapter for the bundled CUA driver (trycua/cua).

The driver is the input/output half of a computer-use agent: it lists windows,
reads an accessibility tree, screenshots a window, and delivers clicks and
keystrokes without stealing focus. This module wraps the driver's CLI so the
harness can drive it from Python, and degrades cleanly when the daemon or a
given window is unavailable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config

BUNDLED = config.BASE_DIR / "tools" / "cua-driver" / "cua-driver"
SOCKET = Path.home() / ".cache" / "cua-driver" / "cua-driver.sock"

# Apps that must run through XWayland so the driver can address their windows
# on GNOME Wayland, where the Shell helper extension is not loadable yet.
X11_HINTS = ("chrome", "chromium", "code", "code-oss", "slack", "discord", "obsidian")

_DAEMON_LOCK = threading.Lock()


def binary() -> str | None:
    if BUNDLED.exists() and os.access(BUNDLED, os.X_OK):
        return str(BUNDLED)
    return shutil.which("cua-driver")


def available() -> bool:
    return binary() is not None


def daemon_running() -> bool:
    if not SOCKET.exists():
        return False
    return _call(["status"], timeout=8, raw=True) is not None


def ensure_daemon() -> bool:
    """Start the driver daemon once and wait for its socket."""
    if not available():
        return False
    with _DAEMON_LOCK:
        if daemon_running():
            return True
        SOCKET.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(
                [binary(), "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return False
        for _ in range(40):
            if SOCKET.exists():
                time.sleep(0.15)
                return True
            time.sleep(0.1)
    return False


def stop_daemon() -> None:
    _call(["stop"], timeout=10, raw=True)


def _call(args: list[str], timeout: float = 45, raw: bool = False):
    exe = binary()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    if raw:
        return out or None
    try:
        return json.loads(out)
    except ValueError:
        return {"ok": False, "error": out[-400:] or proc.stderr[-400:]}


def tool(name: str, args: dict | None = None, timeout: float = 45) -> dict:
    if not available():
        return {"ok": False, "error": "cua driver not installed"}
    if not ensure_daemon():
        return {"ok": False, "error": "cua driver daemon unavailable"}
    payload = json.dumps(args or {})
    result = _call(["call", name, payload], timeout=timeout)
    if not isinstance(result, dict):
        return {"ok": False, "error": "no response from driver"}
    return result


# --------------------------------------------------------------------- reads
def windows(pid: int | None = None) -> list[dict]:
    args = {"pid": pid} if pid else {}
    result = tool("list_windows", args, timeout=15)
    found = result.get("windows")
    return found if isinstance(found, list) else []


def resolve_window(app: str, pid: int | None = None) -> dict | None:
    """Find the frontmost window of an app by name or pid."""
    if pid:
        found = windows(pid)
    else:
        needle = app.casefold()
        found = [w for w in windows() if needle in str(w.get("app_name", "")).casefold()]
    if not found:
        return None
    with_z = [w for w in found if isinstance(w.get("z_index"), int)]
    return max(with_z, key=lambda w: w["z_index"]) if with_z else found[0]


def window_state(pid: int, window_id: int, max_elements: int = 120, query: str | None = None,
                 timeout_ms: int = 2000) -> dict:
    args = {
        "pid": pid,
        "window_id": window_id,
        "max_elements": max_elements,
        "timeout_ms": timeout_ms,
    }
    if query:
        args["query"] = query
    result = tool("get_window_state", args, timeout=40)
    if result.get("degraded") or (not result.get("tree_markdown") and not result.get("ok", True)):
        recycle()
        retry = tool("get_window_state", args, timeout=40)
        if retry.get("tree_markdown"):
            result = retry
    if not result.get("tree_markdown") and not result.get("ok", True):
        return {"ok": False, "error": result.get("refusal", {}).get("message") or result.get("error", "")}
    result["ok"] = True
    result["degraded"] = bool(result.get("degraded"))
    return result


def desktop_state() -> dict:
    result = tool("get_desktop_state", {}, timeout=45)
    ok = bool(result.get("screenshot_png_b64"))
    result["ok"] = ok
    return result


# ------------------------------------------------------------------- actions
def steps(step_list: list[dict], app: str | None = None, observe: bool = True,
          foreground_fallback: bool = True, timeout: float = 75) -> dict:
    payload: dict = {"steps": step_list[:24]}
    if app:
        payload["app"] = app
    if observe:
        payload["observe"] = {}
    if foreground_fallback:
        payload["foreground_fallback"] = True
    return tool("run_steps", payload, timeout=timeout)


def script(body: str, timeout_ms: int = 60000) -> dict:
    """Run one driver script so reads and actions share a session."""
    result = tool("run_script", {"script": body, "timeout_ms": timeout_ms}, timeout=timeout_ms / 1000 + 15)
    if result.get("ok") is False or result.get("code") or result.get("error"):
        return {"ok": False, "error": result.get("error") or result.get("message") or str(result.get("reason", "script failed"))}
    shot = result.get("screenshot_png_b64")
    inner = result.get("value")
    if isinstance(inner, dict) and "value" in inner:
        ok = inner.get("ok", True)
        if ok is False:
            return {"ok": False, "error": str(inner.get("error") or "script error"), "value": inner.get("value")}
        return {"ok": True, "value": inner.get("value"), "screenshot": shot}
    return {"ok": True, "value": inner, "screenshot": shot}


def launch(app: str) -> dict:
    """Launch an app, forcing XWayland for toolkits that need addressing."""
    needle = app.casefold()
    env = os.environ.copy()
    argv: list[str] = []
    force_x11 = any(hint in needle for hint in X11_HINTS)
    if force_x11:
        env["ELECTRON_OZONE_PLATFORM_HINT"] = "x11"
        env["GDK_BACKEND"] = "x11"
    if "chrome" in needle and shutil.which("flatpak"):
        argv = ["flatpak", "run", "com.google.Chrome", "--ozone-platform=x11"]
        command = "flatpak"
    else:
        command = shutil.which(app)
    if command and not argv:
        argv = [command]
        if force_x11 and "code" in needle:
            argv.append("--ozone-platform=x11")
    elif not argv:
        try:
            proc = subprocess.Popen(
                ["gtk-launch", app],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            argv = ["gtk-launch", app]
            del proc
        except OSError:
            return {"ok": False, "error": f"cannot launch {app}"}
    if argv:
        try:
            subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "launched": " ".join(argv)}


def wait_for_window(app: str, timeout: float = 12.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        window = resolve_window(app)
        if window:
            return window
        time.sleep(0.4)
    return None


def recycle() -> bool:
    """Restart the daemon; AT-SPI occasionally drops its registry connection."""
    stop_daemon()
    time.sleep(0.6)
    return ensure_daemon()


def doctor() -> dict:
    result = _call(["check_permissions"], timeout=20)
    return result if isinstance(result, dict) else {}
