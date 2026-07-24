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
from multiprocessing import get_context
from queue import Empty
from threading import Thread
from typing import Any

from bd1.mattermost import (
    MattermostError,
    delete_token,
    get_token,
    normalize_server_url,
    remove_bd1_status,
    store_token,
    verify_token,
)
from bd1.settings import DEFAULT_VPN_INTERFACE_PATTERNS, Settings, load_settings, save_settings
from bd1.window_icon import apply_window_icon

MattermostWindowClosed = Callable[["MattermostWindow"], None]


class MattermostWindow:
    """Control the separate process that owns the Mattermost settings window."""

    def __init__(self, on_closed: MattermostWindowClosed) -> None:
        self.on_closed = on_closed
        self._context = get_context("spawn")
        self._commands: Any = self._context.Queue()
        self._process: Any = None

    def start(self) -> None:
        self._process = self._context.Process(
            target=_run_mattermost_window_process,
            args=(self._commands,),
            name="bd1-mattermost-window",
        )
        self._process.daemon = True
        self._process.start()
        Thread(
            target=self._wait_for_process,
            name="bd1-mattermost-window-monitor",
            daemon=True,
        ).start()

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


def configure_mattermost(
    settings: Settings,
    server_url: str,
    token: str,
    vpn_patterns: str,
) -> Settings:
    normalized_url = normalize_server_url(server_url)
    normalized_token = token.strip()
    if not normalized_token:
        normalized_token = get_token(normalized_url) or ""
    if not normalized_token:
        raise ValueError("Le jeton d'accès personnel est obligatoire.")

    patterns = _parse_vpn_patterns(vpn_patterns)
    verify_token(normalized_url, normalized_token)
    if token.strip():
        store_token(normalized_url, normalized_token)

    updated = replace(
        settings,
        mattermost_url=normalized_url,
        vpn_interface_patterns=patterns,
    )
    save_settings(updated)
    if settings.mattermost_url and settings.mattermost_url != normalized_url:
        with suppress(MattermostError):
            delete_token(settings.mattermost_url)
    return updated


def disable_mattermost(settings: Settings) -> tuple[Settings, tuple[str, ...]]:
    warnings: list[str] = []
    server_url = settings.mattermost_url
    if server_url:
        token = None
        try:
            token = get_token(server_url)
            if token is not None:
                remove_bd1_status(server_url, token)
        except MattermostError as error:
            warnings.append(str(error))
        if token is not None:
            try:
                delete_token(server_url)
            except MattermostError as error:
                warnings.append(str(error))

    updated = replace(settings, mattermost_url="")
    save_settings(updated)
    return updated, tuple(warnings)


def _parse_vpn_patterns(value: str) -> tuple[str, ...]:
    patterns = tuple(
        dict.fromkeys(
            pattern.strip()
            for line in value.splitlines()
            for pattern in line.split(",")
            if pattern.strip()
        )
    )
    return patterns or DEFAULT_VPN_INTERFACE_PATTERNS


def _run_mattermost_window_process(commands: Any) -> None:
    _MattermostWindowUI(load_settings(), commands).run()


class _MattermostWindowUI:
    def __init__(self, settings: Settings, commands: Any) -> None:
        self.settings = settings
        self._commands = commands

    def run(self) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        root = tk.Tk()
        root.title("BD-1 - Intégration Mattermost")
        apply_window_icon(root)
        root.resizable(False, False)

        server_var = tk.StringVar(value=self.settings.mattermost_url)
        token_var = tk.StringVar()
        patterns_var = tk.StringVar(value=", ".join(self.settings.vpn_interface_patterns))

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Serveur Mattermost (HTTPS)").grid(row=0, column=0, sticky="w")
        server_entry = ttk.Entry(frame, textvariable=server_var, width=58)
        server_entry.grid(row=1, column=0, sticky="ew", pady=(3, 12))

        ttk.Label(frame, text="Jeton d'accès personnel").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=token_var, show="•", width=58).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(3, 2),
        )
        ttk.Label(frame, text="Laisser vide pour conserver le jeton actuel.").grid(
            row=4,
            column=0,
            sticky="w",
            pady=(0, 12),
        )

        ttk.Label(frame, text="Interfaces VPN (motifs séparés par des virgules)").grid(
            row=5,
            column=0,
            sticky="w",
        )
        ttk.Entry(frame, textvariable=patterns_var, width=58).grid(
            row=6,
            column=0,
            sticky="ew",
            pady=(3, 14),
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, sticky="e")

        def save() -> None:
            try:
                self.settings = configure_mattermost(
                    self.settings,
                    server_var.get(),
                    token_var.get(),
                    patterns_var.get(),
                )
            except (MattermostError, ValueError) as error:
                messagebox.showerror("BD-1", str(error), parent=root)
                return
            messagebox.showinfo("BD-1", "L'intégration Mattermost est activée.", parent=root)
            root.destroy()

        def disable() -> None:
            if not messagebox.askyesno(
                "BD-1",
                "Désactiver l'intégration Mattermost ?",
                parent=root,
            ):
                return
            self.settings, warnings = disable_mattermost(self.settings)
            message = "L'intégration Mattermost est désactivée."
            if warnings:
                message += "\n\nLe nettoyage distant a échoué :\n" + "\n".join(warnings)
                messagebox.showwarning("BD-1", message, parent=root)
            else:
                messagebox.showinfo("BD-1", message, parent=root)
            root.destroy()

        ttk.Button(buttons, text="Désactiver", command=disable).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Annuler", command=root.destroy).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(buttons, text="Enregistrer", command=save).grid(row=0, column=2)

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.after(100, lambda: _process_commands(root, self._commands))
        root.after_idle(server_entry.focus_set)
        root.mainloop()


def _process_commands(root: Any, commands: Any) -> None:
    try:
        while True:
            command = commands.get_nowait()
            if command == "close":
                root.destroy()
                return
            if command == "focus":
                root.deiconify()
                root.lift()
                root.focus_force()
    except Empty:
        pass
    root.after(100, lambda: _process_commands(root, commands))
