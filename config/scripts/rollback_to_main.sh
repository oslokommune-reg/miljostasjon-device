#!/bin/bash
# Desktop shortcut "Tilbake til main".
# Undoes the power-safety host config, switches the repo back to main and
# reboots. Unsent readings are handed over to the old app version.

# Nyere images kloner til ~/scripts/<repo>, eldre til ~/<repo>.
REPO_DIR="$HOME/scripts/miljostasjon-device"
[ -d "$REPO_DIR/.git" ] || REPO_DIR="$HOME/miljostasjon-device"

echo "Setter stasjonen tilbake til main ($REPO_DIR)."
echo ""

if [ -f "$REPO_DIR/config/host/revert_host_config.sh" ]; then
    sudo bash "$REPO_DIR/config/host/revert_host_config.sh"
fi

sudo git -C "$REPO_DIR" fetch origin main || echo "ADVARSEL: fikk ikke hentet main; bruker lokal kopi."
sudo git -C "$REPO_DIR" checkout -f main
sudo git -C "$REPO_DIR" reset --hard origin/main 2>/dev/null || true

rm -f "$HOME/Desktop/rollback_to_main.desktop" "$HOME/Desktop/maintenance.desktop" \
      "$HOME/.miljostasjon-maintenance"

echo ""
echo "Ferdig. Repoet står nå på: $(git -C "$REPO_DIR" log -1 --format='%h %s')"
echo "Starter på nytt om 15 sekunder (Ctrl+C for å avbryte)..."
sleep 15
sudo reboot
