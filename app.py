#!/usr/bin/env python3
"""J.A.R.V.I.S. harness server — local voice control for this machine."""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import signal
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jarvis import config, cua_driver, llm
from jarvis.actions import Actions
from jarvis.bus import EventBus
from jarvis.cua_agent import Agent
from jarvis.engine import Engine
from jarvis.screen import ScreenVision, LATEST as SCREEN_LATEST
from jarvis.system import Sampler, full_status
from jarvis.tts import TTS

config.ensure_dirs()
BUS = EventBus()
SAMPLER = Sampler(BUS)
ACTIONS = Actions(BUS, SAMPLER)
SCREEN = ScreenVision()
AGENT = Agent(BUS, SCREEN)
ENGINE = Engine(BUS, SAMPLER, ACTIONS, SCREEN, AGENT)
VOICE = TTS()

def _ocr_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


ALLOWED_ORIGINS = {
    f"http://127.0.0.1:{config.PORT}",
    f"http://localhost:{config.PORT}",
}


def build_state() -> dict:
    return {
        "online": True,
        "name": config.SETTINGS["assistant_name"],
        "title": config.SETTINGS["user_title"],
        "voice": config.SETTINGS["voice"],
        "language": config.SETTINGS["listen_language"],
        "wake_words": config.SETTINGS["wake_words"],
        "awake_seconds": config.SETTINGS["awake_seconds"],
        "stats": SAMPLER.snapshot(),
        "logs": BUS.recent_logs(),
        "capabilities": {
            **config.capabilities(),
            "tts": VOICE.available(),
            "llm": llm.available(),
            "screen": True if SCREEN.watching else SCREEN_LATEST.exists(),
            "screen_ocr": _ocr_available(),
            "agent": cua_driver.available(),
        },
        "engine": ENGINE.status(),
        "agent": {"running": AGENT.running},
        "greeting": full_status(SAMPLER.snapshot()) if SAMPLER.snapshot() else "All systems initialising, sir.",
        "server_time": time.time(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "JarvisHarness/2.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003
        if os.environ.get("JARVIS_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ------------------------------------------------------------------ GET
    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(build_state())
            return
        if path == "/api/health":
            self._json({"ok": True, "uptime": time.time(), "llm": llm.available(), "tts": VOICE.available()})
            return
        if path == "/api/events":
            self._sse()
            return
        if path == "/api/tts":
            text = (parse_qs(urlparse(self.path).query).get("text", [""])[0])[:1000]
            self._tts_stream(text)
            return
        if path == "/api/screen/latest":
            target = SCREEN.last_path if SCREEN.last_path and SCREEN.last_path.exists() else SCREEN_LATEST
            if target.exists():
                self._file(target, "image/png", cache=False)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
            return
        if path in ("/", "/index.html"):
            self._file(config.WEB_DIR / "index.html", "text/html; charset=utf-8", cache=False)
            return
        self._static(path)

    # ----------------------------------------------------------------- POST
    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if not self._origin_ok():
            self._json({"ok": False, "say": "Origin rejected, sir."}, HTTPStatus.FORBIDDEN)
            return
        try:
            body = self._body()
        except ValueError as exc:
            self._json({"ok": False, "say": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/command":
            text = str(body.get("text", ""))[:1000]
            if not text.strip():
                self._json({"ok": False, "say": "I didn't receive a command, sir."}, HTTPStatus.BAD_REQUEST)
                return
            result = ENGINE.handle(text)
            BUS.publish("command", {"text": text, "action": result.get("action"), "ok": result.get("ok")})
            self._json(result)
            return

        if path == "/api/tts":
            text = str(body.get("text", ""))[:1000]
            try:
                audio, mime = VOICE.synthesize(text)
            except Exception as exc:
                BUS.log("VOX", f"TTS offline: {exc}", "warn")
                self._json({"ok": False, "say": "Voice synthesis offline, sir."}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self._write(audio)
            return

        if path == "/api/heard":
            text = str(body.get("text", ""))[:1000]
            if text.strip():
                BUS.log("MIC", text)
            self._json({"ok": True})
            return

        if path == "/api/agent":
            task = str(body.get("task", ""))[:600].strip()
            if not task:
                self._json({"ok": False, "say": "What should I do, sir?"}, HTTPStatus.BAD_REQUEST)
                return
            AGENT.start(task)
            self._json({"ok": True, "say": "On it, sir.", "task": task})
            return

        if path == "/api/agent/stop":
            AGENT.stop()
            self._json({"ok": True, "say": "Stopping the agent, sir."})
            return

        if path == "/api/engage":
            BUS.log("LINK", "Voice link engaged", "ok")
            SCREEN.start_watching()
            self._json({"ok": True})
            return

        if path == "/api/listen":
            on = bool(body.get("on", True))
            if on:
                SCREEN.start_watching()
            else:
                SCREEN.stop_watching()
            BUS.log("LINK", "Voice link live" if on else "Voice link paused", "ok")
            self._json({"ok": True, "listening": on})
            return

        self._json({"ok": False, "say": "Unknown endpoint."}, HTTPStatus.NOT_FOUND)

    # -------------------------------------------------------------- helpers
    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > 2_000_000:
            raise ValueError("Payload too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Malformed JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return not origin or origin in ALLOWED_ORIGINS

    def _json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._write(data)

    def _write(self, data: bytes) -> None:
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _file(self, path: Path, content_type: str, cache: bool = True) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-cache")
        self.end_headers()
        self._write(data)

    def _static(self, path: str) -> None:
        relative = path.lstrip("/")
        candidate = (config.WEB_DIR / relative).resolve()
        try:
            candidate.relative_to(config.WEB_DIR)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(candidate.name)
        self._file(candidate, (mime or "application/octet-stream") + ("; charset=utf-8" if (mime or "").startswith("text/") else ""))

    def _tts_stream(self, text: str) -> None:
        if not text.strip():
            self._json({"ok": False, "say": "No text, sir."}, HTTPStatus.BAD_REQUEST)
            return
        generator = VOICE.stream(text)
        try:
            first = next(generator)
        except Exception as exc:
            BUS.log("VOX", f"TTS offline: {exc}", "warn")
            self._json({"ok": False, "say": "Voice synthesis offline, sir."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", VOICE.mime(text))
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self._chunk(first)
            for chunk in generator:
                self._chunk(chunk)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _chunk(self, data: bytes) -> None:
        self.wfile.write(f"{len(data):X}\r\n".encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        client = BUS.subscribe()
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.write(BUS.encode_sse("hello", {"time": time.time()}))
            self.wfile.flush()
            last = time.time()
            while True:
                try:
                    message = client.get(timeout=1.0)
                    self.wfile.write(BUS.encode_sse(message["event"], message["payload"]))
                    self.wfile.flush()
                except queue.Empty:
                    if time.time() - last > 12:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        last = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            BUS.unsubscribe(client)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    config.ensure_dirs()
    SAMPLER.start()
    BUS.log("SYS", "J.A.R.V.I.S. harness online", "ok")
    if llm.available():
        BUS.log("NEURAL", "DeepSeek neural core linked", "ok")
    else:
        BUS.log("NEURAL", "Neural core offline; local control only", "warn")
    if not VOICE.available():
        BUS.log("VOX", "edge-tts missing; browser voice fallback only", "warn")
    else:
        VOICE.prewarm(["Yes, sir?", "At your service, sir.", "Right away, sir."])
    server = Server((config.HOST, config.PORT), Handler)
    print(f"J.A.R.V.I.S. online at http://{config.HOST}:{config.PORT}", flush=True)

    def shutdown(*_args):
        print("\nPowering down harness.", flush=True)

        def stop():
            SAMPLER.stop()
            ACTIONS.stop()
            server.shutdown()

        threading.Thread(target=stop, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
