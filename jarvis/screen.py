"""Screen capture and on-device visual reading.

The harness captures the whole desktop through the XDG portal (no browser
screen-share permission needed), then extracts text with RapidOCR. When a
local vision model is available in Ollama it is used as a fallback for
purely visual questions.
"""

from __future__ import annotations

import base64
import threading
import time
from pathlib import Path

from . import config

SCREEN_DIR = config.DATA_DIR / "screen"
LATEST = SCREEN_DIR / "latest.png"


def capture_screen(target: Path | None = None) -> Path | None:
    """Take a full-screen shot via the desktop portal, falling back to common tools."""
    target = target or LATEST
    target.parent.mkdir(parents=True, exist_ok=True)
    pictures = Path.home() / "Pictures"
    pictures.mkdir(exist_ok=True)
    started = time.time()
    try:
        from .actions import _run
    except Exception:
        return None
    code, _ = _run([
        "gdbus", "call", "--session", "--dest", "org.freedesktop.portal.Desktop",
        "--object-path", "/org/freedesktop/portal/desktop",
        "--method", "org.freedesktop.portal.Screenshot.Screenshot",
        "", "{'interactive': <false>}",
    ], timeout=8)
    if code == 0:
        for _ in range(28):
            shots = [p for p in pictures.glob("*.png") if p.stat().st_mtime >= started - 1]
            if shots:
                newest = max(shots, key=lambda p: p.stat().st_mtime)
                if newest.stat().st_size > 1000:
                    target.write_bytes(newest.read_bytes())
                    try:
                        newest.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return target
            time.sleep(0.25)
    import shutil
    for candidate in (["grim", str(target)], ["gnome-screenshot", "-f", str(target)],
                      ["spectacle", "-b", "-n", "-o", str(target)],
                      ["import", "-window", "root", str(target)]):
        if not shutil.which(candidate[0]):
            continue
        code, _ = _run(candidate, timeout=10)
        if code == 0 and target.exists() and target.stat().st_size > 1000:
            return target
    return None


class ScreenVision:
    """A living read of the display: a background watcher keeps OCR text warm."""

    INTERVAL = 3.5

    def __init__(self) -> None:
        self._ocr_engine = None
        self._lock = threading.Lock()
        self.last_text = ""
        self.last_path: Path | None = None
        self.last_at = 0.0
        self._watch = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture_lock = threading.Lock()
        self._vision_model: str | None = None
        self._vision_checked = False

    def capture(self) -> Path | None:
        with self._capture_lock:
            path = capture_screen()
        if path:
            self.last_path = path
        return path

    # ------------------------------------------------------------- watching
    def start_watching(self) -> None:
        self._watch.set()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="screen-watch")
        self._thread.start()

    def stop_watching(self) -> None:
        self._watch.clear()

    @property
    def watching(self) -> bool:
        return self._watch.is_set()

    def _loop(self) -> None:
        while True:
            if not self._watch.is_set():
                time.sleep(0.4)
                continue
            fired = False
            try:
                path = self.capture()
                if path:
                    self.read(path)
                    self.last_at = time.time()
                    fired = True
            except Exception:
                pass
            if fired:
                self._watch.wait(self.INTERVAL)
            else:
                self._watch.wait(1.5)

    def fresh(self, max_age: float = 8.0) -> str:
        """Cached OCR, if a watcher pass landed recently."""
        if self.last_text and time.time() - self.last_at <= max_age:
            return self.last_text
        return ""

    def _load_ocr(self):
        if self._ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr_engine = RapidOCR()
        return self._ocr_engine

    def read(self, path: Path | None = None) -> str:
        path = path or self.last_path or self.capture()
        if not path or not path.exists():
            return ""
        with self._lock:
            try:
                engine = self._load_ocr()
                result, _ = engine(str(path))
            except Exception:
                return ""
        if not result:
            return ""
        lines: list[str] = []
        for item in result:
            try:
                text = str(item[1]).strip()
                score = float(item[2])
            except (IndexError, TypeError, ValueError):
                continue
            if text and score >= 0.35 and (not lines or lines[-1] != text):
                lines.append(text)
        text = "\n".join(lines)
        self.last_text = text[:9000]
        return self.last_text

    def read_boxes(self, path: Path) -> list[tuple[int, int, str]]:
        """OCR with pixel centres, for grounding clicks on canvases."""
        if not path or not path.exists():
            return []
        with self._lock:
            try:
                engine = self._load_ocr()
                result, _ = engine(str(path))
            except Exception:
                return []
        boxes: list[tuple[int, int, str]] = []
        for item in result or []:
            try:
                points = item[0]
                text = str(item[1]).strip()
                score = float(item[2])
            except (IndexError, TypeError, ValueError):
                continue
            if not text or score < 0.4:
                continue
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
            boxes.append((int(sum(xs) / len(xs)), int(sum(ys) / len(ys)), text[:60]))
        return boxes

    # ---------------------------------------------------------- local vision
    def _find_vision_model(self) -> str | None:
        if self._vision_checked:
            return self._vision_model
        self._vision_checked = True
        try:
            import json
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
                data = json.loads(response.read().decode())
            names = [m.get("name", "") for m in data.get("models", [])]
            for candidate in ("moondream", "llava", "qwen2.5vl", "llama3.2-vision", "minicpm-v", "bakllava"):
                for name in names:
                    if candidate in name.casefold():
                        self._vision_model = name
                        return name
        except Exception:
            pass
        return None

    def describe(self, prompt: str, path: Path | None = None, timeout: float = 90.0) -> str:
        model = self._find_vision_model()
        path = path or self.last_path
        if not model or not path or not path.exists():
            return ""
        try:
            import json
            import urllib.request
            payload = {
                "model": model,
                "prompt": prompt,
                "images": [base64.b64encode(path.read_bytes()).decode("ascii")],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 320},
            }
            request = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return str(json.loads(response.read().decode()).get("response", "")).strip()
        except Exception:
            return ""
