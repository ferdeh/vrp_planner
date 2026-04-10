"""Time conversion helpers."""

from __future__ import annotations

from datetime import time


def hhmm_to_minutes(value: str | time) -> int:
    """Convert HH:MM string or time object to minutes from midnight."""

    if isinstance(value, time):
        return value.hour * 60 + value.minute
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def minutes_to_hhmm(value: int) -> str:
    """Convert minutes from midnight to HH:MM."""

    normalized = max(value, 0) % (24 * 60)
    hours = normalized // 60
    minutes = normalized % 60
    return f"{hours:02d}:{minutes:02d}"


def elapsed_minutes(start_value: str | time | None, end_value: str | time | None) -> int | None:
    """Return elapsed minutes between HH:MM values, allowing next-day wrap once."""

    if start_value is None or end_value is None:
        return None

    start_minutes = hhmm_to_minutes(start_value)
    end_minutes = hhmm_to_minutes(end_value)
    if end_minutes < start_minutes:
        end_minutes += 24 * 60
    return end_minutes - start_minutes


def clamp_window(start_minutes: int, end_minutes: int) -> tuple[int, int]:
    """Ensure window bounds are ordered."""

    if end_minutes < start_minutes:
        return start_minutes, start_minutes
    return start_minutes, end_minutes
