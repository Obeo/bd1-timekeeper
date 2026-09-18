# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from queue import Empty, Queue

import pystray
from PIL import Image

from bd1.mattermost_window import MattermostWindow
from bd1.models import ObservationType, RuntimeState
from bd1.paths import icon_dir
from bd1.report_window import ReportView, ReportWindow
from bd1.storage import ObservationStore
from bd1.updates import AvailableUpdate, find_update, installed_version

ObservationRecorder = Callable[[ObservationType, datetime | None, dict[str, object] | None], None]
LOGGER = logging.getLogger(__name__)
UPDATE_CHECK_INTERVAL_SECONDS = 86400
_MACOS_DISPATCHER_CLASS = None


class _MainThreadDispatcher:
    def __init__(self) -> None:
        self._callbacks: Queue[Callable[[], None]] = Queue()
        self._native = _make_macos_dispatcher(self) if sys.platform == "darwin" else None

    def dispatch(self, callback: Callable[[], None]) -> None:
        if self._native is None or threading.current_thread() is threading.main_thread():
            callback()
            return
        self._callbacks.put(callback)
        self._native.performSelectorOnMainThread_withObject_waitUntilDone_("run:", None, False)

    def _run_pending(self) -> None:
        try:
            callback = self._callbacks.get_nowait()
        except Empty:
            return
        try:
            callback()
        except Exception:
            LOGGER.exception("Could not update the macOS tray UI")


def _make_macos_dispatcher(dispatcher: _MainThreadDispatcher) -> object:
    global _MACOS_DISPATCHER_CLASS
    if _MACOS_DISPATCHER_CLASS is None:
        import Foundation
        import objc

        class NativeDispatcher(Foundation.NSObject):
            @objc.namedSelector(b"run:")
            def run(self, _object: object) -> None:
                self.dispatcher._run_pending()

        _MACOS_DISPATCHER_CLASS = NativeDispatcher

    native = _MACOS_DISPATCHER_CLASS.alloc().init()
    native.dispatcher = dispatcher
    return native


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
        update_checks_enabled: bool = True,
        notifications_enabled: bool = True,
    ) -> None:
        self.store = store
        self.add_observation = add_observation
        self.autostart_is_enabled = autostart_is_enabled
        self.toggle_autostart = toggle_autostart
        self.mattermost_settings_changed = mattermost_settings_changed
        self.stop_callback = stop_callback
        self.update_checks_enabled = update_checks_enabled
        self.notifications_enabled = notifications_enabled
        self._ui_dispatcher = _MainThreadDispatcher()
        self.current_version = installed_version()
        self.available_update: AvailableUpdate | None = None
        self._update_check_stop = threading.Event()
        self.state = RuntimeState.PC_ON
        self._report_window: ReportWindow | None = None
        self._report_window_lock = threading.Lock()
        self._mattermost_window: MattermostWindow | None = None
        self._mattermost_window_lock = threading.Lock()
        self.icon = pystray.Icon("BD-1", self._load_image(self.state), "BD-1", self._menu())

    def run(self) -> None:
        if self.update_checks_enabled:
            self.icon.run(setup=self._check_updates)
        else:
            self.icon.run()

    def stop(self) -> None:
        self._update_check_stop.set()
        with self._report_window_lock:
            report_window = self._report_window
        if report_window is not None:
            report_window.close()
        with self._mattermost_window_lock:
            mattermost_window = self._mattermost_window
        if mattermost_window is not None:
            mattermost_window.close()
        self._ui_dispatcher.dispatch(self.icon.stop)

    def set_state(self, state: RuntimeState) -> None:
        self._ui_dispatcher.dispatch(lambda: self._set_state_on_ui(state))

    def _set_state_on_ui(self, state: RuntimeState) -> None:
        self.state = state
        self.icon.icon = self._load_image(state)
        self.icon.menu = self._menu()
        self.icon.update_menu()

    def _menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem(f"Version : BD-1 v{self.current_version}", None, enabled=False),
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
            pystray.MenuItem(
                "Rechercher les mises à jour",
                lambda *_: self._check_updates_now(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Lancer au démarrage",
                lambda *_: self._toggle_autostart(),
                checked=lambda _: self.autostart_is_enabled(),
            ),
        ]
        if self.available_update is not None:
            items.extend(
                (
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem(
                        f"Télécharger BD-1 v{self.available_update.version}",
                        lambda *_: self._download_update(),
                    ),
                )
            )
        items.extend(
            (
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quitter", lambda *_: self.stop_callback()),
            )
        )
        return pystray.Menu(*items)

    def _check_updates(self, icon: pystray.Icon) -> None:
        self._ui_dispatcher.dispatch(lambda: setattr(icon, "visible", True))
        while not self._update_check_stop.is_set():
            update = find_update()
            if update is not None:
                self._set_available_update(icon, update)
                return
            if self._update_check_stop.wait(UPDATE_CHECK_INTERVAL_SECONDS):
                return

    def _check_updates_now(self) -> None:
        threading.Thread(target=self._check_updates_now_worker, daemon=True).start()

    def _check_updates_now_worker(self) -> None:
        update = find_update()
        if update is None:
            self._notify_update("Aucune nouvelle version détectée.")
            return
        self._set_available_update(self.icon, update)

    def _set_available_update(self, icon: pystray.Icon, update: AvailableUpdate) -> None:
        self._ui_dispatcher.dispatch(lambda: self._set_available_update_on_ui(icon, update))

    def _set_available_update_on_ui(self, icon: pystray.Icon, update: AvailableUpdate) -> None:
        self.available_update = update
        icon.menu = self._menu()
        icon.update_menu()
        self._notify_update(f"BD-1 v{update.version} est disponible au téléchargement.", icon)

    def _notify_update(self, message: str, icon: pystray.Icon | None = None) -> None:
        target = icon if icon is not None else self.icon
        self._ui_dispatcher.dispatch(lambda: self._notify_update_on_ui(target, message))

    def _notify_update_on_ui(self, icon: pystray.Icon, message: str) -> None:
        if self.notifications_enabled and icon.HAS_NOTIFICATION:
            try:
                icon.notify(message, "Mise à jour de BD-1")
            except Exception:
                LOGGER.info("Could not display the update notification", exc_info=True)

    def _download_update(self) -> None:
        if self.available_update is not None:
            webbrowser.open(self.available_update.download_url)

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
