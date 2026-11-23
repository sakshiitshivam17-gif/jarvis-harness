"""Host telemetry and read-only system reports."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

from .bus import EventBus
from . import config


def _read(path: str | Path, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return default


def _run(argv: list[str], timeout: float = 4.0) -> str:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        return (proc.stdout or proc.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _cpu_times() -> tuple[int, int]:
    fields = _read("/proc/stat").splitlines()[0].split()[1:]
    values = [int(v) for v in fields] + [0] * (8 - len(fields))
    idle = values[3] + values[4]
    total = sum(values)
    return total, idle


def _net_totals(interface: str) -> tuple[int, int]:
    for line in _read("/proc/net/dev").splitlines():
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        if name.strip() != interface:
            continue
        nums = data.split()
        if len(nums) >= 9:
            return int(nums[0]), int(nums[8])
    return 0, 0


def active_interface() -> str:
    try:
        for line in _read("/proc/net/route").splitlines()[1:]:
            parts = line.split()
            if len(parts) > 2 and parts[1] == "00000000" and parts[2] != "00000000":
                return parts[0]
    except OSError:
        pass
    for name in sorted(os.listdir("/sys/class/net")):
        if name != "lo" and _read(f"/sys/class/net/{name}/operstate") == "up":
            return name
    return ""


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _battery() -> tuple[int | None, str]:
    for root in Path("/sys/class/power_supply").glob("BAT*"):
        capacity = _read(root / "capacity")
        status = _read(root / "status", "Unknown")
        if capacity.isdigit():
            return int(capacity), status
    return None, "Unknown"


def _temperature() -> float | None:
    values: list[float] = []
    for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
        raw = _read(zone / "temp")
        if raw.lstrip("-").isdigit():
            value = int(raw) / 1000.0
            if 5 < value < 130:
                values.append(value)
    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        for label in ("temp1_input", "temp2_input"):
            raw = _read(hwmon / label)
            if raw.lstrip("-").isdigit():
                value = int(raw) / 1000.0
                if 5 < value < 130:
                    values.append(value)
    return round(max(values), 1) if values else None


def _volume() -> tuple[int | None, bool]:
    out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    match = re.search(r"Volume:\s+([0-9.]+)", out)
    if not match:
        return None, False
    return round(float(match.group(1)) * 100), "[MUTED]" in out


def _brightness() -> int | None:
    for backlight in Path("/sys/class/backlight").glob("*"):
        cur = _read(backlight / "brightness")
        maxv = _read(backlight / "max_brightness")
        if cur.isdigit() and maxv.isdigit() and int(maxv) > 0:
            return round(int(cur) / int(maxv) * 100)
    return None


def mpris_players() -> list[str]:
    out = _run(["busctl", "--user", "list", "--no-legend"])
    names = []
    for line in out.splitlines():
        name = line.split(maxsplit=1)[0] if line.strip() else ""
        if name.startswith("org.mpris.MediaPlayer2."):
            names.append(name)
    return names


def now_playing() -> dict:
    players = mpris_players()
    if not players:
        return {}
    name = players[0]
    out = _run(["busctl", "--user", "get-property", name, "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player", "Metadata"], timeout=3)
    title = re.search(r'"xesam:title"\s+s\s+"([^"]*)"', out)
    artist = re.search(r'"xesam:artist"\s+as\s+\d+\s+"([^"]*)"', out)
    status = _run(["busctl", "--user", "get-property", name, "/org/mpris/MediaPlayer2",
                   "org.mpris.MediaPlayer2.Player", "PlaybackStatus"], timeout=3)
    return {
        "player": name,
        "title": title.group(1) if title else "",
        "artist": artist.group(1) if artist else "",
        "status": status.split('"')[1] if '"' in status else "",
    }


def _weather(location: str) -> dict | None:
    query = urllib.parse.quote(location or config.SETTINGS.get("weather_location") or "")
    url = f"https://wttr.in/{query}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis-harness/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        current = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        place = ", ".join(
            part[0]["value"] for part in (area.get("areaName"), area.get("region"), area.get("country")) if part
        )
        return {
            "place": place or location or "your location",
            "temp_c": current.get("temp_C"),
            "feels_c": current.get("FeelsLikeC"),
            "desc": (current.get("weatherDesc") or [{}])[0].get("value", "unknown"),
            "humidity": current.get("humidity"),
            "wind": current.get("windspeedKmph"),
        }
    except (OSError, ValueError, KeyError, IndexError):
        return None


class Sampler(threading.Thread):
    """Continuously collect host telemetry and publish it to the interface."""

    def __init__(self, bus: EventBus, interval: float = 1.5) -> None:
        super().__init__(daemon=True, name="sampler")
        self.bus = bus
        self.interval = interval
        self.stop_event = threading.Event()
        self.history = {
            "cpu": deque(maxlen=64),
            "mem": deque(maxlen=64),
            "down": deque(maxlen=64),
            "up": deque(maxlen=64),
            "temp": deque(maxlen=64),
        }
        self._prev_cpu = _cpu_times()
        self._prev_net = (0, 0)
        self._last_volume: tuple[int | None, bool] = (None, False)
        self._volume_tick = 0
        self._boot_time = time.time()
        self._iface = active_interface()
        self._prev_net = _net_totals(self._iface)
        self._stats: dict = {}
        self._weather_cache: tuple[float, dict | None] = (0.0, None)

    def stop(self) -> None:
        self.stop_event.set()

    def snapshot(self) -> dict:
        return dict(self._stats)

    def weather(self, location: str = "") -> dict | None:
        stamp, cached = self._weather_cache
        if time.time() - stamp < 600 and (not location or location == config.SETTINGS.get("weather_location")):
            return cached
        result = _weather(location)
        self._weather_cache = (time.time(), result)
        return result

    def _collect(self) -> dict:
        now = time.time()
        total, idle = _cpu_times()
        prev_total, prev_idle = self._prev_cpu
        d_total = max(total - prev_total, 1)
        d_idle = max(idle - prev_idle, 0)
        cpu = max(0.0, min(100.0, (1 - d_idle / d_total) * 100))
        self._prev_cpu = (total, idle)

        meminfo = {}
        for line in _read("/proc/meminfo").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meminfo[key] = value.strip()
        mem_total = int(meminfo.get("MemTotal", "1").split()[0])
        mem_avail = int(meminfo.get("MemAvailable", "1").split()[0])
        mem = max(0.0, min(100.0, (1 - mem_avail / max(mem_total, 1)) * 100))

        if self._iface:
            down_total, up_total = _net_totals(self._iface)
            d_down = max(down_total - self._prev_net[0], 0)
            d_up = max(up_total - self._prev_net[1], 0)
            self._prev_net = (down_total, up_total)
            span = max(now - getattr(self, "_last_collect", now - self.interval), 0.2)
            down_rate = d_down / span / 1024
            up_rate = d_up / span / 1024
        else:
            down_rate = up_rate = 0.0
        self._last_collect = now

        battery, charge_state = _battery()
        temp = _temperature()
        disk = shutil.disk_usage("/")
        self._volume_tick += 1
        if self._volume_tick >= 4:
            self._volume_tick = 0
            self._last_volume = _volume()
        volume, muted = self._last_volume

        for key, value in (("cpu", cpu), ("mem", mem), ("down", down_rate), ("up", up_rate), ("temp", temp or 0)):
            self.history[key].append(round(value, 1))

        return {
            "cpu": round(cpu, 1),
            "mem": round(mem, 1),
            "mem_used_gb": round((mem_total - mem_avail) / 1024 / 1024, 1),
            "mem_total_gb": round(mem_total / 1024 / 1024, 1),
            "swap": round(float(meminfo.get("SwapFree", "0").split()[0]) / max(float(meminfo.get("SwapTotal", "1").split()[0]), 1) * 100, 1),
            "disk": round(disk.used / disk.total * 100, 1),
            "disk_free_gb": round(disk.free / 1024**3, 1),
            "temp": temp,
            "battery": battery,
            "charging": charge_state,
            "down": round(down_rate, 1),
            "up": round(up_rate, 1),
            "net_if": self._iface,
            "uptime": int(now - self._boot_time),
            "load": list(os.getloadavg()),
            "volume": volume,
            "muted": muted,
            "brightness": _brightness(),
            "ip": local_ip(),
            "host": socket.gethostname(),
            "chip": _cpu_model(),
            "os": _os_name(),
            "now": now,
            "history": {key: list(values) for key, values in self.history.items()},
        }

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._stats = self._collect()
                self.bus.publish("stats", self._stats)
            except Exception as exc:  # telemetry should never kill the server
                self.bus.log("SYS", f"Telemetry fault: {exc}", "warn")
            self.stop_event.wait(self.interval)


def _cpu_model() -> str:
    for line in _read("/proc/cpuinfo").splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "Unknown processor"


def _os_name() -> str:
    for line in _read("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "Linux"


def system_report(stats: dict, metric: str) -> str:
    """Spoken plain-text answers for local status questions."""
    if metric == "cpu":
        return f"CPU utilization is {stats.get('cpu', 0):.1f} percent, sir."
    if metric == "memory":
        return (
            f"Memory is at {stats.get('mem', 0):.1f} percent — "
            f"{stats.get('mem_used_gb', 0)} of {stats.get('mem_total_gb', 0)} gigabytes in use."
        )
    if metric == "disk":
        return f"Root storage is {stats.get('disk', 0):.1f} percent full, with {stats.get('disk_free_gb', 0)} gigabytes free."
    if metric == "battery":
        charge = stats.get("battery")
        if charge is None:
            return "No battery is detected, sir. Mains power only."
        return f"Battery is at {charge} percent and {str(stats.get('charging', '')).lower()}."
    if metric == "temperature":
        temp = stats.get("temp")
        return f"Core temperature is {temp} degrees Celsius, sir." if temp else "No thermal sensor is reporting, sir."
    if metric == "network":
        return (
            f"Network interface {stats.get('net_if') or 'none'} is active. "
            f"Local address {stats.get('ip')}. Downstream {stats.get('down', 0):.1f} kilobytes per second."
        )
    if metric == "volume":
        vol = stats.get("volume")
        return f"Output volume is {vol} percent{', muted' if stats.get('muted') else ''}, sir." if vol is not None else "I can't read the audio mixer, sir."
    if metric == "uptime":
        seconds = int(stats.get("uptime", 0))
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        return f"Reactor uptime is {days} days, {hours} hours and {minutes} minutes, sir."
    return "All monitored systems are nominal, sir."


def full_status(stats: dict) -> str:
    battery = stats.get("battery")
    battery_text = f"battery {battery} percent" if battery is not None else "mains power"
    temp = stats.get("temp")
    temp_text = f"{temp} degrees" if temp else "thermals nominal"
    return (
        f"All systems are online, sir. CPU {stats.get('cpu', 0):.0f} percent, "
        f"memory {stats.get('mem', 0):.0f} percent, {battery_text}, {temp_text}. "
        f"Neural core {'linked' if config.capabilities()['llm'] else 'offline'}. Awaiting orders."
    )
