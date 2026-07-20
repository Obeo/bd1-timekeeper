# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from datetime import datetime

from bd1.models import ObservationType
from bd1.settings import Settings
from bd1.state import StateMachine
from bd1.storage import ObservationStore
from bd1.system import system_boot_time

ObserverPrinter = Callable[[str], None]
BootTimeProvider = Callable[[], datetime]


class HeadlessObserver:
    def __init__(
        self,
        settings: Settings,
        store: ObservationStore,
        printer: ObserverPrinter = print,
        boot_time_provider: BootTimeProvider = system_boot_time,
    ) -> None:
        self.settings = settings
        self.store = store
        self.printer = printer
        self.boot_time_provider = boot_time_provider
        self.state_machine = StateMachine()
        self._stop_event = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._monitor: object | None = None

    def run(self) -> None:
        self._record_system_boot()
        self.add_observation(ObservationType.APP_STARTED, metadata={"source": "observer"})
        self._start_activity_monitor()
        self._start_heartbeat()
        self.printer("BD-1 observe l'activité. Ctrl+C pour arrêter.")
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        previous_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        try:
            self._stop_event.wait()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            signal.signal(signal.SIGINT, previous_sigint)
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        self._stop_activity_monitor()
        self._stop_heartbeat()
        self.add_observation(ObservationType.APP_STOPPED, metadata={"source": "observer"})

    def add_observation(
        self,
        observation_type: ObservationType,
        observed_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        observation = self.store.add(
            observation_type,
            observed_at=observed_at or datetime.now().astimezone(),
            metadata=metadata,
        )
        state = self.state_machine.record(observation.type)
        self.printer(f"{observation.observed_at:%H:%M:%S} {observation.type.value} ({state.value})")

    def _record_system_boot(self) -> None:
        try:
            boot_time = self.boot_time_provider()
        except Exception:
            self.state_machine.record(ObservationType.BOOT)
            return

        if self.store.exists_at(ObservationType.BOOT, boot_time):
            self.state_machine.record(ObservationType.BOOT)
            return
        self.add_observation(
            ObservationType.BOOT,
            observed_at=boot_time,
            metadata={"source": "system_boot"},
        )

    def _start_activity_monitor(self) -> None:
        from bd1.activity import ActivityMonitor

        self._monitor = ActivityMonitor(
            idle_threshold_seconds=self.settings.idle_threshold_seconds,
            callback=self.add_observation,
            poll_seconds=self.settings.activity_poll_seconds,
            idle_ignored_process_names=self.settings.idle_ignored_process_names,
        )
        self._monitor.start()

    def _stop_activity_monitor(self) -> None:
        if self._monitor is None:
            return
        self._monitor.stop()
        self._monitor = None

    def _start_heartbeat(self) -> None:
        self._heartbeat_thread = threading.Thread(target=self._record_heartbeats, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)

    def _record_heartbeats(self) -> None:
        interval = max(1.0, self.settings.heartbeat_interval_seconds)
        while not self._heartbeat_stop.wait(interval):
            self.add_observation(ObservationType.APP_HEARTBEAT, metadata={"source": "observer"})

    def _handle_signal(self, signum: int, frame: object) -> None:
        self._stop_event.set()


def run_headless_observer(
    settings: Settings,
    store: ObservationStore,
    printer: ObserverPrinter = print,
) -> None:
    HeadlessObserver(settings, store, printer).run()
