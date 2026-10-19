#!/bin/bash
# Kjøres fra skrivebordssnarveien "Bygg Docker på nytt".
# Spør om bekreftelse og kjører rebuild.sh fra repoet som startup.sh har klonet.

REPO_DIR="$HOME/scripts/miljostasjon-device"

echo "Dette stopper containerne, sletter Docker-images og bygger alt på nytt."
echo "Det kan ta 10-30 minutter. Stasjonen sender ikke data mens dette pågår."
echo ""
read -r -p "Vil du fortsette? [j/N] " svar
if [[ ! "$svar" =~ ^[jJyY]$ ]]; then
    echo "Avbrutt."
    sleep 2
    exit 0
fi

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
