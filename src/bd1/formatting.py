# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from datetime import datetime

from bd1.calendar import is_working_day
from bd1.models import (
    WEEKLY_DECLARATION_TARGET_HOURS,
    DailyReport,
    Observation,
    ObservationType,
    TimeBlock,
    WeeklyReport,
)


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes = remainder // 60
    return f"{hours} h {minutes:02d}"


def format_daily_report(report: DailyReport) -> str:
    lines = [f"BD-1 daily report - {report.date}", ""]
    lines.append("Suggested interpretation:")
    _append_timeline_blocks(lines, report.work_blocks, report.break_blocks)
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

    lines.extend(["", "Observed timeline:"])
    visible_observations = _visible_observations(report.observations)
    if visible_observations:
        for observation in visible_observations:
            lines.append(f"- {_format_time(observation.observed_at)} {observation.type.value}")
    else:
        lines.append("- No observations")

    return "\n".join(lines)


def format_weekly_report(
    report: WeeklyReport,
    apply_weekly_cap: bool = False,
    weekly_cap_hours: int = WEEKLY_DECLARATION_TARGET_HOURS,
) -> str:
    lines = [f"BD-1 weekly report - week of {report.week_start}", ""]
    declaration = report.declaration_for(weekly_cap_hours) if apply_weekly_cap else None
    days = declaration.proposed_days if declaration is not None else report.days
    for day in days:
        if not is_working_day(datetime.fromisoformat(day.date).date()):
            continue
        if not day.observations:
            lines.append(f"{day.date}: no observations")
            lines.append("")
            continue

        lines.append(f"{day.date}: {format_duration(day.worked_seconds)} worked")
        _append_timeline_blocks(lines, day.work_blocks, day.break_blocks, prefix="  ")
        for anomaly in day.anomalies:
            lines.append(f"  - {anomaly}")
        lines.append("")
    worked_seconds = (
        declaration.proposed_seconds if declaration is not None else report.worked_seconds
    )
    lines.append(f"Weekly total: {format_duration(worked_seconds)}")
    return "\n".join(lines)


def _append_timeline_blocks(
    lines: list[str],
    work_blocks: tuple[TimeBlock, ...],
    break_blocks: tuple[TimeBlock, ...],
    prefix: str = "",
) -> None:
    blocks = sorted((*work_blocks, *break_blocks), key=lambda block: (block.start, block.end))
    if not blocks:
        lines.append(f"{prefix}- No interpreted blocks")
        return
    for block in blocks:
        title = "Work" if block.label == "work" else "Break"
        lines.append(
            f"{prefix}- {title}: {_format_time(block.start)} -> {_format_time(block.end)} "
            f"({format_duration(block.seconds)})"
        )


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def _visible_observations(observations: tuple[Observation, ...]) -> tuple[Observation, ...]:
    return tuple(
        observation
        for observation in observations
        if observation.type != ObservationType.APP_HEARTBEAT
    )
