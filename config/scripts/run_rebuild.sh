#!/bin/bash
# Kjøres fra skrivebordssnarveien "Bygg Docker på nytt".
# Kjører rebuild.sh fra repoet som startup.sh har klonet.

# Nyere images kloner til ~/scripts/<repo>, eldre til ~/<repo>.
REPO_DIR="$HOME/scripts/miljostasjon-device"
[ -f "$REPO_DIR/rebuild.sh" ] || REPO_DIR="$HOME/miljostasjon-device"

if [ ! -f "$REPO_DIR/rebuild.sh" ]; then
    echo "FEIL: Fant ikke rebuild.sh i ~/scripts/miljostasjon-device eller ~/miljostasjon-device"
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
