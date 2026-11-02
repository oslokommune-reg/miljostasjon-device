#!/bin/bash
# ============================================================
# Repeated hard power-cut simulation against a TEST Pi, run from a PC:
#   bash tools/powercut_test.sh <ssh-host> [cycles]
#
# Each cycle waits until the app is writing, records the highest committed
# seq, then crashes the Pi with sysrq 'b' (immediate reboot without sync or
# unmount: same on-disk effect as pulling the plug, except that the SD
# card's own controller keeps power). After the reboot it runs
# verify_power_safety.sh, which fails if any committed reading was lost or
# anything is corrupt.
#
# The test Pi must run with FAKE_DEVICES=1 (synthetic data, uploads
# disabled, one write per second) and POWER_AGENT_ARGS=--dry-run.
# Finish with a few real plug pulls; see docs/POWER_SAFETY.md.
# ============================================================

HOST="${1:?usage: powercut_test.sh <ssh-host> [cycles]}"
CYCLES="${2:-10}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=5 $HOST"
REPO_ON_PI='$(test -d ~/scripts/miljostasjon-device && echo ~/scripts/miljostasjon-device || echo ~/miljostasjon-device)'

max_seq() {
    $SSH "sudo python3 -c \"import sqlite3; print(sqlite3.connect('/var/lib/miljostasjon/data/buffer.db').execute('SELECT COALESCE(MAX(seq),0) FROM readings').fetchone()[0])\"" 2>/dev/null
}

wait_for_writes() {  # until the Pi answers and the buffer grows
    local a b
    for _ in $(seq 1 90); do
        a=$(max_seq); sleep 5; b=$(max_seq)
        if [ -n "$a" ] && [ -n "$b" ] && [ "$b" -gt "$a" ]; then return 0; fi
    done
    return 1
}

failed=0
for i in $(seq 1 "$CYCLES"); do
    echo "=== Cycle $i/$CYCLES"
    if ! wait_for_writes; then echo "Pi did not come back writing data"; failed=$((failed + 1)); break; fi

    sleep $((RANDOM % 20))  # cut at a random moment
    before=$(max_seq)
    echo "Highest committed seq before cut: $before. Cutting power..."
    $SSH 'echo 1 | sudo tee /proc/sys/kernel/sysrq >/dev/null; echo b | sudo tee /proc/sysrq-trigger' >/dev/null 2>&1

    sleep 30
    if ! wait_for_writes; then echo "Pi did not come back writing data"; failed=$((failed + 1)); break; fi
    if ! $SSH "cd $REPO_ON_PI && sudo bash tools/verify_power_safety.sh $before"; then
        failed=$((failed + 1))
    fi
done

echo ""
echo "Cycles with failures: $failed"
[ "$failed" = 0 ]
