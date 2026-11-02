# schedule_source.py
# ------------------------------------------------------------
# Where the power schedule comes from. Kept separate from the decision
# logic so the source can later be replaced (e.g. by AWS) without touching
# power_agent.py: implement fetch() on a new class and pass it in.
#
# Order of preference in load_schedule():
#   1. the remote source (today: config/power_schedule.json on GitHub)
#   2. the last known valid schedule, cached on disk
#   3. the copy in the local repo checkout (first boot without network)
# ------------------------------------------------------------

import json
import os
import tempfile
import urllib.request
from typing import Iterable, Tuple

from power_schedule import PowerSchedule, ScheduleError, parse_schedule

GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/oslokommune-reg/miljostasjon-device/"
    "{branch}/config/power_schedule.json"
)


class GitHubRawSource:
    def __init__(self, branch: str, timeout: float = 10):
        self.url = GITHUB_RAW_URL.format(branch=branch)
        self.timeout = timeout

    def __str__(self):
        return self.url

    def fetch(self) -> dict:
        with urllib.request.urlopen(self.url, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


class FileSource:
    def __init__(self, path: str):
        self.path = path

    def __str__(self):
        return self.path

    def fetch(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)


def _write_atomic(path: str, data: dict) -> None:
    """Write via temp file + fsync + rename, so the cache is never half-written."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".schedule-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def load_schedule(remote, cache_path: str, fallbacks: Iterable = ()) -> Tuple[PowerSchedule, str, bool]:
    """Return (schedule, origin, from_remote). Raises ScheduleError if no
    source, cache or fallback gives a valid schedule."""
    errors = []
    try:
        data = remote.fetch()
        schedule = parse_schedule(data)
        _write_atomic(cache_path, data)
        return schedule, str(remote), True
    except Exception as e:
        errors.append(f"{remote}: {e}")

    for source in [FileSource(cache_path), *fallbacks]:
        try:
            return parse_schedule(source.fetch()), str(source), False
        except Exception as e:
            errors.append(f"{source}: {e}")

    raise ScheduleError("no valid schedule: " + "; ".join(errors))
