# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from typing import TYPE_CHECKING

from bd1.autostart import AutostartManager
from bd1.mattermost import (
    MattermostError,
    get_token,
    normalize_server_url,
    sync_custom_status,
)
from bd1.models import ObservationType
from bd1.network import network_status, work_location
from bd1.settings import Settings, load_settings, save_settings
from bd1.single_instance import SingleInstanceLock
from bd1.state import StateMachine
from bd1.storage import ObservationStore
from bd1.system import system_boot_time
from bd1.tray import TrayApp

if TYPE_CHECKING:
    from bd1.activity import ActivityMonitor
    from bd1.windows_session import WindowsSessionEndListener

LOGGER = logging.getLogger(__name__)
MATTERMOST_SYNC_INTERVAL_SECONDS = 3600


class BD1Application:
    def __init__(
        self,
        settings: Settings,
        store: ObservationStore,
        activity_monitor_enabled: bool = True,
        boot_time_provider: Callable[[], datetime] = system_boot_time,
        autostart_manager: AutostartManager | None = None,
        single_instance_lock: SingleInstanceLock | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.activity_monitor_enabled = activity_monitor_enabled
        self.boot_time_provider = boot_time_provider
        self.autostart_manager = autostart_manager or AutostartManager()
        self.single_instance_lock = single_instance_lock or SingleInstanceLock()
        self.state_machine = StateMachine()
        self.tray: TrayApp | None = None
        self.activity_monitor: ActivityMonitor | None = None
        self.windows_session_listener: WindowsSessionEndListener | None = None
        if activity_monitor_enabled:
            from bd1.activity import ActivityMonitor

            self.activity_monitor = ActivityMonitor(
                idle_threshold_seconds=settings.idle_threshold_seconds,
                callback=self.add_observation,
                poll_seconds=settings.activity_poll_seconds,
                idle_ignored_process_names=settings.idle_ignored_process_names,
            )
        self._stopping = False
        self._stop_lock = threading.Lock()
        self._shutdown_requested = threading.Event()
        self._windows_session_end_recorded = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._mattermost_stop = threading.Event()
        self._mattermost_thread: threading.Thread | None = None
        self._mattermost_last_location: str | None = None
        self._mattermost_last_date: date | None = None

    def run(self) -> None:
        if not self.single_instance_lock.acquire():
            return

        atexit.register(self._record_app_stopped)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._record_system_boot()
        startup_network_status = network_status()
        self.add_observation(
            ObservationType.APP_STARTED,
            metadata={"source": "app", **startup_network_status},
        )
        self.autostart_manager.refresh_if_enabled()
        self.tray = TrayApp(
            store=self.store,
            add_observation=self.add_observation,
            autostart_is_enabled=self.autostart_is_enabled,
            toggle_autostart=self.toggle_autostart,
            mattermost_settings_changed=self.mattermost_settings_changed,
            stop_callback=self.stop,
        )
        if self.activity_monitor is not None:
            self.activity_monitor.start()
        self._start_windows_session_listener()
        self._start_heartbeat()
        self._start_mattermost_sync(startup_network_status)
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
        if self.windows_session_listener is not None:
            self.windows_session_listener.stop()
        self._stop_heartbeat()
        self._stop_mattermost_sync()
        self._record_app_stopped()
        if self.tray is not None:
            self.tray.stop()
        self.store.close()
        self.single_instance_lock.release()

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

    def mattermost_settings_changed(self) -> None:
        with self._stop_lock:
            if self._stopping:
                return
        self._stop_mattermost_sync()
        self.settings = load_settings()
        self._mattermost_stop = threading.Event()
        self._mattermost_thread = None
        self._mattermost_last_location = None
        self._mattermost_last_date = None
        self._start_mattermost_sync(network_status())

    def _record_app_stopped(self) -> None:
        try:
            self.store.add(ObservationType.APP_STOPPED, metadata={"source": "app"})
        except RuntimeError:
            return

    def _record_windows_session_end(self, phase: str) -> None:
        if self._windows_session_end_recorded.is_set():
            return
        self._windows_session_end_recorded.set()
        try:
            self.store.add(
                ObservationType.SHUTDOWN,
                metadata={"source": "windows_session", "phase": phase},
            )
            self.store.add(
                ObservationType.APP_STOPPED,
                metadata={"source": "windows_session", "phase": phase},
            )
        except RuntimeError:
            return

    def _start_windows_session_listener(self) -> None:
        if sys.platform != "win32":
            return

        from bd1.windows_session import WindowsSessionEndListener

        self.windows_session_listener = WindowsSessionEndListener(self._record_windows_session_end)
        self.windows_session_listener.start()

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

    def _start_mattermost_sync(self, startup_network_status: dict[str, object]) -> None:
        if not self.settings.mattermost_url:
            return
        stop_event = self._mattermost_stop
        self._mattermost_thread = threading.Thread(
            target=self._sync_mattermost_periodically,
            args=(startup_network_status, stop_event),
            daemon=True,
        )
        self._mattermost_thread.start()

    def _stop_mattermost_sync(self) -> None:
        self._mattermost_stop.set()
        if self._mattermost_thread is not None:
            self._mattermost_thread.join(timeout=2)

    def _sync_mattermost_periodically(
        self,
        current_network_status: dict[str, object],
        stop_event: threading.Event,
    ) -> None:
        while True:
            self._sync_mattermost(current_network_status)
            if stop_event.wait(MATTERMOST_SYNC_INTERVAL_SECONDS):
                return
            current_network_status = network_status()

    def _sync_mattermost(self, current_network_status: dict[str, object]) -> None:
        location = work_location(
            current_network_status,
            self.settings.vpn_interface_patterns,
        )
        today = datetime.now().astimezone().date()
        if location == self._mattermost_last_location and today == self._mattermost_last_date:
            return

        try:
            server_url = normalize_server_url(self.settings.mattermost_url)
            token = get_token(server_url)
            if token is None:
                return
            sync_custom_status(server_url, token, location)
        except (MattermostError, ValueError) as error:
            LOGGER.warning("Could not synchronize Mattermost custom status: %s", error)
            return

        self._mattermost_last_location = location
        self._mattermost_last_date = today

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
