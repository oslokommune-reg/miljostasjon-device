#!/bin/bash
# ============================================================
# Health check after a (simulated) power cut. Run on the Pi as root:
#   sudo bash tools/verify_power_safety.sh [MIN_SEQ]
#
# MIN_SEQ: the highest seq that was committed before the cut. The check
# fails if the buffer's highest seq is lower, i.e. committed data was lost.
# Prints one line per check and exits non-zero if any check fails.
# ============================================================

MIN_SEQ="${1:-0}"
DB=/var/lib/miljostasjon/data/buffer.db
FAIL=0

check() {  # check <name> <ok:0/1> <detail>
    if [ "$2" = 0 ]; then echo "OK    $1: $3"; else echo "FAIL  $1: $3"; FAIL=1; fi
}

# Filesystem: any ext4 or MMC errors logged by the kernel since boot?
errs=$(journalctl -k -b --no-pager | grep -ciE "EXT4-fs (error|warning)|mmc.*(error|timeout)|I/O error")
check "kernel fs/mmc errors" "$([ "$errs" = 0 ]; echo $?)" "$errs this boot"
recov=$(journalctl -k -b --no-pager | grep -ciE "EXT4-fs.*recovery complete")
echo "INFO  ext4 journal recoveries this boot: $recov"

# Buffer database
if [ -f "$DB" ]; then
    read -r integrity count min max < <(python3 - "$DB" <<'EOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
i = c.execute("PRAGMA integrity_check").fetchone()[0]
n, lo, hi = c.execute("SELECT COUNT(*), COALESCE(MIN(seq),0), COALESCE(MAX(seq),0) FROM readings").fetchone()
print(i, n, lo, hi)
EOF
)
    check "sqlite integrity" "$([ "$integrity" = ok ]; echo $?)" "$integrity"
    contiguous=$([ "$count" = 0 ] || [ $((max - min + 1)) = "$count" ]; echo $?)
    check "no gaps in seq" "$contiguous" "count=$count min=$min max=$max"
    check "no committed data lost" "$([ "$max" -ge "$MIN_SEQ" ]; echo $?)" "max=$max >= before-cut=$MIN_SEQ"
else
    check "sqlite buffer exists" 1 "$DB missing"
fi

# Git repo and Docker
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
git -C "$REPO" fsck --connectivity-only >/dev/null 2>&1
check "git repo" "$?" "$(git -C "$REPO" log -1 --format=%h 2>/dev/null)"
locks=$(find "$REPO/.git" -maxdepth 4 -name '*.lock' | wc -l)
check "no git lock files" "$([ "$locks" = 0 ]; echo $?)" "$locks"
systemctl is-active --quiet docker
check "docker running" "$?" "$(systemctl is-active docker)"
state=$(docker inspect -f '{{.State.Status}}' prod 2>/dev/null)
check "prod container" "$([ "$state" = running ]; echo $?)" "${state:-missing}"
systemctl is-active --quiet miljostasjon-power
check "power agent" "$?" "$(systemctl is-active miljostasjon-power)"

exit $FAIL
