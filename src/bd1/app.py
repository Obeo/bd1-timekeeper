from __future__ import annotations

import atexit
import signal
from datetime import datetime

from bd1.activity import ActivityMonitor
from bd1.models import ObservationType
from bd1.reports import ReportService
from bd1.settings import Settings
from bd1.state import StateMachine
from bd1.storage import ObservationStore
from bd1.tray import TrayApp


class BD1Application:
    def __init__(self, settings: Settings, store: ObservationStore) -> None:
        self.settings = settings
        self.store = store
        self.state_machine = StateMachine()
        self.report_service = ReportService(store)
        self.tray: TrayApp | None = None
        self.activity_monitor = ActivityMonitor(
            idle_threshold_seconds=settings.idle_threshold_seconds,
            callback=self.add_observation,
        )
        self._stopping = False

    def run(self) -> None:
        atexit.register(self._record_shutdown)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.add_observation(ObservationType.BOOT, metadata={"source": "app"})
        self.tray = TrayApp(
            store=self.store,
            report_service=self.report_service,
            add_observation=self.add_observation,
            stop_callback=self.stop,
        )
        self.activity_monitor.start()
        self.tray.run()

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self.activity_monitor.stop()
        self._record_shutdown()
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

    def _record_shutdown(self) -> None:
        if self.state_machine.state.value == "OFFLINE":
            return
        self.add_observation(ObservationType.SHUTDOWN, metadata={"source": "app"})

    def _handle_signal(self, signum: int, frame: object) -> None:
        self.stop()
