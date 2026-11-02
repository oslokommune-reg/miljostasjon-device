#!/usr/bin/env python3
# power_agent.py
# ------------------------------------------------------------
# Host service (miljostasjon-power.service) that shuts the Pi down cleanly
# before the relay cuts the power, based on config/power_schedule.json.
#
# Every CHECK_SECONDS it decides (see power_schedule.decide) whether to shut
# down. Shutdown stops the app container first, with time for its final
# upload, then powers off. Docker's own shutdown only waits 15 s.
#
# Maintenance: while the flag file exists (and is younger than
# MAINTENANCE_MAX_AGE), nothing is shut down. Toggle it with the
# "Vedlikeholdsmodus" desktop shortcut or `touch`/`rm` the file.
# ------------------------------------------------------------

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from power_schedule import decide  # noqa: E402
from schedule_source import FileSource, GitHubRawSource, load_schedule  # noqa: E402

CHECK_SECONDS = 15
REMOTE_RETRY_SECONDS = 300
MAINTENANCE_MAX_AGE = timedelta(hours=12)
CONTAINER_STOP_SECONDS = 45  # > SHUTDOWN_UPLOAD_SECONDS in main/main.py


def log(msg: str) -> None:
    print(msg, flush=True)  # stdout goes to the journal


def clock_synced() -> bool:
    try:
        out = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return out == "yes"
    except Exception:
        return False


def uptime() -> timedelta:
    with open("/proc/uptime") as f:
        return timedelta(seconds=float(f.read().split()[0]))


def maintenance_active(flag: str) -> bool:
    try:
        age = time.time() - os.path.getmtime(flag)
    except OSError:
        return False
    return age < MAINTENANCE_MAX_AGE.total_seconds()


def shut_down(container: str, dry_run: bool) -> None:
    if dry_run:
        log("DRY RUN: would stop the container and power off now.")
        return
    log(f"Stopping container {container} (up to {CONTAINER_STOP_SECONDS}s)...")
    subprocess.run(
        ["docker", "stop", "--time", str(CONTAINER_STOP_SECONDS), container],
        timeout=CONTAINER_STOP_SECONDS + 30,
    )
    log("Powering off.")
    subprocess.run(["systemctl", "poweroff"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="main")
    parser.add_argument("--bundled", required=True, help="power_schedule.json in the repo checkout")
    parser.add_argument("--cache", default="/var/lib/miljostasjon/power_schedule.json")
    parser.add_argument("--maintenance-flag", required=True)
    parser.add_argument("--container", default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    remote = GitHubRawSource(args.branch)
    fallbacks = [FileSource(args.bundled)]

    schedule, origin, from_remote = load_schedule(remote, args.cache, fallbacks)
    log(f"Schedule loaded from {origin}.")
    last_fetch = time.monotonic()

    last_reason = None
    shutdown_started = False
    while True:
        if not from_remote and time.monotonic() - last_fetch >= REMOTE_RETRY_SECONDS:
            last_fetch = time.monotonic()
            schedule, origin, from_remote = load_schedule(remote, args.cache, fallbacks)
            if from_remote:
                log(f"Schedule refreshed from {origin}.")

        if maintenance_active(args.maintenance_flag):
            reason = f"maintenance mode ({args.maintenance_flag}); not shutting down"
            shutdown = False
        else:
            d = decide(schedule, datetime.now(timezone.utc), uptime(), clock_synced())
            reason, shutdown = d.reason, d.shutdown

        if reason != last_reason:  # log changes only, to keep writes down
            log(reason)
            last_reason = reason

        if shutdown and not shutdown_started:
            shutdown_started = True  # dry run: log once, keep evaluating
            shut_down(args.container, args.dry_run)
        elif not shutdown:
            shutdown_started = False

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
