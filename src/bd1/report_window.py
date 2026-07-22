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
from dataclasses import replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from multiprocessing import get_context
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from typing import Any, Literal

from bd1.calendar import is_working_day
from bd1.eurecia import (
    EureciaAuthenticationError,
    EureciaCredentialError,
    EureciaError,
    EureciaHttpClient,
    delete_password,
    eurecia_days_from_report,
    get_saved_password,
    store_password,
)
from bd1.formatting import format_duration
from bd1.macos_dock import DockController, create_dock_controller
from bd1.models import (
    DailyReport,
    Observation,
    ObservationType,
    TimeBlock,
    WeeklyReport,
)
from bd1.reports import ReportService
from bd1.settings import DEFAULT_WEEKLY_CAP_HOURS, Settings, load_settings, save_settings


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
DELETE_DAY_CONFIRMATION = (
    "Attention, tous les événements de cette journée vont être supprimés.\n\n"
    "BD-1 considérera ensuite cette journée comme sans information et ne "
    "l'utilisera plus dans les statistiques globales."
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
        process.join()

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
    from bd1.settings import load_settings
    from bd1.storage import ObservationStore

    settings = load_settings()
    store = ObservationStore(database_path)
    try:
        _ReportWindowUI(
            ReportService(
                store,
                lunch_automatic_work_resume=settings.lunch_automatic_work_resume,
            ),
            settings,
            initial_view,
            initial_date,
            commands,
        ).run()
    finally:
        store.close()


class _ReportWindowUI:
    """Tk implementation running in the report process' main thread."""

    def __init__(
        self,
        report_service: ReportService,
        settings: Settings,
        initial_view: ReportView,
        initial_date: date,
        commands: Any,
        dock_controller: DockController | None = None,
    ) -> None:
        self.report_service = report_service
        self.settings = settings
        self.initial_view = initial_view
        self.initial_date = initial_date
        self._commands = commands
        self._dock_controller = (
            dock_controller if dock_controller is not None else create_dock_controller()
        )
        self._eurecia_client: EureciaHttpClient | None = None
        self._eurecia_password: str | None = None
        self._eurecia_remember_password = False
        self._eurecia_password_was_saved = False
        self._eurecia_saved_password_rejected = False

    def run(self) -> None:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("BD-1 - Rapports")
        root.geometry("900x950")
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
        weekly_cap_var = tk.BooleanVar(value=self.settings.weekly_37h_cap_enabled)

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
        footer_left = tk.Frame(footer)
        footer_left.pack(side="left")
        status_label = tk.Label(footer_left, textvariable=status_message_var, anchor="w")
        status_label.pack(side="left")
        weekly_cap_button = tk.Checkbutton(
            footer_left,
            text=f"Plafond {self.settings.weekly_cap_hours}h",
            variable=weekly_cap_var,
            command=lambda: toggle_weekly_cap(),
        )
        weekly_cap_button.pack(side="left", before=status_label, padx=(0, 12))
        delete_button = tk.Button(
            footer,
            text="Supprimer la journée",
            command=lambda: delete_current_day(),
        )
        delete_button.pack(side="right")
        eurecia_button = tk.Button(
            footer,
            text="Pousser vers Eurecia",
            command=lambda: push_to_eurecia(),
        )

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
        push_in_progress = False

        def close_window() -> None:
            nonlocal window_closed
            if window_closed:
                return
            if push_in_progress:
                messagebox.showwarning(
                    "Envoi Eurecia en cours",
                    "Attendez la fin de la sauvegarde Eurecia avant de fermer le rapport.",
                    parent=root,
                )
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

        def toggle_weekly_cap() -> None:
            enabled = weekly_cap_var.get()
            save_settings(replace(load_settings(), weekly_37h_cap_enabled=enabled))
            self.settings = replace(self.settings, weekly_37h_cap_enabled=enabled)
            render()

        def delete_current_day() -> None:
            if current_view != ReportView.DAY:
                return
            if not messagebox.askyesno(
                "Supprimer la journée ?",
                DELETE_DAY_CONFIRMATION,
                parent=root,
            ):
                return
            deleted_count = self.report_service.delete_day(current_date)
            render()
            status_message_var.set(f"{deleted_count} événement(s) supprimé(s)")

        def eurecia_configuration() -> tuple[EureciaHttpClient, str] | None:
            from tkinter import simpledialog

            base_url = self.settings.eurecia_base_url
            email = self.settings.eurecia_email
            if not base_url:
                base_url = simpledialog.askstring(
                    "Configuration Eurecia",
                    "URL de votre instance Eurecia :\n"
                    "Format : https://<tenant>.eurecia.com/eurecia/",
                    initialvalue="https://",
                    parent=root,
                )
            if not base_url:
                return None
            if not email:
                email = simpledialog.askstring(
                    "Configuration Eurecia",
                    "Adresse e-mail Eurecia :",
                    parent=root,
                )
            if not email:
                return None
            password = self._eurecia_password
            if password is None:
                saved_password = None
                if not self._eurecia_saved_password_rejected:
                    try:
                        saved_password = get_saved_password(base_url, email)
                    except EureciaCredentialError as error:
                        messagebox.showwarning("Authentification Eurecia", str(error), parent=root)
                self._eurecia_password_was_saved = (
                    saved_password is not None or self._eurecia_saved_password_rejected
                )
                if saved_password is not None:
                    password = saved_password
                    self._eurecia_remember_password = True
                else:
                    credentials = _ask_eurecia_password(
                        root,
                        remember_default=self._eurecia_saved_password_rejected,
                    )
                    if credentials is None:
                        return None
                    password, self._eurecia_remember_password = credentials
            if not password:
                return None
            try:
                if (
                    self._eurecia_client is None
                    or self._eurecia_client.base_url != base_url.rstrip("/") + "/"
                ):
                    self._eurecia_client = EureciaHttpClient(base_url)
            except EureciaError as error:
                messagebox.showerror("Configuration Eurecia", str(error), parent=root)
                return None

            self._eurecia_password = password
            if base_url != self.settings.eurecia_base_url or email != self.settings.eurecia_email:
                self.settings = replace(
                    self.settings,
                    eurecia_base_url=base_url,
                    eurecia_email=email,
                )
                save_settings(
                    replace(
                        load_settings(),
                        eurecia_base_url=base_url,
                        eurecia_email=email,
                    )
                )
            return self._eurecia_client, password

        def push_to_eurecia() -> None:
            nonlocal push_in_progress
            if current_view != ReportView.WEEK or push_in_progress:
                return
            configured = eurecia_configuration()
            if configured is None:
                return
            client, password = configured
            report = self.report_service.weekly(current_date)
            apply_weekly_cap = self.settings.weekly_37h_cap_enabled
            weekly_cap_hours = self.settings.weekly_cap_hours
            email = self.settings.eurecia_email
            week = date.fromisoformat(report.week_start).isocalendar()
            remember_password = self._eurecia_remember_password
            password_was_saved = self._eurecia_password_was_saved
            replace_saved_password = self._eurecia_saved_password_rejected

            log_window = tk.Toplevel(root)
            log_window.title(f"Envoi Eurecia — {week.year}-W{week.week:02d}")
            log_window.geometry("720x460")
            log_window.minsize(520, 300)
            log_window.columnconfigure(0, weight=1)
            log_window.rowconfigure(0, weight=1)
            log_text = tk.Text(log_window, wrap="word", padx=12, pady=10, state="disabled")
            log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
            log_scrollbar = tk.Scrollbar(log_window, command=log_text.yview)
            log_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
            log_text.configure(yscrollcommand=log_scrollbar.set)
            log_text.tag_configure("success", foreground="#176b45")
            log_text.tag_configure("error", foreground="#b00020")

            def copy_log(_event: Any = None) -> str:
                try:
                    content = log_text.get("sel.first", "sel.last")
                except tk.TclError:
                    content = log_text.get("1.0", "end-1c")
                root.clipboard_clear()
                root.clipboard_append(content)
                root.update_idletasks()
                return "break"

            def select_all_log(_event: Any = None) -> str:
                log_text.tag_add("sel", "1.0", "end-1c")
                return "break"

            for shortcut in ("<Control-c>", "<Control-C>", "<Command-c>"):
                log_text.bind(shortcut, copy_log)
            for shortcut in ("<Control-a>", "<Control-A>", "<Command-a>"):
                log_text.bind(shortcut, select_all_log)
            close_log_button = tk.Button(
                log_window,
                text="Fermer",
                state="disabled",
                command=log_window.destroy,
            )
            close_log_button.grid(row=1, column=0, columnspan=2, pady=(0, 10))
            log_window.protocol("WM_DELETE_WINDOW", lambda: None)

            events: SimpleQueue[tuple[str, str]] = SimpleQueue()
            push_in_progress = True
            eurecia_button.configure(state="disabled")

            def worker() -> None:
                try:
                    events.put(("log", "Préparation des segments affichés dans BD-1."))
                    target_days = eurecia_days_from_report(
                        report,
                        apply_weekly_cap=apply_weekly_cap,
                        weekly_cap_hours=weekly_cap_hours,
                        vpn_interface_patterns=self.settings.vpn_interface_patterns,
                    )
                    segment_count = sum(len(day.segments) for day in target_days)
                    events.put(
                        (
                            "log",
                            f"{len(target_days)} journée(s), {segment_count} segment(s) à envoyer.",
                        )
                    )
                    if not client.is_authenticated():
                        events.put(("log", "Session absente ou expirée : authentification SSO."))
                        try:
                            client.login(email, password)
                        except EureciaAuthenticationError:
                            events.put(
                                (
                                    "authentication_failed",
                                    "Le mot de passe enregistré a été refusé."
                                    if password_was_saved
                                    else "",
                                )
                            )
                            raise
                        events.put(("log", "Authentification réussie."))
                        try:
                            if remember_password and (
                                not password_was_saved or replace_saved_password
                            ):
                                store_password(client.base_url, email, password)
                                events.put(("password_saved", ""))
                            elif not remember_password and password_was_saved:
                                delete_password(client.base_url, email)
                                events.put(("password_deleted", ""))
                        except EureciaCredentialError as error:
                            events.put(("warning", str(error)))
                    else:
                        events.put(("log", "Session Eurecia encore valide : réutilisation."))
                    client.replace_timesheet(
                        week.year,
                        week.week,
                        target_days,
                        progress=lambda message: events.put(("log", message)),
                    )
                except (EureciaError, ValueError) as error:
                    events.put(("error", str(error)))
                except Exception as error:
                    events.put(("error", f"Erreur inattendue : {error}"))
                else:
                    events.put(("success", "Envoi terminé avec succès."))
                finally:
                    events.put(("done", ""))

            def append_log(message: str, tag: str | None = None) -> None:
                log_text.configure(state="normal")
                log_text.insert("end", message + "\n", (tag,) if tag else ())
                log_text.configure(state="disabled")
                log_text.see("end")

            def poll_events() -> None:
                nonlocal push_in_progress
                finished = False
                while not events.empty():
                    kind, message = events.get()
                    if kind == "authentication_failed":
                        self._eurecia_password = None
                        self._eurecia_saved_password_rejected = password_was_saved
                        if message:
                            append_log(message, "error")
                    elif kind == "password_saved":
                        self._eurecia_password_was_saved = True
                        self._eurecia_saved_password_rejected = False
                    elif kind == "password_deleted":
                        self._eurecia_password_was_saved = False
                        self._eurecia_saved_password_rejected = False
                    elif kind == "warning":
                        append_log(f"AVERTISSEMENT — {message}")
                    elif kind == "error":
                        append_log(
                            f"ÉCHEC — {message}\n"
                            "La saisie automatique n'a pas fonctionné, "
                            "effectuez la saisie manuellement.",
                            "error",
                        )
                    elif kind == "success":
                        append_log(f"SUCCÈS — {message}", "success")
                    elif kind == "done":
                        finished = True
                    else:
                        append_log(message)
                if finished:
                    push_in_progress = False
                    eurecia_button.configure(state="normal")
                    close_log_button.configure(state="normal")
                    log_window.protocol("WM_DELETE_WINDOW", log_window.destroy)
                    return
                root.after(100, poll_events)

            Thread(target=worker, name="bd1-eurecia-push", daemon=True).start()
            root.after(100, poll_events)

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
                _render_weekly(
                    text,
                    report,
                    apply_weekly_cap=self.settings.weekly_37h_cap_enabled,
                    weekly_cap_hours=self.settings.weekly_cap_hours,
                )
                worked_seconds = (
                    report.declaration_for(self.settings.weekly_cap_hours).proposed_seconds
                    if self.settings.weekly_37h_cap_enabled
                    else report.worked_seconds
                )
                worked_var.set(format_duration(worked_seconds))
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
            if current_view == ReportView.WEEK:
                weekly_cap_button.pack(side="left", before=status_label, padx=(0, 12))
                delete_button.pack_forget()
                eurecia_button.pack(side="right")
            else:
                weekly_cap_button.pack_forget()
                eurecia_button.pack_forget()
                delete_button.pack(side="right")
            status_message_var.set("")
            text.configure(state="disabled")
            text.see("1.0")

        def process_commands() -> None:
            try:
                while True:
                    command: ReportCommand = self._commands.get_nowait()
                    if command == "close":
                        close_window()
                        if window_closed:
                            return
                    if command == "focus":
                        _focus_report_window(root, self._dock_controller)
            except Empty:
                pass
            root.after(100, process_commands)

        render()
        root.after(100, process_commands)
        _run_mainloop_with_dock(root, self._dock_controller)


def _run_mainloop_with_dock(root: Any, dock_controller: DockController) -> None:
    root.after_idle(dock_controller.show)
    try:
        root.mainloop()
    finally:
        dock_controller.hide()


def _focus_report_window(root: Any, dock_controller: DockController) -> None:
    dock_controller.show()
    root.deiconify()
    root.lift()
    root.focus_force()


def _ask_eurecia_password(
    parent: Any,
    *,
    remember_default: bool,
) -> tuple[str, bool] | None:
    import tkinter as tk

    result: tuple[str, bool] | None = None
    window = tk.Toplevel(parent)
    window.title("Authentification Eurecia")
    window.resizable(False, False)
    window.transient(parent)

    password = tk.StringVar()
    remember = tk.BooleanVar(value=remember_default)
    frame = tk.Frame(window, padx=16, pady=14)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="Mot de passe Eurecia / SSO :", anchor="w").pack(fill="x")
    entry = tk.Entry(frame, textvariable=password, show="*", width=42)
    entry.pack(fill="x", pady=(4, 10))
    tk.Checkbutton(
        frame,
        text="Mémoriser dans le trousseau système",
        variable=remember,
    ).pack(anchor="w")
    buttons = tk.Frame(frame)
    buttons.pack(anchor="e", pady=(14, 0))

    def submit() -> None:
        nonlocal result
        value = password.get()
        if value:
            result = value, remember.get()
            window.destroy()

    tk.Button(buttons, text="Annuler", command=window.destroy).pack(side="left", padx=(0, 8))
    tk.Button(buttons, text="Continuer", command=submit, default="active").pack(side="left")
    window.bind("<Return>", lambda _event: submit())
    window.bind("<Escape>", lambda _event: window.destroy())
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    entry.focus_set()
    window.grab_set()
    parent.wait_window(window)
    return result


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


def _render_weekly(
    text: Any,
    report: WeeklyReport,
    apply_weekly_cap: bool = False,
    weekly_cap_hours: int = DEFAULT_WEEKLY_CAP_HOURS,
) -> None:
    _clear(text)
    days = _displayed_week_days(report, apply_weekly_cap, weekly_cap_hours)
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
        if index < len(days) - 1:
            _insert_line(text, "", "muted")


def _displayed_week_days(
    report: WeeklyReport,
    apply_weekly_cap: bool,
    weekly_cap_hours: int,
) -> tuple[DailyReport, ...]:
    report_days = (
        report.declaration_for(weekly_cap_hours).proposed_days if apply_weekly_cap else report.days
    )
    return tuple(day for day in report_days if is_working_day(date.fromisoformat(day.date)))


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
