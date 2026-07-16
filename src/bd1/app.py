# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import atexit
import signal
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from bd1.autostart import AutostartManager
from bd1.models import ObservationType
from bd1.reports import ReportService
from bd1.settings import Settings, save_settings
from bd1.state import StateMachine
from bd1.storage import ObservationStore
from bd1.system import system_boot_time
from bd1.tray import TrayApp

if TYPE_CHECKING:
    from bd1.activity import ActivityMonitor


class BD1Application:
    def __init__(
        self,
        settings: Settings,
        store: ObservationStore,
        activity_monitor_enabled: bool = True,
        boot_time_provider: Callable[[], datetime] = system_boot_time,
        autostart_manager: AutostartManager | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.activity_monitor_enabled = activity_monitor_enabled
        self.boot_time_provider = boot_time_provider
        self.autostart_manager = autostart_manager or AutostartManager()
        self.state_machine = StateMachine()
        self.report_service = ReportService(store)
        self.tray: TrayApp | None = None
        self.activity_monitor: ActivityMonitor | None = None
        if activity_monitor_enabled:
            from bd1.activity import ActivityMonitor

            self.activity_monitor = ActivityMonitor(
                idle_threshold_seconds=settings.idle_threshold_seconds,
                callback=self.add_observation,
                poll_seconds=settings.activity_poll_seconds,
            )
        self._stopping = False
        self._stop_lock = threading.Lock()
        self._shutdown_requested = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def run(self) -> None:
        atexit.register(self._record_app_stopped)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._record_system_boot()
        self.add_observation(ObservationType.APP_STARTED, metadata={"source": "app"})
        self.autostart_manager.refresh_if_enabled()
        self.tray = TrayApp(
            store=self.store,
            report_service=self.report_service,
            add_observation=self.add_observation,
            autostart_is_enabled=self.autostart_is_enabled,
            toggle_autostart=self.toggle_autostart,
            stop_callback=self.stop,
        )
        if self.activity_monitor is not None:
            self.activity_monitor.start()
        self._start_heartbeat()
        self._start_signal_watcher()
        try:
            self.tray.run()
        finally:
            self.stop()

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopping:
                return
            self._stopping = True

        if self.activity_monitor is not None:
            self.activity_monitor.stop()
        self._stop_heartbeat()
        self._record_app_stopped()
        if self.tray is not None:
            self.tray.stop()
        self.store.close()

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
        if self.tray is not None:
            self.tray.set_state(state)

    def autostart_is_enabled(self) -> bool:
        return self.autostart_manager.is_enabled()

    def toggle_autostart(self) -> bool:
        enabled = not self.autostart_manager.is_enabled()
        status = self.autostart_manager.set_enabled(enabled)
        self.settings = replace(self.settings, autostart_enabled=status.enabled)
        save_settings(self.settings)
        return status.enabled

    def _record_app_stopped(self) -> None:
        try:
            self.store.add(ObservationType.APP_STOPPED, metadata={"source": "app"})
        except RuntimeError:
            return

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
            try:
                self.store.add(
                    ObservationType.APP_HEARTBEAT,
                    metadata={"source": "app"},
                )
            except RuntimeError:
                return

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

    def _handle_signal(self, signum: int, frame: object) -> None:
        self._shutdown_requested.set()

    def _start_signal_watcher(self) -> None:
        thread = threading.Thread(target=self._wait_for_shutdown_request, daemon=True)
        thread.start()

    def _wait_for_shutdown_request(self) -> None:
        self._shutdown_requested.wait()
        if self.tray is not None:
            self.tray.stop()
