"""Thread-safe event fan-out and a bounded activity log."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque


class EventBus:
    def __init__(self, log_limit: int = 120) -> None:
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()
        self.logs: deque[dict] = deque(maxlen=log_limit)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: str, payload: dict) -> None:
        message = {"event": event, "payload": payload, "at": time.time()}
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                pass

    def log(self, kind: str, message: str, level: str = "info") -> None:
        entry = {
            "kind": kind,
            "message": message,
            "level": level,
            "at": time.time(),
        }
        self.logs.append(entry)
        self.publish("log", entry)

    def recent_logs(self, limit: int = 40) -> list[dict]:
        return list(self.logs)[-limit:]

    @staticmethod
    def encode_sse(event: str, payload: dict) -> bytes:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return f"event: {event}\ndata: {body}\n\n".encode("utf-8")
