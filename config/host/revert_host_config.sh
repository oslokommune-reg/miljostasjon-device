#!/bin/bash
# ============================================================
# Undo apply_host_config.sh. Run as root, before switching the repo back
# to a branch without power-safety (rollback_to_main.sh does this):
#   sudo bash <repo>/config/host/revert_host_config.sh
#
# Readings still in the SQLite buffer are exported to the JSON buffer that
# the old app version reads, so they are uploaded after the rollback.
# ============================================================

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR=/var/lib/miljostasjon/data

echo "Reverting power-safety host config"

# Stop the controlled shutdown first, so it cannot power off mid-rollback.
systemctl disable --now miljostasjon-power.service 2>/dev/null
rm -f /etc/systemd/system/miljostasjon-power.service /etc/default/miljostasjon-power

# Export pending readings for the old app (it reads <repo>/~/dev_persistent_storage
# when started by startup.sh under systemd, where HOME is unset).
docker stop --time 45 prod >/dev/null 2>&1
OLD_BUFFER="$REPO_DIR/~/dev_persistent_storage/temporary_device_data.json"
if [ -f "$DATA_DIR/buffer.db" ]; then
    mkdir -p "$(dirname "$OLD_BUFFER")"
    python3 - "$DATA_DIR/buffer.db" "$OLD_BUFFER" <<'EOF'
import json, os, sqlite3, sys
db, out = sys.argv[1], sys.argv[2]
rows = [json.loads(p) for (p,) in sqlite3.connect(db).execute("SELECT payload FROM readings ORDER BY seq")]
existing = []
if os.path.exists(out):
    try:
        existing = json.load(open(out))
    except ValueError:
        pass
json.dump(existing + rows, open(out, "w"), indent=4)
print(f"Exported {len(rows)} pending readings to {out}")
EOF
    mv "$DATA_DIR/buffer.db" "$DATA_DIR/buffer.db.reverted-$(date +%Y%m%d%H%M%S)"
    rm -f "$DATA_DIR/buffer.db-wal" "$DATA_DIR/buffer.db-shm"
fi

for unit_d in /etc/systemd/system/*.service.d; do
    rm -f "$unit_d/50-miljostasjon.conf"
    rmdir "$unit_d" 2>/dev/null
done

for t in apt-daily.timer apt-daily-upgrade.timer man-db.timer; do
    systemctl enable --now "$t" 2>/dev/null
done

if [ -f /etc/systemd/system/tmp.mount ]; then
    systemctl disable tmp.mount
    rm -f /etc/systemd/system/tmp.mount
fi

if [ -f /etc/systemd/journald.conf.d/50-miljostasjon.conf ]; then
    rm -f /etc/systemd/journald.conf.d/50-miljostasjon.conf
    systemctl restart systemd-journald
fi

if command -v dphys-swapfile >/dev/null && ! systemctl is-enabled -q dphys-swapfile; then
    systemctl enable dphys-swapfile
    dphys-swapfile setup && dphys-swapfile swapon
fi

systemctl daemon-reload
rm -f /var/lib/miljostasjon/host-config-applied
echo "Power-safety host config reverted."
