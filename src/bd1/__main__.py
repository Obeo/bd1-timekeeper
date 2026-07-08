from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from importlib.util import find_spec

from bd1.formatting import format_daily_report, format_weekly_report
from bd1.models import ObservationType
from bd1.reports import ReportService
from bd1.storage import ObservationStore


def main() -> None:
    parser = argparse.ArgumentParser(description="BD-1 desktop companion")
    parser.add_argument("--report", choices=("today", "week"), help="Print a report and exit.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument(
        "--mark-working", action="store_true", help="Add a manual working observation."
    )
    parser.add_argument("--mark-break", action="store_true", help="Add a manual break observation.")
    parser.add_argument(
        "--diagnose-desktop",
        action="store_true",
        help="Print desktop/tray diagnostics and exit.",
    )
    parser.add_argument(
        "--profile-runtime",
        action="store_true",
        help="Print lightweight process resource diagnostics and exit.",
    )
    parser.add_argument(
        "--no-activity-monitor",
        action="store_true",
        help="Run the tray app without keyboard/mouse activity listeners.",
    )
    args = parser.parse_args()

    if args.diagnose_desktop:
        print(_desktop_diagnostics())
        return
    if args.profile_runtime:
        print(_runtime_profile())
        return

    store = ObservationStore()
    try:
        if args.mark_working:
            store.add(ObservationType.USER_WORKING, metadata={"source": "cli"})
            return
        if args.mark_break:
            store.add(ObservationType.USER_BREAK, metadata={"source": "cli"})
            return
        if args.report:
            target_date = _parse_date(args.date)
            reports = ReportService(store)
            if args.report == "today":
                print(format_daily_report(reports.daily(target_date)))
            else:
                print(format_weekly_report(reports.weekly(target_date)))
            return

        try:
            from bd1.app import BD1Application
            from bd1.settings import load_settings
        except ModuleNotFoundError as error:
            if error.name in {"PIL", "pynput", "pystray"}:
                print(
                    "BD-1 desktop dependencies are not installed. "
                    'Run: python -m pip install -e ".[desktop]"',
                    file=sys.stderr,
                )
                raise SystemExit(2) from error
            if error.name == "tkinter":
                print(
                    "BD-1 needs tkinter for report windows. "
                    "On openSUSE, install it with: sudo zypper install python313-tk",
                    file=sys.stderr,
                )
                raise SystemExit(2) from error
            raise

        BD1Application(
            settings=load_settings(),
            store=store,
            activity_monitor_enabled=not args.no_activity_monitor,
        ).run()
    finally:
        store.close()


def _parse_date(value: str | None) -> date:
    if value is None:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _desktop_diagnostics() -> str:
    lines = ["BD-1 desktop diagnostics"]
    for name in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "DISPLAY", "WAYLAND_DISPLAY"):
        lines.append(f"{name}: {os.environ.get(name, '<unset>')}")

    for module in ("PIL", "pynput", "pystray", "tkinter"):
        lines.append(f"{module}: {'available' if find_spec(module) else 'missing'}")

    if find_spec("pystray"):
        import pystray

        lines.append(f"pystray backend: {pystray.Icon.__module__}")
        lines.append(f"pystray HAS_MENU: {getattr(pystray.Icon, 'HAS_MENU', None)}")
        lines.append(f"pystray HAS_NOTIFICATION: {getattr(pystray.Icon, 'HAS_NOTIFICATION', None)}")

    return "\n".join(lines)


def _runtime_profile() -> str:
    import psutil

    process = psutil.Process()
    memory = process.memory_info()
    lines = ["BD-1 runtime profile"]
    lines.append(f"pid: {process.pid}")
    lines.append(f"rss_mb: {memory.rss / 1024 / 1024:.1f}")
    lines.append(f"vms_mb: {memory.vms / 1024 / 1024:.1f}")
    lines.append(f"threads: {process.num_threads()}")
    lines.append(f"cpu_percent: {process.cpu_percent(interval=0.1):.1f}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
