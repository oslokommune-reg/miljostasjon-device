#!/usr/bin/env bash
# Wrapper for build_sdm.sh: håndterer WSL og legger timestamp på ferdig image.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
TIMESTAMPED_IMG="miljostasjon-pi-${TIMESTAMP}.img"

# --- Sjekk avhengigheter ---
missing=()
for cmd in sdm rsync sudo; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if (( ${#missing[@]} > 0 )); then
    echo "ERROR: mangler nødvendige verktøy: ${missing[*]}" >&2
    echo "       Installer rsync/sudo via apt, og sdm fra https://github.com/gitbls/sdm" >&2
    exit 1
fi

# --- Sjekk WSL-versjon ---
IS_WSL=false
if grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null; then
    IS_WSL=true
    # WSL1 har ikke loop-device-støtte som sdm trenger
    if ! [[ -e /dev/loop-control ]]; then
        echo "ERROR: dette ser ut som WSL1. sdm trenger WSL2 (loop-devices)." >&2
        echo "       Konverter med: wsl --set-version <distro> 2" >&2
        exit 1
    fi
fi

# --- Speil til WSL-filsystem hvis nødvendig ---
if [[ "$IS_WSL" == true && "$PROJECT_DIR" == /mnt/* ]]; then
    WORK_DIR="$HOME/.sdm-build/$(basename "$PROJECT_DIR")"
    echo "==> WSL oppdaget. Speiler prosjekt til $WORK_DIR (ytelse + loop-device-kompatibilitet)."
    mkdir -p "$WORK_DIR"
    rsync -a --delete \
        --exclude='/miljostasjon-pi*.img' \
        --exclude='.git' \
        "$PROJECT_DIR/" "$WORK_DIR/"
    cd "$WORK_DIR"
else
    cd "$PROJECT_DIR"
fi

# --- Kjør selve buildet ---
echo "==> Kjører build_sdm.sh i $(pwd)"
bash build_sdm.sh

if [[ ! -f miljostasjon-pi.img ]]; then
    echo "ERROR: forventet utfil miljostasjon-pi.img mangler" >&2
    exit 1
fi

# sdm kjører via sudo, så fila kan eies av root
sudo mv miljostasjon-pi.img "$TIMESTAMPED_IMG"
sudo chown "$(id -u):$(id -g)" "$TIMESTAMPED_IMG"

# --- Kopier tilbake til Windows-mappen om nødvendig ---
if [[ "$IS_WSL" == true && "$PROJECT_DIR" == /mnt/* ]]; then
    echo "==> Kopierer ferdig image tilbake til prosjektmappen"
    cp "$TIMESTAMPED_IMG" "$PROJECT_DIR/$TIMESTAMPED_IMG"
    FINAL_PATH="$PROJECT_DIR/$TIMESTAMPED_IMG"
else
    FINAL_PATH="$(pwd)/$TIMESTAMPED_IMG"
fi

echo
echo "==> Ferdig. Image:"
echo "    $FINAL_PATH"