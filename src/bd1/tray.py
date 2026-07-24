# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

import pystray
from PIL import Image

from bd1.mattermost_window import MattermostWindow
from bd1.models import ObservationType, RuntimeState
from bd1.paths import icon_dir
from bd1.report_window import ReportView, ReportWindow
from bd1.storage import ObservationStore

ObservationRecorder = Callable[[ObservationType, datetime | None, dict[str, object] | None], None]


class TrayIconName(StrEnum):
    OFFLINE = "sleep.png"
    PC_ON = "idle.png"
    ACTIVE = "active.png"
    IDLE = "pause.png"


class TrayApp:
    def __init__(
        self,
        store: ObservationStore,
        add_observation: ObservationRecorder,
        autostart_is_enabled: Callable[[], bool],
        toggle_autostart: Callable[[], bool],
        mattermost_settings_changed: Callable[[], None],
        stop_callback: Callable[[], None],
    ) -> None:
        self.store = store
        self.add_observation = add_observation
        self.autostart_is_enabled = autostart_is_enabled
        self.toggle_autostart = toggle_autostart
        self.mattermost_settings_changed = mattermost_settings_changed
        self.stop_callback = stop_callback
        self.state = RuntimeState.PC_ON
        self._report_window: ReportWindow | None = None
        self._report_window_lock = threading.Lock()
        self._mattermost_window: MattermostWindow | None = None
        self._mattermost_window_lock = threading.Lock()
        self.icon = pystray.Icon("BD-1", self._load_image(self.state), "BD-1", self._menu())

    def run(self) -> None:
        self.icon.run()

    def stop(self) -> None:
        with self._report_window_lock:
            report_window = self._report_window
        if report_window is not None:
            report_window.close()
        with self._mattermost_window_lock:
            mattermost_window = self._mattermost_window
        if mattermost_window is not None:
            mattermost_window.close()
        self.icon.stop()

    def set_state(self, state: RuntimeState) -> None:
        self.state = state
        self.icon.icon = self._load_image(state)
        self.icon.menu = self._menu()
        self.icon.update_menu()

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("BD-1", None, enabled=False),
            pystray.MenuItem(f"État : {self._state_label()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Marquer : début de travail",
                lambda *_: self.add_observation(
                    ObservationType.USER_WORKING,
                    None,
                    {"source": "tray"},
                ),
            ),
            pystray.MenuItem(
                "Marquer : début de pause",
                lambda *_: self.add_observation(
                    ObservationType.USER_BREAK,
                    None,
                    {"source": "tray"},
                ),
            ),
            pystray.MenuItem("Rapports", lambda *_: self._show_report_window(ReportView.DAY)),
            pystray.MenuItem(
                "Configurer",
                pystray.Menu(
                    pystray.MenuItem(
                        "Intégration Mattermost",
                        lambda *_: self._show_mattermost_window(),
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Lancer au démarrage",
                lambda *_: self._toggle_autostart(),
                checked=lambda _: self.autostart_is_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", lambda *_: self.stop_callback()),
        )

    def _toggle_autostart(self) -> None:
        self.toggle_autostart()
        self.icon.update_menu()

    def _show_report_window(self, view: ReportView) -> None:
        with self._report_window_lock:
            if self._report_window is None or not self._report_window.is_alive():
                self._report_window = ReportWindow(
                    database_path=self.store.path,
                    initial_view=view,
                    initial_date=datetime.now().date(),
                    on_closed=self._report_window_closed,
                )
                self._report_window.start()
            else:
                self._report_window.focus()

    def _report_window_closed(self, report_window: ReportWindow) -> None:
        with self._report_window_lock:
            if self._report_window is report_window:
                self._report_window = None

    def _show_mattermost_window(self) -> None:
        with self._mattermost_window_lock:
            if self._mattermost_window is None or not self._mattermost_window.is_alive():
                self._mattermost_window = MattermostWindow(
                    on_closed=self._mattermost_window_closed,
                )
                self._mattermost_window.start()
            else:
                self._mattermost_window.focus()

    def _mattermost_window_closed(self, mattermost_window: MattermostWindow) -> None:
        with self._mattermost_window_lock:
            if self._mattermost_window is mattermost_window:
                self._mattermost_window = None
        self.mattermost_settings_changed()

    @staticmethod
    def _load_image(state: RuntimeState) -> Image.Image:
        mapping = {
            RuntimeState.OFFLINE: TrayIconName.OFFLINE,
            RuntimeState.PC_ON: TrayIconName.PC_ON,
            RuntimeState.ACTIVE: TrayIconName.ACTIVE,
            RuntimeState.IDLE: TrayIconName.IDLE,
        }
        return Image.open(icon_dir() / mapping[state]).convert("RGBA")

    def _state_label(self) -> str:
        labels = {
            RuntimeState.OFFLINE: "arrêté",
            RuntimeState.PC_ON: "PC démarré",
            RuntimeState.ACTIVE: "travail probable",
            RuntimeState.IDLE: "pause probable",
        }
        return labels[self.state]
