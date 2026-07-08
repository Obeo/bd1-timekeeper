from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

import pystray
from PIL import Image

from bd1.formatting import format_daily_report, format_weekly_report
from bd1.models import ObservationType, RuntimeState
from bd1.paths import icon_dir
from bd1.reports import ReportService
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
        report_service: ReportService,
        add_observation: ObservationRecorder,
        stop_callback: Callable[[], None],
    ) -> None:
        self.store = store
        self.report_service = report_service
        self.add_observation = add_observation
        self.stop_callback = stop_callback
        self.state = RuntimeState.PC_ON
        self.icon = pystray.Icon("BD-1", self._load_image(self.state), "BD-1", self._menu())

    def run(self) -> None:
        self.icon.run()

    def stop(self) -> None:
        self.icon.stop()

    def set_state(self, state: RuntimeState) -> None:
        self.state = state
        self.icon.icon = self._load_image(state)
        self.icon.menu = self._menu()
        self.icon.update_menu()

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("BD-1", None, enabled=False),
            pystray.MenuItem(f"Etat : {self._state_label()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Marquer : debut de travail",
                lambda *_: self.add_observation(
                    ObservationType.USER_WORKING,
                    None,
                    {"source": "tray"},
                ),
            ),
            pystray.MenuItem(
                "Marquer : debut de pause",
                lambda *_: self.add_observation(
                    ObservationType.USER_BREAK,
                    None,
                    {"source": "tray"},
                ),
            ),
            pystray.MenuItem("Rapport du jour", lambda *_: self._show_daily_report()),
            pystray.MenuItem("Rapport de la semaine", lambda *_: self._show_weekly_report()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", lambda *_: self.stop_callback()),
        )

    def _show_daily_report(self) -> None:
        self._show_text_window(
            "BD-1 - Rapport du jour", format_daily_report(self.report_service.daily())
        )

    def _show_weekly_report(self) -> None:
        self._show_text_window(
            "BD-1 - Rapport de la semaine",
            format_weekly_report(self.report_service.weekly()),
        )

    def _show_text_window(self, title: str, content: str) -> None:
        thread = threading.Thread(target=self._open_text_window, args=(title, content), daemon=True)
        thread.start()

    @staticmethod
    def _open_text_window(title: str, content: str) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.title(title)
        root.geometry("760x520")
        text = tk.Text(root, wrap="word", padx=12, pady=12)
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        root.mainloop()

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
            RuntimeState.OFFLINE: "arrete",
            RuntimeState.PC_ON: "PC demarre",
            RuntimeState.ACTIVE: "travail probable",
            RuntimeState.IDLE: "pause probable",
        }
        return labels[self.state]
