from __future__ import annotations

import argparse
from datetime import date, datetime

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
    args = parser.parse_args()

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

        from bd1.app import BD1Application
        from bd1.settings import load_settings

        BD1Application(settings=load_settings(), store=store).run()
    finally:
        store.close()


def _parse_date(value: str | None) -> date:
    if value is None:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    main()
