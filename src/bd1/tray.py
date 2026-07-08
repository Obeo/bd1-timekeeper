from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta
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
        autostart_is_enabled: Callable[[], bool],
        toggle_autostart: Callable[[], bool],
        stop_callback: Callable[[], None],
    ) -> None:
        self.store = store
        self.report_service = report_service
        self.add_observation = add_observation
        self.autostart_is_enabled = autostart_is_enabled
        self.toggle_autostart = toggle_autostart
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
            pystray.MenuItem(
                "Lancer au demarrage",
                lambda *_: self._toggle_autostart(),
                checked=lambda _: self.autostart_is_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", lambda *_: self.stop_callback()),
        )

    def _toggle_autostart(self) -> None:
        self.toggle_autostart()
        self.icon.update_menu()

    def _show_daily_report(self) -> None:
        self._show_report_window("day")

    def _show_weekly_report(self) -> None:
        self._show_report_window("week")

    def _show_report_window(self, report_kind: str) -> None:
        thread = threading.Thread(
            target=self._open_report_window,
            args=(self.report_service, report_kind, date.today()),
            daemon=True,
        )
        thread.start()

    @staticmethod
    def _open_report_window(
        report_service: ReportService,
        report_kind: str,
        initial_date: date,
    ) -> None:
        import tkinter as tk

        current_date = initial_date
        step = timedelta(days=1 if report_kind == "day" else 7)
        base_title = (
            "BD-1 - Rapport du jour" if report_kind == "day" else "BD-1 - Rapport de la semaine"
        )

        root = tk.Tk()
        root.title(base_title)
        root.geometry("760x520")

        toolbar = tk.Frame(root)
        toolbar.pack(fill="x")

        title_label = tk.Label(toolbar, anchor="w")
        title_label.pack(side="left", fill="x", expand=True, padx=8, pady=6)

        text = tk.Text(root, wrap="word", padx=12, pady=12)
        text.pack(fill="both", expand=True)

        def render() -> None:
            if report_kind == "day":
                report = report_service.daily(current_date)
                content = format_daily_report(report)
                title_label.configure(text=report.date)
            else:
                report = report_service.weekly(current_date)
                content = format_weekly_report(report)
                title_label.configure(text=f"Week of {report.week_start}")

            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", content)
            text.configure(state="disabled")

        def move_back() -> None:
            nonlocal current_date
            current_date = current_date - step
            render()

        def move_forward() -> None:
            nonlocal current_date
            current_date = current_date + step
            render()

        previous_button = tk.Button(toolbar, text="Precedent", command=move_back)
        previous_button.pack(side="right", padx=(4, 8), pady=6)

        next_button = tk.Button(toolbar, text="Suivant", command=move_forward)
        next_button.pack(side="right", padx=4, pady=6)

        render()
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
