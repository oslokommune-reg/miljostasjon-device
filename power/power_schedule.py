# power_schedule.py
# ------------------------------------------------------------
# Pure decision logic for controlled shutdown before scheduled power cuts.
# No I/O here, so it can be unit tested (tests/test_power_schedule.py).
#
# All comparisons are done in UTC. Aware datetimes that share a tzinfo are
# compared by wall clock in Python, which gives wrong answers around the
# daylight saving changes; converting to UTC first avoids that.
# ------------------------------------------------------------

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Window:
    start: time
    end: time  # end <= start means the window ends the next day


@dataclass(frozen=True)
class PowerSchedule:
    tz: ZoneInfo
    windows: List[Window]
    shutdown_lead: timedelta  # shut down this long before the window ends
    start_tolerance: timedelta  # relay clock may run a bit ahead of ours
    unsynced_max_uptime: timedelta  # clock never synced: shut down after this
    outside_window_grace: timedelta  # booted outside a window: stay up this long


@dataclass(frozen=True)
class Decision:
    shutdown: bool
    reason: str


def _parse_hhmm(value, field: str) -> time:
    if not isinstance(value, str) or not _HHMM.match(value):
        raise ScheduleError(f"{field}: expected 'HH:MM', got {value!r}")
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _parse_minutes(data: dict, key: str, low: int, high: int) -> timedelta:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ScheduleError(f"{key}: expected integer {low}-{high}, got {value!r}")
    return timedelta(minutes=value)


def parse_schedule(data: dict) -> PowerSchedule:
    """Validate raw config (see config/power_schedule.json). Raises ScheduleError."""
    if not isinstance(data, dict):
        raise ScheduleError("schedule must be a JSON object")
    try:
        tz = ZoneInfo(data.get("timezone", ""))
    except Exception:
        raise ScheduleError(f"timezone: unknown zone {data.get('timezone')!r}")

    raw_windows = data.get("windows")
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ScheduleError("windows: expected a non-empty list")
    windows = []
    for i, w in enumerate(raw_windows):
        if not isinstance(w, dict):
            raise ScheduleError(f"windows[{i}]: expected an object")
        start = _parse_hhmm(w.get("start"), f"windows[{i}].start")
        end = _parse_hhmm(w.get("end"), f"windows[{i}].end")
        if start == end:
            raise ScheduleError(f"windows[{i}]: start and end are equal")
        windows.append(Window(start, end))

    return PowerSchedule(
        tz=tz,
        windows=windows,
        shutdown_lead=_parse_minutes(data, "shutdown_lead_minutes", 1, 60),
        start_tolerance=_parse_minutes(data, "start_tolerance_minutes", 0, 60),
        unsynced_max_uptime=_parse_minutes(data, "unsynced_max_uptime_minutes", 2, 240),
        outside_window_grace=_parse_minutes(data, "outside_window_grace_minutes", 2, 240),
    )


def _local_to_utc(day: date, t: time, tz: ZoneInfo) -> datetime:
    # A wall time that does not exist (spring forward) or exists twice (fall
    # back) is resolved by zoneinfo using fold=0, i.e. the earlier offset.
    return datetime.combine(day, t, tzinfo=tz).astimezone(timezone.utc)


def current_window_end(schedule: PowerSchedule, now_utc: datetime) -> Optional[datetime]:
    """End (UTC) of the window that contains now, or None if outside all windows."""
    today = now_utc.astimezone(schedule.tz).date()
    for window in schedule.windows:
        # Check windows starting yesterday too, for windows crossing midnight.
        for offset in (-1, 0):
            day = today + timedelta(days=offset)
            start = _local_to_utc(day, window.start, schedule.tz)
            end_day = day + timedelta(days=1) if window.end <= window.start else day
            end = _local_to_utc(end_day, window.end, schedule.tz)
            if start - schedule.start_tolerance <= now_utc < end:
                return end
    return None


def decide(
    schedule: PowerSchedule,
    now_utc: datetime,
    uptime: timedelta,
    clock_synced: bool,
) -> Decision:
    """Decide whether to shut down now."""
    if not clock_synced:
        # The wall clock cannot be trusted (no RTC). Fall back to uptime so we
        # still shut down cleanly before even the shortest window ends.
        if uptime >= schedule.unsynced_max_uptime:
            return Decision(True, f"clock not synchronised after {uptime}")
        return Decision(False, "waiting for clock synchronisation")

    end = current_window_end(schedule, now_utc)
    if end is not None:
        shutdown_at = end - schedule.shutdown_lead
        local = shutdown_at.astimezone(schedule.tz).strftime("%H:%M")
        if now_utc >= shutdown_at:
            return Decision(True, f"power window ends; shutdown time {local} reached")
        return Decision(False, f"in power window; shutdown at {local}")

    # Booted outside every window (unexpected power, or relay and config out
    # of step). Stay up long enough to upload, then shut down.
    if uptime >= schedule.outside_window_grace:
        return Decision(True, f"outside power windows for {uptime}")
    return Decision(False, "outside power windows; grace period running")
