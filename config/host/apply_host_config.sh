#!/bin/bash
# ============================================================
# Power-safety host configuration. Run as root:
#   sudo bash <repo>/config/host/apply_host_config.sh
#
# Idempotent: startup.sh runs it on every boot, so changes here reach all
# stations through git. Undo everything with revert_host_config.sh.
#
# - stable data directory for the app buffer (+ migrate old JSON buffers)
# - controlled shutdown service (miljostasjon-power.service)
# - fewer SD card writes: no swap, capped journal, /tmp in RAM, no apt/man-db timers
# - startup service waits for network and Docker
# ============================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST_DIR="$REPO_DIR/config/host"
DATA_DIR=/var/lib/miljostasjon/data
STATE_DIR=/var/lib/miljostasjon

# The repo lives in ~/scripts/<repo> (newer images) or ~/<repo> (older).
PARENT="$(dirname "$REPO_DIR")"
if [ -f "$PARENT/startup.sh" ]; then SCRIPTS_DIR="$PARENT"; else SCRIPTS_DIR="$PARENT/scripts"; fi
APP_USER="$(stat -c %U "$SCRIPTS_DIR")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
BRANCH="$(git -C "$REPO_DIR" symbolic-ref --short -q HEAD || echo main)"

echo "Applying power-safety host config (repo $REPO_DIR, branch $BRANCH, user $APP_USER)"

# --- Data directory + migration of old JSON buffers ---------------------
mkdir -p "$DATA_DIR"
n=0
for old in "$REPO_DIR/~/dev_persistent_storage/temporary_device_data.json" \
           "/root/dev_persistent_storage/temporary_device_data.json" \
           "$APP_HOME/dev_persistent_storage/temporary_device_data.json"; do
    if [ -s "$old" ]; then
        n=$((n + 1))
        # The app imports *.json from the data dir into its SQLite buffer.
        mv "$old" "$DATA_DIR/legacy-$(date +%Y%m%d%H%M%S)-$n.json"
        echo "Moved old buffer $old to $DATA_DIR for import"
    fi
done

# --- Fewer SD card writes ------------------------------------------------
if systemctl is-enabled -q dphys-swapfile 2>/dev/null; then
    dphys-swapfile swapoff || true
    dphys-swapfile uninstall || true
    systemctl disable --now dphys-swapfile
    echo "Swap disabled"
fi

mkdir -p /etc/systemd/journald.conf.d
if ! cmp -s "$HOST_DIR/journald-miljostasjon.conf" /etc/systemd/journald.conf.d/50-miljostasjon.conf; then
    install -m 644 "$HOST_DIR/journald-miljostasjon.conf" /etc/systemd/journald.conf.d/50-miljostasjon.conf
    systemctl restart systemd-journald
    journalctl --vacuum-size=64M >/dev/null 2>&1 || true
    echo "Journal capped"
fi

if [ ! -f /etc/systemd/system/tmp.mount ] && [ -f /usr/share/systemd/tmp.mount ]; then
    cp /usr/share/systemd/tmp.mount /etc/systemd/system/tmp.mount
    systemctl enable tmp.mount  # takes effect at next boot
    echo "/tmp in RAM from next boot"
fi

for t in apt-daily.timer apt-daily-upgrade.timer man-db.timer; do
    if systemctl is-enabled -q "$t" 2>/dev/null; then
        systemctl disable --now "$t"
        echo "Disabled $t"
    fi
done

# --- Startup service: wait for network and Docker ------------------------
# The unit name differs between image generations; find it by ExecStart.
for unit in $(grep -l 'scripts/startup.sh' /etc/systemd/system/*.service 2>/dev/null); do
    dropin="$unit.d/50-miljostasjon.conf"
    mkdir -p "$unit.d"
    install -m 644 "$HOST_DIR/startup-dropin.conf" "$dropin"
done

# --- Controlled shutdown service -----------------------------------------
# Local overrides (e.g. POWER_AGENT_ARGS=--dry-run on a test Pi) go in
# /etc/default/miljostasjon-power and are never overwritten.
[ -f /etc/default/miljostasjon-power ] || echo 'POWER_AGENT_ARGS=' > /etc/default/miljostasjon-power

unit_tmp="$(mktemp)"
sed -e "s|@REPO_DIR@|$REPO_DIR|g" \
    -e "s|@BRANCH@|$BRANCH|g" \
    -e "s|@APP_HOME@|$APP_HOME|g" \
    "$HOST_DIR/miljostasjon-power.service" > "$unit_tmp"
if ! cmp -s "$unit_tmp" /etc/systemd/system/miljostasjon-power.service; then
    install -m 644 "$unit_tmp" /etc/systemd/system/miljostasjon-power.service
    systemctl daemon-reload
    systemctl enable miljostasjon-power.service
    systemctl restart miljostasjon-power.service
    echo "Controlled shutdown service installed"
else
    systemctl daemon-reload
fi
rm -f "$unit_tmp"

mkdir -p "$STATE_DIR"
git -C "$REPO_DIR" rev-parse --short HEAD > "$STATE_DIR/host-config-applied" 2>/dev/null || true
echo "Power-safety host config applied."
