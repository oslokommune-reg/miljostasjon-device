#!/bin/bash
# Kjøres fra skrivebordssnarveien "Bygg Docker på nytt".
# Kjører rebuild.sh fra repoet som startup.sh har klonet.

REPO_DIR="$HOME/scripts/miljostasjon-device"

if [ ! -f "$REPO_DIR/rebuild.sh" ]; then
    echo "FEIL: Fant ikke $REPO_DIR/rebuild.sh"
    read -r -p "Trykk Enter for å lukke..."
    exit 1
fi

# rebuild.sh avslutter med å følge loggene. Fang Ctrl+C her, så vinduet
# ikke lukkes før brukeren har sett resultatet.
trap 'echo ""' INT
sudo bash "$REPO_DIR/rebuild.sh"
trap - INT

echo ""
read -r -p "Trykk Enter for å lukke..."
