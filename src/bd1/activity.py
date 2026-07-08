from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from pynput import keyboard, mouse

from bd1.models import ObservationType

ObservationCallback = Callable[[ObservationType, datetime | None, dict[str, object] | None], None]


class ActivityMonitor:
    def __init__(self, idle_threshold_seconds: int, callback: ObservationCallback) -> None:
        self.idle_threshold_seconds = idle_threshold_seconds
        self.callback = callback
        self._last_activity_monotonic = time.monotonic()
        self._last_activity_at = datetime.now().astimezone()
        self._seen_activity = False
        self._idle = False
        self._stop_event = threading.Event()
        self._watcher_thread = threading.Thread(target=self._watch_idle, daemon=True)
        self._keyboard_listener = keyboard.Listener(on_press=self._on_activity)
        self._mouse_listener = mouse.Listener(on_move=self._on_activity, on_click=self._on_activity)

    def start(self) -> None:
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._watcher_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._keyboard_listener.stop()
        self._mouse_listener.stop()
        self._watcher_thread.join(timeout=2)

    def _on_activity(self, *args: object) -> None:
        self._last_activity_monotonic = time.monotonic()
        self._last_activity_at = datetime.now().astimezone()
        if not self._seen_activity:
            self._seen_activity = True
            self._idle = False
            self.callback(ObservationType.FIRST_ACTIVITY, self._last_activity_at, None)
            return
        if self._idle:
            self._idle = False
            self.callback(ObservationType.ACTIVITY_RESUMED, self._last_activity_at, None)

    def _watch_idle(self) -> None:
        while not self._stop_event.wait(1.0):
            if self._idle or not self._seen_activity:
                continue
            idle_seconds = time.monotonic() - self._last_activity_monotonic
            if idle_seconds >= self.idle_threshold_seconds:
                self._idle = True
                idle_started_at = self._last_activity_at
                self.callback(
                    ObservationType.IDLE_STARTED,
                    idle_started_at,
                    {
                        "idle_threshold_seconds": self.idle_threshold_seconds,
                        "observed_idle_seconds": int(idle_seconds),
                        "detected_at": datetime.now().astimezone().isoformat(),
                        "threshold_crossed_at": (
                            idle_started_at + timedelta(seconds=self.idle_threshold_seconds)
                        ).isoformat(),
                    },
                )
