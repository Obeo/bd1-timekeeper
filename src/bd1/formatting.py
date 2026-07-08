from __future__ import annotations

from datetime import datetime

from bd1.models import DailyReport, TimeBlock, WeeklyReport


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes = remainder // 60
    return f"{hours} h {minutes:02d}"


def format_daily_report(report: DailyReport) -> str:
    lines = [f"BD-1 daily report - {report.date}", ""]
    lines.append("Observed timeline:")
    if report.observations:
        for observation in report.observations:
            lines.append(f"- {_format_time(observation.observed_at)} {observation.type.value}")
    else:
        lines.append("- No observations")

    lines.extend(["", "Suggested interpretation:"])
    _append_blocks(lines, "Work", report.work_blocks)
    _append_blocks(lines, "Break", report.break_blocks)
    lines.extend(
        [
            "",
            f"Estimated worked time: {format_duration(report.worked_seconds)}",
            f"Estimated break time: {format_duration(report.break_seconds)}",
        ]
    )

    if report.anomalies:
        lines.extend(["", "Anomalies:"])
        lines.extend(f"- {anomaly}" for anomaly in report.anomalies)

    return "\n".join(lines)


def format_weekly_report(report: WeeklyReport) -> str:
    lines = [f"BD-1 weekly report - week of {report.week_start}", ""]
    for day in report.days:
        lines.append(f"{day.date}: {format_duration(day.worked_seconds)} worked")
        for anomaly in day.anomalies:
            lines.append(f"  - {anomaly}")
    lines.extend(["", f"Weekly total: {format_duration(report.worked_seconds)}"])
    return "\n".join(lines)


def _append_blocks(lines: list[str], title: str, blocks: tuple[TimeBlock, ...]) -> None:
    if not blocks:
        lines.append(f"- {title}: none")
        return
    for block in blocks:
        lines.append(
            f"- {title}: {_format_time(block.start)} -> {_format_time(block.end)} "
            f"({format_duration(block.seconds)})"
        )


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M")
