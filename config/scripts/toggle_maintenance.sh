#!/bin/bash
# Desktop shortcut "Vedlikeholdsmodus".
# While the flag exists, miljostasjon-power.service does not shut the Pi
# down. The flag expires by itself after 12 hours, so a forgotten flag
# does not disable controlled shutdown for good.

FLAG="$HOME/.miljostasjon-maintenance"

if [ -f "$FLAG" ]; then
    rm -f "$FLAG"
    echo "Vedlikeholdsmodus er AV. Pi-en slår seg av etter tidsplanen igjen."
else
    touch "$FLAG"
    echo "Vedlikeholdsmodus er PÅ i 12 timer. Pi-en slår seg ikke av automatisk."
    echo "NB: Releet kutter fortsatt strømmen når vinduet er over."
fi
echo ""
read -r -p "Trykk Enter for å lukke..."
