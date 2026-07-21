# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from queue import Empty, Queue
from typing import Any

from pynput import keyboard, mouse

from bd1.audio_activity import is_microphone_used_by
from bd1.models import ObservationType
from bd1.processes import is_any_process_running

ObservationCallback = Callable[[ObservationType, datetime | None, dict[str, object] | None], None]
ProcessRunningChecker = Callable[[tuple[str, ...]], bool]
MicrophoneActivityChecker = Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    observation_type: ObservationType
    observed_at: datetime
    metadata: dict[str, object] | None = None


class ActivityMonitor:
    def __init__(
        self,
        idle_threshold_seconds: int,
        callback: ObservationCallback,
        poll_seconds: float = 10.0,
        idle_ignored_process_names: tuple[str, ...] = (),
        meeting_activity_detection_enabled: bool = True,
        meeting_process_names: tuple[str, ...] = (),
        process_running_checker: ProcessRunningChecker = is_any_process_running,
        microphone_activity_checker: MicrophoneActivityChecker = is_microphone_used_by,
    ) -> None:
        self.idle_threshold_seconds = idle_threshold_seconds
        self.poll_seconds = poll_seconds
        self.callback = callback
        self.idle_ignored_process_names = idle_ignored_process_names
        self.meeting_activity_detection_enabled = meeting_activity_detection_enabled
        self.meeting_process_names = meeting_process_names
        self.process_running_checker = process_running_checker
        self.microphone_activity_checker = microphone_activity_checker
        self._last_activity_monotonic = time.monotonic()
        self._last_activity_at = datetime.now().astimezone()
        self._seen_activity = False
        self._idle = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._events: Queue[ActivityEvent] = Queue()
        self._watcher_thread = threading.Thread(target=self._watch_idle, daemon=True)
        self._event_thread = threading.Thread(target=self._process_events, daemon=True)
        self._keyboard_listener = keyboard.Listener(on_press=self._on_activity)
        self._mouse_listener = mouse.Listener(on_move=self._on_activity, on_click=self._on_activity)

    def start(self) -> None:
        self._event_thread.start()
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._watcher_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._stop_listener(self._keyboard_listener)
        self._stop_listener(self._mouse_listener)
        self._watcher_thread.join(timeout=2)
        self._event_thread.join(timeout=2)

    def _on_activity(self, *args: object) -> None:
        observation_type: ObservationType | None = None
        observed_at = datetime.now().astimezone()

        try:
            with self._lock:
                self._last_activity_monotonic = time.monotonic()
                self._last_activity_at = observed_at
                if not self._seen_activity:
                    self._seen_activity = True
                    self._idle = False
                    observation_type = ObservationType.FIRST_ACTIVITY
                elif self._idle:
                    self._idle = False
                    observation_type = ObservationType.ACTIVITY_RESUMED

            if observation_type is not None:
                self._events.put(ActivityEvent(observation_type, observed_at))
        except Exception:
            return

    def _watch_idle(self) -> None:
        while not self._stop_event.wait(self.poll_seconds):
            idle_started_at: datetime | None = None
            idle_seconds = 0.0

            try:
                with self._lock:
                    if self._idle or not self._seen_activity:
                        continue
                    idle_seconds = time.monotonic() - self._last_activity_monotonic
                    if idle_seconds < self.idle_threshold_seconds:
                        continue
                    if (
                        self._has_ignored_process_running()
                        or self._has_meeting_microphone_activity()
                    ):
                        self._last_activity_monotonic = time.monotonic()
                        self._last_activity_at = datetime.now().astimezone()
                        continue
                    self._idle = True
                    idle_started_at = self._last_activity_at

                if idle_started_at is not None:
                    self._events.put(
                        ActivityEvent(
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
                    )
            except Exception:
                continue

    def _process_events(self) -> None:
        while not self._stop_event.is_set() or not self._events.empty():
            try:
                event = self._events.get(timeout=0.25)
            except Empty:
                continue

            try:
                self.callback(event.observation_type, event.observed_at, event.metadata)
            except Exception:
                continue

    @staticmethod
    def _stop_listener(listener: Any) -> None:
        try:
            listener.stop()
        except Exception:
            return

    def _has_ignored_process_running(self) -> bool:
        if not self.idle_ignored_process_names:
            return False
        try:
            return self.process_running_checker(self.idle_ignored_process_names)
        except Exception:
            return False

    def _has_meeting_microphone_activity(self) -> bool:
        if not self.meeting_activity_detection_enabled or not self.meeting_process_names:
            return False
        try:
            return self.microphone_activity_checker(self.meeting_process_names)
        except Exception:
            return False
