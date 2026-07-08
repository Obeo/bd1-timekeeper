from __future__ import annotations

import atexit
import signal
import threading
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from bd1.models import ObservationType
from bd1.reports import ReportService
from bd1.settings import Settings
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
    ) -> None:
        self.settings = settings
        self.store = store
        self.activity_monitor_enabled = activity_monitor_enabled
        self.boot_time_provider = boot_time_provider
        self.state_machine = StateMachine()
        self.report_service = ReportService(store)
        self.tray: TrayApp | None = None
        self.activity_monitor: ActivityMonitor | None = None
        if activity_monitor_enabled:
            from bd1.activity import ActivityMonitor

            self.activity_monitor = ActivityMonitor(
                idle_threshold_seconds=settings.idle_threshold_seconds,
                callback=self.add_observation,
            )
        self._stopping = False
        self._stop_lock = threading.Lock()
        self._shutdown_requested = threading.Event()

    def run(self) -> None:
        atexit.register(self._record_app_stopped)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._record_system_boot()
        self.add_observation(ObservationType.APP_STARTED, metadata={"source": "app"})
        self.tray = TrayApp(
            store=self.store,
            report_service=self.report_service,
            add_observation=self.add_observation,
            stop_callback=self.stop,
        )
        if self.activity_monitor is not None:
            self.activity_monitor.start()
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

    def _record_app_stopped(self) -> None:
        try:
            self.store.add(ObservationType.APP_STOPPED, metadata={"source": "app"})
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
