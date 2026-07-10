from __future__ import annotations

import os
import platform
import plistlib
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APP_ID = "com.bd1.app"
APP_NAME = "BD-1"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


@dataclass(frozen=True, slots=True)
class AutostartStatus:
    supported: bool
    enabled: bool
    location: Path | str | None
    detail: str = ""


class AutostartManager:
    def __init__(
        self,
        command: list[str] | None = None,
        platform_name: str | None = None,
    ) -> None:
        self.command = command or default_autostart_command()
        self.platform_name = platform_name or platform.system().lower()

    def status(self) -> AutostartStatus:
        if self._is_linux():
            path = self._linux_desktop_file()
            return AutostartStatus(True, path.exists(), path)
        if self._is_macos():
            path = self._macos_plist_file()
            return AutostartStatus(True, path.exists(), path)
        if self._is_windows():
            return self._windows_status()
        return AutostartStatus(False, False, None, f"Unsupported platform: {self.platform_name}")

    def is_enabled(self) -> bool:
        return self.status().enabled

    def enable(self) -> AutostartStatus:
        if self._is_linux():
            return self._enable_linux()
        if self._is_macos():
            return self._enable_macos()
        if self._is_windows():
            return self._enable_windows()
        return AutostartStatus(False, False, None, f"Unsupported platform: {self.platform_name}")

    def disable(self) -> AutostartStatus:
        if self._is_linux():
            path = self._linux_desktop_file()
            path.unlink(missing_ok=True)
            return AutostartStatus(True, False, path)
        if self._is_macos():
            path = self._macos_plist_file()
            path.unlink(missing_ok=True)
            return AutostartStatus(True, False, path)
        if self._is_windows():
            return self._disable_windows()
        return AutostartStatus(False, False, None, f"Unsupported platform: {self.platform_name}")

    def set_enabled(self, enabled: bool) -> AutostartStatus:
        if enabled:
            return self.enable()
        return self.disable()

    def refresh_if_enabled(self) -> AutostartStatus:
        """Rewrite an existing autostart entry with this application's current command."""
        status = self.status()
        if not status.enabled:
            return status
        return self.enable()

    def _enable_linux(self) -> AutostartStatus:
        path = self._linux_desktop_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "[Desktop Entry]",
                    "Type=Application",
                    f"Name={APP_NAME}",
                    "Comment=BD-1 desktop companion",
                    f"Exec={shlex.join(self.command)}",
                    "Terminal=false",
                    "X-GNOME-Autostart-enabled=true",
                    "Categories=Utility;",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return AutostartStatus(True, True, path)

    def _enable_macos(self) -> AutostartStatus:
        path = self._macos_plist_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as file:
            plistlib.dump(
                {
                    "Label": APP_ID,
                    "ProgramArguments": self.command,
                    "RunAtLoad": True,
                    "KeepAlive": False,
                },
                file,
            )
        return AutostartStatus(True, True, path)

    def _windows_status(self) -> AutostartStatus:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return AutostartStatus(True, True, WINDOWS_RUN_KEY)
        except FileNotFoundError:
            return AutostartStatus(True, False, WINDOWS_RUN_KEY)
        except OSError as error:
            return AutostartStatus(True, False, WINDOWS_RUN_KEY, str(error))

    def _enable_windows(self) -> AutostartStatus:
        import winreg

        command_line = subprocess.list2cmdline(self.command)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command_line)
        return AutostartStatus(True, True, WINDOWS_RUN_KEY)

    def _disable_windows(self) -> AutostartStatus:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                WINDOWS_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        return AutostartStatus(True, False, WINDOWS_RUN_KEY)

    def _linux_desktop_file(self) -> Path:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_home / "autostart" / "bd1.desktop"

    @staticmethod
    def _macos_plist_file() -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"

    def _is_linux(self) -> bool:
        return self.platform_name == "linux"

    def _is_macos(self) -> bool:
        return self.platform_name == "darwin"

    def _is_windows(self) -> bool:
        return self.platform_name == "windows"


def default_autostart_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "bd1"]
