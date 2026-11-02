#!/bin/bash
# ============================================================
# Install power-safety on a station, after checking out the branch:
#   cd <repo>
#   sudo git fetch origin
#   sudo git checkout -B power-safety --track origin/power-safety
#   sudo bash tools/install_power_safety.sh
#
# Start early in a power window: the image build can take ~10 minutes.
# Maintenance mode is on during the install, so the station is not shut
# down by the new service halfway through.
#
# Applies the host config, builds the app image, installs this branch's
# startup.sh and desktop shortcuts right away (instead of on the next
# boot) and reboots. Undo with the "Tilbake til main" desktop shortcut.
# ============================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

PARENT="$(dirname "$REPO_DIR")"
if [ -f "$PARENT/startup.sh" ]; then SCRIPTS_DIR="$PARENT"; else SCRIPTS_DIR="$PARENT/scripts"; fi
APP_USER="$(stat -c %U "$SCRIPTS_DIR")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
FLAG="$APP_HOME/.miljostasjon-maintenance"

echo "Installing power-safety from $(git log -1 --format='%h %s')"
sudo -u "$APP_USER" touch "$FLAG"

bash config/host/apply_host_config.sh

# Load the same env as startup.sh, so the build and host-sync see it.
set -a
# shellcheck disable=SC1091
. "$SCRIPTS_DIR/config.sh" >/dev/null
for env_file in "$APP_HOME/dev.env" "$APP_HOME/prod.env"; do
    # shellcheck disable=SC1090
    [ -f "$env_file" ] && . "$env_file"
done
set +a

echo "Building app image..."
docker compose build
git rev-parse HEAD > .git/miljostasjon-built-commit  # see startup.sh

# Same copy that runs on every boot (docker-compose.yml, host-sync).
docker compose run --rm -T host-sync

rm -f "$FLAG"
echo ""
echo "Installed. Rebooting in 10 seconds."
sleep 10
systemctl reboot
