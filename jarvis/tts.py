"""Neural voice synthesis with streaming and an on-disk cache."""

from __future__ import annotations

import asyncio
import hashlib
import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path

from . import config

PIPER_BIN = config.BASE_DIR / "tools" / "piper" / "piper" / "piper"
PIPER_MODEL = config.BASE_DIR / config.SETTINGS.get("piper_model", "tools/piper/voices/en_GB-alan-medium.onnx")


class TTS:
    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._available: bool | None = None

    def available(self) -> bool:
        if self.piper_available():
            return True
        if self._available is None:
            try:
                import edge_tts  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    @staticmethod
    def _clean(text: str) -> str:
        cleaned = re.sub(r"[*_`#]+", "", text or "").strip()
        return re.sub(r"\s+", " ", cleaned)[:700]

    def piper_available(self) -> bool:
        return (
            config.SETTINGS.get("tts_engine", "piper") == "piper"
            and PIPER_BIN.exists()
            and PIPER_MODEL.exists()
        )

    def engine(self) -> str:
        return "piper" if self.piper_available() else "edge"

    def mime(self, text: str) -> str:
        return "audio/wav" if self.engine() == "piper" else "audio/mpeg"

    def _target(self, text: str) -> tuple[str, Path, str]:
        cleaned = self._clean(text)
        if not cleaned:
            raise RuntimeError("empty text")
        engine = self.engine()
        voice = "en_GB-alan-medium" if engine == "piper" else config.SETTINGS.get("voice", "en-GB-RyanNeural")
        digest = hashlib.sha256(f"{engine}|{voice}|{cleaned}".encode("utf-8")).hexdigest()[:24]
        suffix = ".wav" if engine == "piper" else ".mp3"
        return cleaned, config.CACHE_DIR / f"{digest}{suffix}", voice

    def cached(self, text: str) -> Path | None:
        try:
            _, path, _ = self._target(text)
        except RuntimeError:
            return None
        return path if path.exists() and path.stat().st_size > 512 else None

    def _synthesize_piper(self, cleaned: str, path: Path) -> None:
        temp = path.with_suffix(".tmp.wav")
        proc = subprocess.run(
            [
                str(PIPER_BIN),
                "--model", str(PIPER_MODEL),
                "--output_file", str(temp),
                "--length_scale", str(config.SETTINGS.get("piper_length_scale", 1.04)),
                "--sentence_silence", "0.18",
            ],
            input=(cleaned + "\n").encode("utf-8"),
            capture_output=True,
            timeout=45,
        )
        if proc.returncode != 0 or not temp.exists():
            raise RuntimeError(proc.stderr.decode("utf-8", "ignore")[-300:] or "piper failed")
        temp.replace(path)

    def stream(self, text: str):
        """Yield audio bytes, writing the full file to the cache."""
        cleaned, path, voice = self._target(text)
        if path.exists() and path.stat().st_size > 512:
            yield path.read_bytes()
            return
        lock = self._lock_for(path.stem)
        with lock:
            if path.exists() and path.stat().st_size > 512:
                yield path.read_bytes()
                return
            config.ensure_dirs()
            if self.engine() == "piper":
                self._synthesize_piper(cleaned, path)
                self._trim_cache()
                yield path.read_bytes()
                return
            if not self.available():
                raise RuntimeError("edge-tts is not installed")
            temp = path.with_suffix(".tmp.mp3")
            chunks: queue.Queue = queue.Queue()

            def worker() -> None:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)

                    async def produce() -> None:
                        communicate = __import__("edge_tts").Communicate(
                            cleaned, voice, rate="-3%", pitch="-2Hz"
                        )
                        with temp.open("wb") as handle:
                            async for item in communicate.stream():
                                if item.get("type") == "audio" and item.get("data"):
                                    data = item["data"]
                                    handle.write(data)
                                    chunks.put(data)
                        chunks.put(None)

                    loop.run_until_complete(produce())
                except Exception as exc:  # noqa: BLE001
                    chunks.put(exc)
                finally:
                    loop.close()

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            try:
                while True:
                    item = chunks.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    yield item
                temp.replace(path)
            finally:
                thread.join(timeout=2)
            self._trim_cache()

    def synthesize(self, text: str) -> tuple[bytes, str]:
        data = b"".join(self.stream(text))
        if not data:
            raise RuntimeError("empty audio")
        return data, self.mime(text)

    def prewarm(self, phrases: list[str]) -> None:
        def run() -> None:
            for phrase in phrases:
                try:
                    for _ in self.stream(phrase):
                        pass
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True, name="tts-prewarm").start()

    @staticmethod
    def _trim_cache(limit: int = 150) -> None:
        files = sorted(list(config.CACHE_DIR.glob("*.mp3")) + list(config.CACHE_DIR.glob("*.wav")), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[limit:]:
            try:
                old.unlink()
            except OSError:
                pass
