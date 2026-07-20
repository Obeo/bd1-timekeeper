# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import date, datetime, timedelta
from enum import StrEnum
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from threading import Thread
from typing import Any, Literal

from bd1.calendar import is_working_day
from bd1.formatting import format_duration
from bd1.models import DailyReport, Observation, ObservationType, TimeBlock, WeeklyReport
from bd1.reports import ReportService


class ReportView(StrEnum):
    DAY = "day"
    WEEK = "week"


ReportCommand = Literal["close", "focus"]
ReportWindowClosed = Callable[["ReportWindow"], None]

_WEEKDAYS = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)


class ReportWindow:
    """Control the separate process that owns the single Tk report window."""

    def __init__(
        self,
        database_path: Path,
        initial_view: ReportView,
        initial_date: date,
        on_closed: ReportWindowClosed,
    ) -> None:
        self.database_path = database_path
        self.initial_view = initial_view
        self.initial_date = initial_date
        self.on_closed = on_closed
        self._context = get_context("spawn")
        self._commands: Any = self._context.Queue()
        self._process: Any = None
        self._monitor_thread: Thread | None = None

    def start(self) -> None:
        self._process = self._context.Process(
            target=_run_report_window_process,
            args=(self.database_path, self.initial_view, self.initial_date, self._commands),
            name="bd1-report-window",
        )
        self._process.daemon = True
        self._process.start()
        self._monitor_thread = Thread(
            target=self._wait_for_process,
            name="bd1-report-window-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def focus(self) -> None:
        if self.is_alive():
            self._commands.put("focus")

    def close(self) -> None:
        process = self._process
        if process is None or not process.is_alive():
            return
        with suppress(BrokenPipeError, OSError):
            self._commands.put("close")
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)

    def _wait_for_process(self) -> None:
        process = self._process
        if process is not None:
            process.join()
        self.on_closed(self)


def _run_report_window_process(
    database_path: Path,
    initial_view: ReportView,
    initial_date: date,
    commands: Any,
) -> None:
    from bd1.storage import ObservationStore

    store = ObservationStore(database_path)
    try:
        _ReportWindowUI(ReportService(store), initial_view, initial_date, commands).run()
    finally:
        store.close()


class _ReportWindowUI:
    """Tk implementation running in the report process' main thread."""

    def __init__(
        self,
        report_service: ReportService,
        initial_view: ReportView,
        initial_date: date,
        commands: Any,
    ) -> None:
        self.report_service = report_service
        self.initial_view = initial_view
        self.initial_date = initial_date
        self._commands = commands

    def run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.title("BD-1 - Rapports")
        root.geometry("900x700")
        root.minsize(680, 500)

        current_view = self.initial_view
        current_date = _normalize_date(self.initial_view, self.initial_date)

        view_var = tk.StringVar(value=current_view.value)
        scope_var = tk.StringVar()
        worked_var = tk.StringVar()
        break_var = tk.StringVar()
        correction_var = tk.StringVar()
        correction_explanation_var = tk.StringVar()
        status_message_var = tk.StringVar()

        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        header = tk.Frame(root, padx=16, pady=4)
        header.grid(row=0, column=0, sticky="ew", pady=(10, 0))
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Rapports BD-1",
            anchor="w",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")

        mode_bar = tk.Frame(header)
        mode_bar.grid(row=0, column=1, sticky="e")
        tk.Radiobutton(
            mode_bar,
            text="Jour",
            value=ReportView.DAY.value,
            variable=view_var,
            indicatoron=False,
            padx=12,
            pady=4,
            command=lambda: set_view(ReportView.DAY),
        ).pack(side="left")
        tk.Radiobutton(
            mode_bar,
            text="Semaine",
            value=ReportView.WEEK.value,
            variable=view_var,
            indicatoron=False,
            padx=12,
            pady=4,
            command=lambda: set_view(ReportView.WEEK),
        ).pack(side="left")

        navigation = tk.Frame(root, padx=16, pady=4)
        navigation.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        navigation.columnconfigure(3, weight=1)

        previous_button = tk.Button(navigation, text="\u2039", width=3, command=lambda: move(-1))
        previous_button.grid(row=0, column=0, padx=(0, 4))
        today_button = tk.Button(navigation, text="Aujourd'hui", command=lambda: go_to_today())
        today_button.grid(row=0, column=1, padx=4)
        next_button = tk.Button(navigation, text="\u203a", width=3, command=lambda: move(1))
        next_button.grid(row=0, column=2, padx=4)
        tk.Label(navigation, textvariable=scope_var, anchor="e").grid(
            row=0, column=3, sticky="e", padx=(16, 0)
        )

        summary = tk.Frame(root, padx=16, pady=4)
        summary.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        for column in range(3):
            summary.columnconfigure(column, weight=1)

        tk.Label(summary, text="Travail estimé", anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(
            summary,
            textvariable=worked_var,
            anchor="w",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=1, column=0, sticky="w")
        tk.Label(summary, text="Pause estimée", anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(
            summary,
            textvariable=break_var,
            anchor="w",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=1, column=1, sticky="w")
        tk.Label(
            summary,
            text="Correction depuis le 1er juin",
            anchor="w",
        ).grid(row=0, column=2, sticky="w")
        tk.Label(
            summary,
            textvariable=correction_var,
            anchor="w",
            font=("TkDefaultFont", 12, "bold"),
        ).grid(row=1, column=2, sticky="w")
        tk.Label(
            summary,
            textvariable=correction_explanation_var,
            anchor="w",
            font=("TkDefaultFont", 9, "italic"),
        ).grid(row=2, column=2, sticky="w")
        content_frame = tk.Frame(root, padx=16)
        content_frame.grid(row=3, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        text = tk.Text(
            content_frame,
            wrap="word",
            padx=14,
            pady=12,
            relief="groove",
            borderwidth=1,
            takefocus=True,
        )
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(content_frame, command=text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)
        text.tag_configure("section", font=("TkDefaultFont", 11, "bold"), spacing1=10)
        text.tag_configure("work", foreground="#176b45")
        text.tag_configure("break", foreground="#985000")
        text.tag_configure("muted", foreground="#666666")

        footer = tk.Frame(root, padx=16, pady=4)
        footer.grid(row=4, column=0, sticky="ew", pady=(6, 10))
        tk.Label(footer, textvariable=status_message_var, anchor="w").pack(side="left")

        def copy_report(_event: Any = None) -> str:
            try:
                content = text.get("sel.first", "sel.last")
            except tk.TclError:
                content = text.get("1.0", "end-1c")
            if not content:
                return "break"
            root.clipboard_clear()
            root.clipboard_append(content)
            root.update_idletasks()
            status_message_var.set("Copié dans le presse-papiers")
            root.after(1500, lambda: status_message_var.set(""))
            return "break"

        def select_all(_event: Any = None) -> str:
            text.tag_add("sel", "1.0", "end-1c")
            return "break"

        text.bind("<Control-c>", copy_report)
        text.bind("<Control-C>", copy_report)
        text.bind("<Command-c>", copy_report)
        text.bind("<Control-a>", select_all)
        text.bind("<Control-A>", select_all)

        window_closed = False

        def close_window() -> None:
            nonlocal window_closed
            if window_closed:
                return
            window_closed = True
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", close_window)
        root.bind("<Escape>", lambda _event: close_window())

        def set_view(view: ReportView, target_date: date | None = None) -> None:
            nonlocal current_view, current_date
            current_view = view
            current_date = _normalize_date(view, target_date or current_date)
            view_var.set(view.value)
            render()

        def go_to_today() -> None:
            set_view(current_view, date.today())

        def move(direction: int) -> None:
            nonlocal current_date
            if current_view == ReportView.DAY:
                next_date = _move_workday(current_date, direction)
            else:
                next_date = current_date + timedelta(days=7 * direction)
            if direction > 0 and next_date > _normalize_date(current_view, date.today()):
                return
            current_date = next_date
            render()

        def navigate(_event: Any, direction: int) -> str:
            move(direction)
            return "break"

        def day_at(event: Any) -> date | None:
            try:
                tags = text.tag_names(text.index(f"@{event.x},{event.y}"))
            except tk.TclError:
                return None
            for tag in tags:
                if tag.startswith("day-heading-"):
                    return date.fromisoformat(tag.removeprefix("day-heading-"))
            return None

        def open_day_from_click(event: Any) -> str | None:
            target_date = day_at(event)
            if target_date is None:
                return None
            set_view(ReportView.DAY, target_date)
            return "break"

        def update_cursor(event: Any) -> None:
            text.configure(cursor="hand2" if day_at(event) is not None else "xterm")

        root.bind_all("<Alt-Left>", lambda event: navigate(event, -1))
        root.bind_all("<Alt-Right>", lambda event: navigate(event, 1))
        text.bind("<Button-1>", open_day_from_click)
        text.bind("<Motion>", update_cursor)
        text.bind("<Leave>", lambda _event: text.configure(cursor="xterm"))

        def render() -> None:
            if current_view == ReportView.DAY:
                report = self.report_service.daily(current_date)
                _render_daily(text, report)
                worked_var.set(format_duration(report.worked_seconds))
                break_var.set(format_duration(report.break_seconds))
            else:
                report = self.report_service.weekly(current_date)
                _render_weekly(text, report)
                worked_var.set(format_duration(report.worked_seconds))
                break_var.set(format_duration(report.break_seconds))
            correction_seconds = self.report_service.all_time_correction_seconds()
            correction_var.set(format_correction(correction_seconds))
            correction_explanation_var.set(format_correction_explanation(correction_seconds))

            scope_var.set(_scope_title(current_view, current_date))
            today_button.configure(
                state="disabled" if _is_today(current_view, current_date) else "normal"
            )
            next_button.configure(
                state="disabled" if _is_latest(current_view, current_date) else "normal"
            )
            status_message_var.set("")
            text.configure(state="disabled")
            text.see("1.0")

        def process_commands() -> None:
            try:
                while True:
                    command: ReportCommand = self._commands.get_nowait()
                    if command == "close":
                        close_window()
                        return
                    if command == "focus":
                        root.deiconify()
                        root.lift()
                        root.focus_force()
            except Empty:
                pass
            root.after(100, process_commands)

        render()
        root.after(100, process_commands)
        root.mainloop()


def _normalize_date(view: ReportView, target_date: date) -> date:
    if view == ReportView.WEEK:
        return target_date - timedelta(days=target_date.weekday())
    while not is_working_day(target_date):
        target_date -= timedelta(days=1)
    return target_date


def _move_workday(current_date: date, direction: int) -> date:
    next_date = current_date + timedelta(days=direction)
    while not is_working_day(next_date):
        next_date += timedelta(days=direction)
    return next_date


def format_correction(seconds: int) -> str:
    hours = seconds / (60 * 60)
    return f"{hours:+.1f} h".replace(".", ",")


def format_correction_explanation(seconds: int) -> str:
    hours = seconds / (60 * 60)
    absolute_hours = f"{abs(hours):.1f} h".replace(".", ",")
    if seconds < 0:
        return f"{absolute_hours} en moins que la référence"
    if seconds > 0:
        return f"{absolute_hours} en plus que la référence"
    return "À l'équilibre"


def _is_today(view: ReportView, current_date: date) -> bool:
    return _normalize_date(view, current_date) == _normalize_date(view, date.today())


def _is_latest(view: ReportView, current_date: date) -> bool:
    return _normalize_date(view, current_date) >= _normalize_date(view, date.today())


def _scope_title(view: ReportView, current_date: date) -> str:
    if view == ReportView.DAY:
        return _format_date(current_date)
    week_end = current_date + timedelta(days=4)
    return f"Semaine du {_format_date(current_date)} au {_format_date(week_end)}"


def _format_date(value: date) -> str:
    return f"{_WEEKDAYS[value.weekday()]} {value.day} {_MONTHS[value.month - 1]} {value.year}"


def _render_daily(text: Any, report: DailyReport) -> None:
    _clear(text)
    _insert_section(text, "Interprétation")
    blocks = _sorted_blocks(report)
    if blocks:
        for block in blocks:
            _insert_block(text, block)
    else:
        _insert_line(text, "Aucune plage interprétée.", "muted")

    _insert_section(text, "Chronologie observée")
    observations = _visible_observations(report.observations)
    if observations:
        for observation in observations:
            _insert_line(text, f"{_format_time(observation.observed_at)}  {observation.type.value}")
    else:
        _insert_line(text, "Aucune information.", "muted")


def _render_weekly(text: Any, report: WeeklyReport) -> None:
    _clear(text)
    days = tuple(day for day in report.days if is_working_day(date.fromisoformat(day.date)))
    for index, day in enumerate(days):
        day_date = date.fromisoformat(day.date)
        tag = f"day-heading-{day.date}"
        text.tag_configure(tag, font=("TkDefaultFont", 10, "bold"), foreground="#175a7a")
        text.insert("end", _format_date(day_date), (tag,))
        text.insert("end", "\n")

        if not _visible_observations(day.observations):
            _insert_line(text, "Aucune information.", "muted")
        else:
            _insert_line(text, f"Travail estimé : {format_duration(day.worked_seconds)}")
            blocks = _sorted_blocks(day)
            if blocks:
                for block in blocks:
                    _insert_block(text, block, indent="  ")
            else:
                _insert_line(text, "Aucune plage interprétée.", "muted")
        if index < len(report.days) - 1:
            _insert_line(text, "", "muted")


def _sorted_blocks(report: DailyReport) -> tuple[TimeBlock, ...]:
    return tuple(sorted((*report.work_blocks, *report.break_blocks), key=lambda block: block.start))


def _insert_block(text: Any, block: TimeBlock, indent: str = "") -> None:
    label = "Travail" if block.label == "work" else "Pause"
    tag = "work" if block.label == "work" else "break"
    text.insert(
        "end",
        f"{indent}{label:<8} {_format_time(block.start)} -> {_format_time(block.end)}  "
        f"{format_duration(block.seconds)}\n",
        (tag,),
    )


def _insert_section(text: Any, title: str) -> None:
    text.insert("end", f"{title}\n", ("section",))


def _insert_line(text: Any, value: str, tag: str | None = None) -> None:
    text.insert("end", f"{value}\n", (tag,) if tag else ())


def _clear(text: Any) -> None:
    text.configure(state="normal")
    text.delete("1.0", "end")


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def _visible_observations(observations: tuple[Observation, ...]) -> tuple[Observation, ...]:
    return tuple(
        observation
        for observation in observations
        if observation.type != ObservationType.APP_HEARTBEAT
    )
