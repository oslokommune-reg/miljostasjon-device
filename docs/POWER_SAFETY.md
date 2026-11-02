# Power safety

Stations get power from a relay on a fixed schedule (today about
07:00–07:30 and 13:00–13:10, Europe/Oslo), and the battery protection also
cuts power without warning a few times a week. This branch makes the Pi
survive hard power cuts without corrupt data, writes less to the SD card,
and shuts down cleanly before scheduled cuts.

## What it does

| Area | Change |
|---|---|
| Data buffer | SQLite (WAL, `synchronous=FULL`) in `/var/lib/miljostasjon/data/buffer.db`. Each reading is one committed transaction; rows are deleted only after the API answers 200. Old JSON buffers are imported once. |
| Upload | Batches of 100, request timeouts, background thread. Final upload (max 25 s) on SIGTERM. |
| Clock | No RTC: readings are not stored until NTP has synced (max 3 min wait). |
| Controlled shutdown | `miljostasjon-power.service` stops the app container and powers off `shutdown_lead_minutes` before the window ends. |
| SD card writes | Swap off, journal capped at 64 MB and synced every 10 min, `/tmp` in RAM, apt/man-db timers off, app logs at INFO with a capped log driver, no rebuild or `--force-recreate` on every boot. |
| Self-repair | `startup.sh` resets Docker's network database when it is corrupt, and removes stale git lock files. |

### Shutdown rules (`power/power_schedule.py`)

- **Clock synced, inside a window:** shut down at window end minus `shutdown_lead_minutes`.
  A window counts from `start_tolerance_minutes` before its start, in case the relay clock runs ahead.
- **Clock synced, outside every window** (unexpected power, or config and relay out of step):
  stay up `outside_window_grace_minutes` to upload, then shut down.
- **Clock not synced:** the wall clock cannot be trusted, so shut down after
  `unsynced_max_uptime_minutes` of uptime. Keep this below the shortest window.
- **Maintenance mode:** while `~/.miljostasjon-maintenance` exists (desktop shortcut
  "Vedlikeholdsmodus"), nothing is shut down. The flag expires after 12 hours.

Times are wall-clock times in `timezone`; daylight saving time is handled
with `zoneinfo` and all comparisons are done in UTC.

## Configuration

`config/power_schedule.json` mirrors the relay schedule. The agent fetches it
from GitHub for the checked-out branch, caches the last valid version in
`/var/lib/miljostasjon/power_schedule.json`, and falls back to the cache (or
the copy in the repo) when the fetch fails or the file is invalid.

Fetching lives in `power/schedule_source.py`. To move the schedule to AWS
later, add a class with a `fetch()` method returning the same JSON and pass
it to `load_schedule()` in `power/power_agent.py`.

## Install on one station

Via TeamViewer, early in a power window (the image build takes up to ~10 minutes).
The repo is in `~/scripts/miljostasjon-device` or, on older images, `~/miljostasjon-device`.

```bash
cd ~/miljostasjon-device        # or ~/scripts/miljostasjon-device
sudo rm -f .git/*.lock          # only if a stale lock blocks git
sudo git fetch origin
sudo git checkout -B power-safety --track origin/power-safety
sudo bash tools/install_power_safety.sh
```

The script applies the host config, builds the app, installs the desktop
shortcuts and reboots. The station then follows the `power-safety` branch on
every boot.

## Roll back to main

Double-click **Tilbake til main** on the desktop. It stops the shutdown
service, exports unsent readings to the old JSON buffer, undoes the host
config, checks out `main` and reboots. The first boot rebuilds the app.

Without the shortcut:

```bash
cd ~/miljostasjon-device        # or ~/scripts/miljostasjon-device
sudo bash config/host/revert_host_config.sh
sudo git checkout -f main && sudo git pull --ff-only origin main
sudo reboot
```

## Check a station

```bash
journalctl -u miljostasjon-power -b      # shutdown decisions
journalctl -u miljostasjon-power -b -1   # previous boot: did it shut down cleanly?
sudo bash tools/verify_power_safety.sh    # buffer, filesystem, git, Docker
docker logs --tail 50 prod
```

## Test on a test Pi

Never on a production station: the test uses synthetic data and crashes the Pi.

1. Install as above, then set test-only overrides:
   ```bash
   echo "POWER_AGENT_ARGS=--dry-run" | sudo tee /etc/default/miljostasjon-power
   # synthetic data, one write per second, uploads off.
   # sed adds a missing final newline first; otherwise the line is glued
   # onto the last variable (the API URL) and breaks it.
   sudo sed -i -e '$a\' ~/prod.env
   echo "FAKE_DEVICES=1" | sudo tee -a ~/prod.env >/dev/null
   sudo reboot
   ```
2. Unit tests (on the Pi or any machine with Python 3.11):
   `python3 -m unittest discover -s tests -v`
3. Simulated power cuts from a PC with SSH access:
   `bash tools/powercut_test.sh <ssh-host> 20`.
   Each cycle crashes the Pi with sysrq `b` (no sync, no unmount) at a random
   moment while it writes, then `verify_power_safety.sh` checks that every
   reading committed before the cut is still there, the database passes
   `integrity_check`, there are no gaps in `seq`, no ext4/MMC errors, no git
   locks, and that Docker, the app and the shutdown service run.
4. Finish with a few real plug pulls (sysrq does not cut power to the SD
   card's own controller), then run `verify_power_safety.sh` after each.
5. Remove the test overrides (`FAKE_DEVICES` line in `~/prod.env`,
   `/etc/default/miljostasjon-power`) and reboot.
