#!/bin/bash
# Fjern alt og bygg Docker-miljøet på nytt fra scratch.
# Brukes ved: exec format error, korrupte biblioteker, eller andre containerproblemer.
#
# Kjøres fra ~/miljostasjon-device/:
#   sudo bash rebuild.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Last inn env-variabler som docker compose trenger ---
for env_file in ~/dev.env ~/prod.env; do
    if [ -f "$env_file" ]; then
        set -a; source "$env_file"; set +a
    fi
done
export DEVICE_ID
DEVICE_ID=$(grep -m1 Serial /proc/cpuinfo | awk '{print $3}') || true

echo "==> Stopper containere..."
docker compose down --remove-orphans || true

echo "==> Fjerner images og byggecache..."
docker image rm miljostasjon-device-prod 2>/dev/null || true
docker builder prune -f
docker image prune -f

echo "==> Bygger på nytt (--no-cache --pull)..."
docker compose build --pull --no-cache

echo "==> Starter containere..."
docker compose up -d

echo ""
echo "==> Ferdig. Logger (Ctrl+C for å avslutte):"
docker compose logs --follow
