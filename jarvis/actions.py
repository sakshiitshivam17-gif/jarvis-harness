"""Real PC actions executed by the local harness."""

from __future__ import annotations

import ast
import html as html_lib
import json
import math
import os
import random
import re
import shlex
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config
from .bus import EventBus
from .intent import HELP_SECTIONS
from .screen import capture_screen
from .system import Sampler, system_report, full_status, now_playing, mpris_players

HOME = Path.home()

APPS: dict[str, list[str]] = {
    "chrome": ["flatpak", "run", "com.google.Chrome"],
    "google chrome": ["flatpak", "run", "com.google.Chrome"],
    "browser": ["flatpak", "run", "com.google.Chrome"],
    "terminal": ["kgx"],
    "console": ["kgx"],
    "files": ["nautilus"],
    "file manager": ["nautilus"],
    "nautilus": ["nautilus"],
    "calculator": ["gnome-calculator"],
    "calc": ["gnome-calculator"],
    "settings": ["gnome-control-center"],
    "control center": ["gnome-control-center"],
    "code": ["code"],
    "vs code": ["code"],
    "visual studio code": ["code"],
    "text editor": ["gnome-text-editor"],
    "calendar": ["gnome-calendar"],
    "weather": ["gnome-weather"],
    "maps": ["gnome-maps"],
    "music": ["gnome-music"],
    "monitor": ["gnome-system-monitor"],
    "system monitor": ["gnome-system-monitor"],
    "disks": ["gnome-disks"],
    "software": ["gnome-software"],
    "camera": ["gnome-camera"],
    "clocks": ["gnome-clocks"],
    "contacts": ["gnome-contacts"],
    "logs": ["gnome-logs"],
}

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "whatsapp": "https://web.whatsapp.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "prime video": "https://www.primevideo.com",
    "hotstar": "https://www.hotstar.com",
    "spotify": "https://open.spotify.com",
    "soundcloud": "https://soundcloud.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "deepseek": "https://chat.deepseek.com",
    "drive": "https://drive.google.com",
    "maps website": "https://maps.google.com",
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",
    "wikipedia": "https://www.wikipedia.org",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "leetcode": "https://leetcode.com",
    "huggingface": "https://huggingface.co",
    "hugging face": "https://huggingface.co",
    "arxiv": "https://arxiv.org",
    "news": "https://news.google.com",
    "calendar web": "https://calendar.google.com",
}

APP_SITE_FALLBACKS = {"spotify", "discord", "slack", "telegram", "notion", "netflix"}


def _run(argv: list[str], timeout: float = 10.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        return proc.returncode, (proc.stdout or proc.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _spawn(argv: list[str]) -> None:
    subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ.copy(),
    )


def _desktop_dirs() -> list[Path]:
    dirs = [HOME / ".local" / "share" / "applications", Path("/usr/share/applications")]
    flatpak = Path("/var/lib/flatpak/exports/share/applications")
    if flatpak.exists():
        dirs.insert(0, flatpak)
    return dirs


def _desktop_field(path: Path, field: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(f"{field}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def resolve_desktop(target: str) -> Path | None:
    needle = target.lower().strip()
    best: tuple[int, Path] | None = None
    for directory in _desktop_dirs():
        if not directory.exists():
            continue
        for entry in directory.glob("*.desktop"):
            name = _desktop_field(entry, "Name").lower()
            keywords = _desktop_field(entry, "Keywords").lower()
            generic = _desktop_field(entry, "GenericName").lower()
            if _desktop_field(entry, "NoDisplay").lower() == "true":
                continue
            score = 0
            if name == needle:
                score = 10
            elif name.startswith(needle):
                score = 7
            elif needle in name:
                score = 5
            elif needle in keywords or needle in generic:
                score = 3
            if score and (best is None or score > best[0]):
                best = (score, entry)
    return best[1] if best else None


def launch_desktop(path: Path) -> bool:
    if shutil.which("gtk-launch"):
        code, _ = _run(["gtk-launch", path.stem])
        if code == 0:
            return True
    if shutil.which("gio"):
        code, _ = _run(["gio", "launch", str(path)])
        if code == 0:
            return True
    return False


def open_url(url: str) -> None:
    if shutil.which("flatpak") and "com.google.Chrome" in _flatpak_ids():
        _spawn(["flatpak", "run", "com.google.Chrome", url])
        return
    if shutil.which("xdg-open"):
        _spawn(["xdg-open", url])
        return
    _spawn(["gio", "open", url])


_FLATPAK_CACHE: set[str] | None = None


def _flatpak_ids() -> set[str]:
    global _FLATPAK_CACHE
    if _FLATPAK_CACHE is None:
        _FLATPAK_CACHE = set()
        if shutil.which("flatpak"):
            code, out = _run(["flatpak", "list", "--app", "--columns=application"], timeout=5)
            if code == 0:
                _FLATPAK_CACHE = set(out.split())
    return _FLATPAK_CACHE


def clean_target(target: str) -> str:
    target = re.sub(r"\b(app|application|program|the)\b", " ", target.lower())
    return re.sub(r"\s+", " ", target).strip()


_YT_CACHE: dict[str, tuple[float, dict | None]] = {}


def _http_json(url: str, timeout: float = 10.0) -> dict | None:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def search_youtube(query: str) -> dict | None:
    """Resolve the first YouTube result so "play X" actually plays X."""
    key = query.casefold().strip()
    cached = _YT_CACHE.get(key)
    if cached and time.time() - cached[0] < 600:
        return cached[1]
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    result = None
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="replace")
        ids = []
        for match in re.finditer(r'"videoId":"([A-Za-z0-9_-]{11})"', body):
            video_id = match.group(1)
            if video_id not in ids:
                ids.append(video_id)
            if len(ids) >= 4:
                break
        if ids:
            video_id = ids[0]
            watch = f"https://www.youtube.com/watch?v={video_id}"
            title = ""
            meta = _http_json("https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": watch, "format": "json"}))
            if meta:
                title = html_lib.unescape(str(meta.get("title", ""))).strip()
            result = {
                "id": video_id,
                "url": watch + "&autoplay=1",
                "title": title[:110] or query,
            }
    except (OSError, ValueError):
        result = None
    _YT_CACHE[key] = (time.time(), result)
    return result


def _search_locations() -> list[Path]:
    home = Path.home()
    return [
        home / "Desktop", home / "Documents", home / "Downloads",
        home / "projects", home / "PycharmProjects", home / "Videos",
        home / "Pictures", home / "Music", config.BASE_DIR.parent,
    ]


def _bookmark_url(target: str) -> str | None:
    """Search the user's Chrome bookmarks when an app/name isn't installed."""
    needle = target.casefold().strip()
    candidates = [
        HOME / ".config" / "google-chrome" / "Default" / "Bookmarks",
        HOME / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome" / "Default" / "Bookmarks",
        HOME / ".config" / "chromium" / "Default" / "Bookmarks",
        HOME / ".config" / "BraveSoftware" / "Brave-Browser" / "Default" / "Bookmarks",
    ]
    best: tuple[int, str] | None = None

    def walk(node):
        nonlocal best
        if isinstance(node, dict):
            if node.get("type") == "url" and node.get("url"):
                name = str(node.get("name", "")).casefold()
                score = 10 if name == needle else 6 if name.startswith(needle) else 4 if needle in name else 0
                if score and (best is None or score > best[0]):
                    best = (score, str(node["url"]))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for path in candidates:
        try:
            if path.exists():
                walk(json.loads(path.read_text(encoding="utf-8", errors="ignore")))
        except (OSError, ValueError):
            continue
    return best[1] if best else None


def find_local_path(target: str) -> Path | None:
    """Find an app project, folder or file anywhere in the usual user spaces."""
    raw = target.strip().strip('"').strip("'")
    if not raw:
        return None
    direct = Path(raw).expanduser()
    if (raw.startswith(("~", "/", "./")) or "/" in raw) and direct.exists():
        return direct

    needle = raw.casefold()
    if not needle:
        return None
    best: tuple[int, Path] | None = None
    seen = 0
    deep = {"node_modules", ".git", ".venv", "venv", "__pycache__", "target", "build", "dist", ".cache", "site-packages", ".npm"}
    for root in _search_locations():
        if not root.exists() or not root.is_dir():
            continue
        try:
            for current, dirs, files in os.walk(root):
                depth = len(Path(current).relative_to(root).parts)
                if depth >= 4:
                    dirs[:] = []
                dirs[:] = [d for d in dirs if d not in deep and not d.startswith(".")]
                for name in files + dirs:
                    seen += 1
                    if seen > 14000:
                        break
                    lowered = name.casefold()
                    score = 0
                    if lowered == needle:
                        score = 100
                    elif Path(lowered).stem == needle:
                        score = 92
                    elif lowered.startswith(needle):
                        score = 74
                    elif needle in lowered:
                        score = 52
                    elif len(needle.split()) > 1 and all(part in lowered for part in needle.split()):
                        score = 40
                    if score:
                        candidate = Path(current) / name
                        if candidate.is_dir() and needle in {"project", "projects"}:
                            continue
                        if best is None or score > best[0]:
                            best = (score, candidate)
                if seen > 14000:
                    break
        except OSError:
            continue
        if seen > 14000 or (best and best[0] >= 100):
            break
    return best[1] if best else None


_FLATPAK_APPS: list[tuple[str, str]] | None = None


def _flatpak_apps() -> list[tuple[str, str]]:
    global _FLATPAK_APPS
    if _FLATPAK_APPS is None:
        _FLATPAK_APPS = []
        if shutil.which("flatpak"):
            code, out = _run(["flatpak", "list", "--app", "--columns=application,name"], timeout=6)
            if code == 0:
                for line in out.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        _FLATPAK_APPS.append((parts[0], parts[1]))
    return _FLATPAK_APPS


def find_flatpak_app(target: str) -> tuple[str, str] | None:
    needle = target.casefold()
    best = None
    for app_id, name in _flatpak_apps():
        lowered = name.casefold()
        score = 10 if lowered == needle else 6 if lowered.startswith(needle) else 4 if needle in lowered else 0
        if score and (best is None or score > best[0]):
            best = (score, app_id, name)
    return (best[1], best[2]) if best else None


class Actions:
    def __init__(self, bus: EventBus, sampler: Sampler) -> None:
        self.bus = bus
        self.sampler = sampler
        self.timers: dict[str, threading.Timer] = {}
        self._stop = threading.Event()

    # ------------------------------------------------------------------ util
    def _ok(self, action: str, say: str, detail: str = "", data: dict | None = None) -> dict:
        if detail:
            self.bus.log("ACT", detail)
        return {"ok": True, "action": action, "say": say, "detail": detail, "data": data or {}}

    def _fail(self, action: str, say: str, detail: str = "") -> dict:
        self.bus.log("ACT", detail or say, "warn")
        return {"ok": False, "action": action, "say": say, "detail": detail, "data": {}}

    # --------------------------------------------------------------- execute
    def execute(self, action: str, args: dict) -> dict:
        handler = getattr(self, f"do_{action}", None)
        if not handler:
            return self._fail(action, "That module isn't fitted yet, sir.")
        try:
            return handler(args)
        except Exception as exc:
            return self._fail(action, f"That action faulted, sir: {exc}", str(exc))

    # ------------------------------------------------------------- knowledge
    def do_empty(self, args):
        return self._ok("empty", "")

    def do_confirm(self, args):
        return self._ok("confirm", "Confirmed, sir.")

    def do_cancel(self, args):
        return self._ok("cancel", random.choice(config.VOICE_LINES["confirm_cancel"]))

    def do_greet(self, args):
        hour = datetime.now().hour
        part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
        return self._ok("greet", f"Good {part}, sir. All systems are standing by.")

    def do_thanks(self, args):
        return self._ok("thanks", "At your service, sir.")

    def do_identity(self, args):
        return self._ok(
            "identity",
            "I am JARVIS — your local computer harness. Voice control, telemetry, and a neural core, all wired to this machine, sir.",
        )

    def do_wellbeing(self, args):
        stats = self.sampler.snapshot()
        return self._ok("wellbeing", f"Operating within normal parameters, sir. CPU at {stats.get('cpu', 0):.0f} percent. Ready when you are.")

    def do_wake(self, args):
        return self._ok("wake", random.choice(config.VOICE_LINES["wake"]), "Voice link woke")

    def do_standby(self, args):
        return self._ok("standby", random.choice(config.VOICE_LINES["sleep"]), "Voice link on standby", {"mode": "standby"})

    def do_quiet(self, args):
        return self._ok("quiet", "", "Voice output silenced")

    def do_clear_feed(self, args):
        return self._ok("clear_feed", "Transcript cleared, sir.")

    def do_help(self, args):
        return self._ok(
            "help",
            "The command matrix is on screen, sir. Apps, system control, timers, notes and machine commands are all online.",
            "Displayed command matrix",
            {"sections": HELP_SECTIONS},
        )

    # ------------------------------------------------------------- telemetry
    def do_time(self, args):
        return self._ok("time", datetime.now().strftime("It is %I:%M %p, sir."), datetime.now().strftime("%H:%M:%S"))

    def do_date(self, args):
        return self._ok("date", datetime.now().strftime("Today is %A, %d %B %Y, sir."))

    def do_status(self, args):
        return self._ok("status", full_status(self.sampler.snapshot()))

    def do_system_metric(self, args):
        metric = args.get("metric", "")
        return self._ok("system_metric", system_report(self.sampler.snapshot(), metric), data={"metric": metric})

    def do_weather(self, args):
        location = args.get("location", "")
        data = self.sampler.weather(location)
        if not data:
            return self._fail("weather", "The weather uplink is unavailable, sir.")
        return self._ok(
            "weather",
            f"{data['place']}: {data['desc']}, {data['temp_c']} degrees Celsius, feels like {data['feels_c']}. Humidity {data['humidity']} percent.",
            f"Weather for {data['place']}",
        )

    def do_now_playing(self, args):
        info = now_playing()
        if not info or not info.get("title"):
            return self._ok("now_playing", "I can't identify an active track, sir.")
        return self._ok("now_playing", f"{info['title']} by {info.get('artist') or 'an unknown artist'}, sir.")

    # ------------------------------------------------------------ apps/sites
    def do_open(self, args):
        target = clean_target(args.get("target", ""))
        if not target:
            return self._fail("open", "Open what, sir?")
        project_mode = False
        for prefix in ("project ", "folder ", "directory ", "dir ", "file "):
            if target.startswith(prefix):
                project_mode = prefix == "project "
                target = target[len(prefix):].strip()
                break
        if not target:
            return self._fail("open", "Open what, sir?")
        if target.startswith(("http://", "https://")):
            return self.do_open_url({"url": target, "label": target})
        if target in SITES:
            return self.do_open_url({"url": SITES[target], "label": target})
        if target in APPS:
            return self.do_open_app({"app": target})
        desktop = resolve_desktop(target)
        if desktop and launch_desktop(desktop):
            return self._ok("open", f"Opening {_desktop_field(desktop, 'Name') or target}, sir.", f"Launched {desktop.name}")

        local = find_local_path(target)
        if local:
            if project_mode and local.is_dir() and shutil.which("code"):
                _spawn(["code", str(local)])
                return self._ok("open", f"Opening project {local.name} in VS Code, sir.", str(local), {"path": str(local)})
            if shutil.which("xdg-open"):
                _spawn(["xdg-open", str(local)])
            else:
                _spawn(["gio", "open", str(local)])
            kind = "folder" if local.is_dir() else "file"
            return self._ok("open", f"Opening {kind} {local.name}, sir.", str(local), {"path": str(local)})

        bookmark = _bookmark_url(target)
        if bookmark:
            return self.do_open_url({"url": bookmark, "label": target})

        flatpak = find_flatpak_app(target)
        if flatpak:
            _spawn(["flatpak", "run", flatpak[0]])
            return self._ok("open", f"Opening {flatpak[1]}, sir.", f"flatpak run {flatpak[0]}", {"app": flatpak[0]})

        if target in APP_SITE_FALLBACKS:
            return self.do_open_url({"url": f"https://{target}.com", "label": target})
        if "." in target and " " not in target:
            return self.do_open_url({"url": f"https://{target}", "label": target})
        result = self.do_search({"query": target})
        result["say"] = f"I couldn't find {target} locally, sir — pulling up a web search."
        return result

    def do_open_app(self, args):
        raw = clean_target(args.get("app", ""))
        fallback_site = args.get("site")
        if fallback_site:
            return self.do_open_url({"url": fallback_site, "label": raw})
        if raw in SITES:
            return self.do_open_url({"url": SITES[raw], "label": raw})
        command = APPS.get(raw)
        if command:
            if shutil.which(command[0]) or command[0] == "flatpak":
                _spawn(command)
                return self._ok("open_app", f"Opening {raw}, sir.", f"Launched {' '.join(command)}", {"app": raw})
            return self._fail("open_app", f"{raw} isn't installed, sir.")
        desktop = resolve_desktop(raw)
        if desktop and launch_desktop(desktop):
            return self._ok("open_app", f"Opening {_desktop_field(desktop, 'Name') or raw}, sir.", f"Launched {desktop.name}", {"app": raw})
        for candidate in (raw, raw.replace(" ", "-"), raw.replace(" ", "")):
            binary = shutil.which(candidate)
            if binary:
                _spawn([binary])
                return self._ok("open_app", f"Launching {candidate}, sir.", binary, {"app": candidate})
        flatpak = find_flatpak_app(raw)
        if flatpak:
            _spawn(["flatpak", "run", flatpak[0]])
            return self._ok("open_app", f"Opening {flatpak[1]}, sir.", f"flatpak run {flatpak[0]}", {"app": flatpak[0]})
        bookmark = _bookmark_url(raw)
        if bookmark:
            return self.do_open_url({"url": bookmark, "label": raw})
        if raw in APP_SITE_FALLBACKS:
            return self.do_open_url({"url": f"https://{raw}.com", "label": raw})
        return self.do_open({"target": raw})

    def do_open_url(self, args):
        url = args.get("url", "").strip()
        if not re.match(r"^https?://", url):
            url = "https://" + url
        open_url(url)
        label = args.get("label") or urllib.parse.urlparse(url).netloc.removeprefix("www.")
        return self._ok("open_url", f"Opening {label}, sir.", f"URL {url}", {"url": url})

    def do_open_path(self, args):
        path = Path(args.get("path", "~")).expanduser()
        if not path.exists():
            return self._fail("open_path", f"{path} doesn't exist, sir.")
        if shutil.which("xdg-open"):
            _spawn(["xdg-open", str(path)])
        else:
            _spawn(["gio", "open", str(path)])
        return self._ok("open_path", f"Opening {path.name or 'home'}, sir.", str(path))

    def do_close_app(self, args):
        raw = clean_target(args.get("app", ""))
        patterns = {
            "chrome": "com.google.Chrome", "browser": "com.google.Chrome",
            "code": "code", "files": "nautilus", "terminal": "kgx",
            "calculator": "gnome-calculator", "settings": "gnome-control-center",
            "spotify": "spotify", "music": "gnome-music",
        }
        pattern = patterns.get(raw)
        if not pattern:
            desktop = resolve_desktop(raw)
            if desktop:
                exec_line = _desktop_field(desktop, "Exec")
                match = re.search(r"(?:flatpak run )?([\w.-]+)", exec_line)
                pattern = match.group(1) if match else raw
            else:
                pattern = raw
        if not pattern:
            return self._fail("close_app", "Close what, sir?")
        if pattern.startswith("com.") and shutil.which("flatpak"):
            code, out = _run(["flatpak", "kill", pattern])
            if code == 0:
                return self._ok("close_app", f"Closing {raw}, sir.")
        code, out = _run(["pkill", "-f", "-i", pattern])
        if code == 0:
            return self._ok("close_app", f"Closing {raw}, sir.")
        return self._fail("close_app", f"I couldn't find a running {raw}, sir.", out)

    # ---------------------------------------------------------------- search
    def do_search(self, args):
        query = args.get("query", "").strip()
        if not query:
            return self._fail("search", "What should I search for, sir?")
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        open_url(url)
        return self._ok("search", f"Searching the web for {query}, sir.", f"Google: {query}", {"query": query})

    def do_youtube(self, args):
        query = args.get("query", "").strip()
        if not query:
            return self._fail("youtube", "What should I play, sir?")
        found = search_youtube(query)
        if found:
            open_url(found["url"])
            return self._ok(
                "youtube",
                f"Playing {found['title']} on YouTube, sir.",
                f"YouTube video {found['id']}: {found['title']}",
                {"query": query, "url": found["url"], "title": found["title"], "video": found["id"]},
            )
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        open_url(url)
        return self._ok("youtube", f"I couldn't pin the first video, sir — here are the results for {query}.", f"YouTube search: {query}", {"query": query})

    def do_music(self, args):
        if mpris_players():
            return self.do_media({"mode": "play"})
        return self.do_open_url({"url": "https://music.youtube.com", "label": "YouTube Music"})

    # ---------------------------------------------------------------- volume
    def _volume_state(self) -> tuple[int | None, bool]:
        code, out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        match = re.search(r"Volume:\s+([0-9.]+)", out)
        if not match:
            return None, False
        return round(float(match.group(1)) * 100), "[MUTED]" in out

    def do_volume(self, args):
        mode = args.get("mode", "status")
        if not shutil.which("wpctl"):
            return self._fail("volume", "The audio mixer isn't available, sir.")
        if mode == "mute":
            _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"])
            return self._ok("volume", "Audio muted, sir.")
        if mode == "unmute":
            _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
            return self._ok("volume", "Audio restored, sir.")
        if mode == "set":
            value = max(0, min(100, int(args.get("value", 50))))
            _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
            _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value}%"])
            return self._ok("volume", f"Volume set to {value} percent, sir.")
        if mode in ("up", "down"):
            amount = int(args.get("value", 10))
            sign = "+" if mode == "up" else "-"
            _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
            _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{amount}%{sign}"])
            vol, _ = self._volume_state()
            return self._ok("volume", f"Volume {'raised' if mode == 'up' else 'lowered'}{f' to {vol} percent' if vol is not None else ''}, sir.")
        vol, muted = self._volume_state()
        return self._ok("volume", f"Volume is at {vol} percent{', muted' if muted else ''}, sir." if vol is not None else "I can't read the mixer, sir.")

    # ------------------------------------------------------------ brightness
    def _backlight(self) -> tuple[Path, int, int] | None:
        for root in Path("/sys/class/backlight").glob("*"):
            try:
                current = int((root / "brightness").read_text().strip())
                maximum = int((root / "max_brightness").read_text().strip())
                return root / "brightness", current, maximum
            except (OSError, ValueError):
                continue
        return None

    def do_brightness(self, args):
        mode = args.get("mode", "status")
        backlight = self._backlight()
        if not backlight:
            code, out = _run(["busctl", "--user", "call", "org.gnome.SettingsDaemon.Power",
                              "/org/gnome/SettingsDaemon/Power", "org.gnome.SettingsDaemon.Power.Screen",
                              "SetPercentage", "u", str(int(args.get("value", 50)))])
            if code == 0:
                return self._ok("brightness", "Display brightness adjusted, sir.")
            return self._fail("brightness", "No brightness controller responded, sir.", out)
        file, current, maximum = backlight
        percent = round(current / maximum * 100)
        if mode == "set":
            target = max(5, min(100, int(args.get("value", 50))))
        elif mode == "up":
            target = min(100, percent + int(args.get("value", 10)))
        elif mode == "down":
            target = max(5, percent - int(args.get("value", 10)))
        else:
            return self._ok("brightness", f"Screen brightness is {percent} percent, sir.")
        raw = round(target / 100 * maximum)
        code, _ = _run([
            "busctl", "call", "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
            "org.freedesktop.login1.Session", "SetBrightness", "ssu",
            "backlight", file.parent.name, str(raw),
        ])
        if code != 0:
            try:
                file.write_text(str(raw))
            except OSError as exc:
                if shutil.which("brightnessctl"):
                    _run(["brightnessctl", "set", f"{target}%"])
                else:
                    return self._fail("brightness", "Brightness is locked down, sir.", str(exc))
        return self._ok("brightness", f"Brightness set to {target} percent, sir.")

    # ----------------------------------------------------------------- media
    def do_media(self, args):
        mode = args.get("mode", "play")
        players = mpris_players()
        if not players:
            if mode == "play":
                return self.do_open_url({"url": "https://music.youtube.com", "label": "YouTube Music"})
            return self._fail("media", "No media session is active, sir.")
        name = players[0]
        method = {"play": "Play", "pause": "Pause", "next": "Next", "previous": "Previous", "stop": "Stop"}.get(mode, "PlayPause")
        code, out = _run(["busctl", "--user", "call", name, "/org/mpris/MediaPlayer2",
                          "org.mpris.MediaPlayer2.Player", method])
        if code != 0:
            return self._fail("media", "The media session refused the command, sir.", out)
        word = {"play": "Playing", "pause": "Paused", "next": "Skipped forward", "previous": "Skipped back", "stop": "Stopped"}.get(mode, "Media updated")
        return self._ok("media", f"{word}, sir.")

    # ------------------------------------------------------------- machine
    def do_lock(self, args):
        code, out = _run(["loginctl", "lock-session"])
        if code != 0:
            return self._fail("lock", "The lock command failed, sir.", out)
        return self._ok("lock", "Locking the session, sir.")

    def do_suspend(self, args):
        def later():
            time.sleep(2.2)
            _run(["systemctl", "suspend"], timeout=15)
        threading.Thread(target=later, daemon=True).start()
        return self._ok("suspend", "Suspending the machine, sir. Good night.")

    def do_shutdown(self, args):
        def later():
            time.sleep(3.5)
            _run(["systemctl", "poweroff"], timeout=20)
        threading.Thread(target=later, daemon=True).start()
        return self._ok("shutdown", "Powering down the reactor now. Goodbye, sir.", "Shutdown scheduled")

    def do_restart(self, args):
        def later():
            time.sleep(3.5)
            _run(["systemctl", "reboot"], timeout=20)
        threading.Thread(target=later, daemon=True).start()
        return self._ok("restart", "Restarting the system, sir. See you on the other side.", "Restart scheduled")

    def do_logout(self, args):
        def later():
            time.sleep(2.0)
            _run(["loginctl", "terminate-session", str(os.getsid(0))], timeout=15)
        threading.Thread(target=later, daemon=True).start()
        return self._ok("logout", "Signing out, sir.")

    def do_screenshot(self, args):
        target = config.DATA_DIR / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
        captured = capture_screen(target)
        if captured:
            return self._ok("screenshot", "Screen captured, sir.", str(captured), {"path": str(captured), "image": "/api/screen/latest?t=" + str(int(time.time()))})
        return self._fail("screenshot", "The screen capture module was blocked, sir.")

    def do_empty_trash(self, args):
        code, out = _run(["gio", "trash", "--empty"])
        if code != 0:
            return self._fail("empty_trash", "Couldn't empty the trash, sir.", out)
        return self._ok("empty_trash", "Trash emptied, sir.")

    # --------------------------------------------------------------- radios
    def do_wifi(self, args):
        state = args.get("state", "status")
        if not shutil.which("nmcli"):
            return self._fail("wifi", "NetworkManager isn't available, sir.")
        if state == "status":
            code, out = _run(["nmcli", "-t", "-f", "WIFI", "general"])
            return self._ok("wifi", f"Wi-Fi radio is {'enabled' if 'enabled' in out else 'disabled'}, sir.")
        code, out = _run(["nmcli", "radio", "wifi", state])
        if code != 0:
            return self._fail("wifi", "The Wi-Fi radio didn't respond, sir.", out)
        return self._ok("wifi", f"Wi-Fi turned {state}, sir.")

    def do_bluetooth(self, args):
        state = args.get("state", "status")
        if not shutil.which("rfkill"):
            return self._fail("bluetooth", "The Bluetooth switch isn't available, sir.")
        code, out = _run(["rfkill", "list", "bluetooth"])
        if "Bluetooth" not in out:
            return self._fail("bluetooth", "No Bluetooth radio detected, sir.")
        if state != "status":
            _run(["rfkill", {"on": "unblock", "off": "block"}.get(state, "list"), "bluetooth"])
        blocked = "Soft blocked: yes" in out
        return self._ok("bluetooth", f"Bluetooth is {'off' if blocked else 'on'}, sir" if state == "status" else f"Bluetooth turned {state}, sir.")

    def do_dnd(self, args):
        wanted = "false" if args.get("state") == "on" else "true"
        code, out = _run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", wanted])
        if code != 0:
            return self._fail("dnd", "Notification settings are read-only right now, sir.", out)
        return self._ok("dnd", f"Do not disturb {'engaged' if wanted == 'false' else 'released'}, sir.")

    def do_night_light(self, args):
        wanted = "true" if args.get("state", "on") == "on" else "false"
        code, out = _run(["gsettings", "set", "org.gnome.settings-daemon.plugins.color", "night-light-enabled", wanted])
        if code != 0:
            return self._fail("night_light", "Night light settings are read-only right now, sir.", out)
        return self._ok("night_light", f"Night light {'engaged' if wanted == 'true' else 'disengaged'}, sir.")

    # --------------------------------------------------------------- timers
    def do_timer(self, args):
        seconds = int(args.get("seconds", 0))
        if seconds <= 0:
            return self._fail("timer", "How long should the timer run, sir?")
        label = args.get("label", "").strip()
        token = f"t{int(time.time() * 1000)}"
        human = _human_duration(seconds)

        def fire():
            self.timers.pop(token, None)
            self.bus.log("TIMER", f"Timer elapsed ({human}{': ' + label if label else ''})", "warn")
            self.bus.publish("timer_fired", {"label": label, "seconds": seconds})

        timer = threading.Timer(seconds, fire)
        timer.daemon = True
        self.timers[token] = timer
        timer.start()
        return self._ok("timer", f"Timer set for {human}{f', to {label}' if label else ''}, sir.", f"Timer {token}: {human}", {"timer": token, "seconds": seconds})

    def do_timer_status(self, args):
        if not self.timers:
            return self._ok("timer_status", "No timers are running, sir.")
        return self._ok("timer_status", f"You have {len(self.timers)} active timer{'' if len(self.timers) == 1 else 's'}, sir.")

    # ---------------------------------------------------------------- notes
    def do_note(self, args):
        text = args.get("text", "").strip()
        if not text:
            return self._fail("note", "What should I remember, sir?")
        config.ensure_dirs()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with config.NOTES_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"- **{timestamp}** — {text}\n")
        return self._ok("note", f"Noted, sir: {text}.", text)

    def do_read_notes(self, args):
        config.ensure_dirs()
        if not config.NOTES_FILE.exists():
            return self._ok("read_notes", "You haven't dictated any notes yet, sir.")
        notes = [line.strip("- ").strip() for line in config.NOTES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        recent = notes[-5:]
        if not recent:
            return self._ok("read_notes", "Your notebook is empty, sir.")
        preamble = f"Your last {len(recent)} notes, sir. " if len(recent) > 1 else "Your note, sir. "
        spoken = " ".join(
            re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}\s*—\s*", "", re.sub(r"\*\*", "", n))
            for n in recent
        )
        return self._ok("read_notes", preamble + spoken, data={"notes": recent})

    def do_clear_notes(self, args):
        config.ensure_dirs()
        config.NOTES_FILE.write_text("", encoding="utf-8")
        return self._ok("clear_notes", "Notebook wiped, sir.")

    # ------------------------------------------------------------ calculator
    def do_calculate(self, args):
        expression = args.get("expression", "").strip().replace("^", "**")
        try:
            value = _safe_eval(expression)
        except Exception:
            return self._fail("calculate", f"I couldn't evaluate {expression}, sir.")
        pretty = f"{value:,.6g}"
        return self._ok("calculate", f"{expression} equals {pretty}, sir.", data={"value": value})

    # ---------------------------------------------------------------- shell
    def do_shell(self, args):
        command = args.get("command", "").strip()
        if not command:
            return self._fail("shell", "What command should I run, sir?")
        code, out = _run(["/bin/bash", "-lc", command], timeout=30)
        trimmed = out[-1600:] if out else ""
        if code != 0:
            return self._fail("shell", f"The command exited with code {code}, sir.", trimmed or "No output")
        summary = trimmed or "Confirmed, sir."
        spoken = "Command executed, sir."
        return self._ok("shell", spoken, summary, {"stdout": trimmed, "code": code, "command": command})

    # ----------------------------------------------------------------- stop
    def stop(self):
        self._stop.set()
        for timer in list(self.timers.values()):
            timer.cancel()
        self.timers.clear()


def _human_duration(seconds: int) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " ".join(parts)


def _safe_eval(expression: str) -> float:
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub,
               ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd, ast.FloorDiv, ast.Call, ast.Name)
    tree = ast.parse(expression, mode="eval")

    def walk(node):
        if not isinstance(node, allowed):
            raise ValueError("unsupported expression")
        for child in ast.iter_child_nodes(node):
            walk(child)
    walk(tree.body)
    env = {k: getattr(math, k) for k in ("sqrt", "sin", "cos", "tan", "log", "log10", "pi", "e") if hasattr(math, k)}
    return eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, env)
