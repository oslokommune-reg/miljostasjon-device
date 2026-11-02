#!/bin/sh
# Kjøres i host-sync-containeren (se docker-compose.yml) hver gang
# startup.sh kjører `docker compose up`, altså ved hver oppstart.
#
# Kopierer config/scripts fra repoet til ~/scripts på verten og legger
# .desktop-snarveiene på skrivebordet. Slik når endringer i startup.sh,
# snarveier o.l. alle stasjoner via git, uten å flashe på nytt.
#
# Monteringer:
#   /repo_scripts      <- config/scripts i repoet (read-only)
#   /repo_parent       <- mappa repoet ligger i (..)
#   /repo_grandparent  <- mappa over den igjen (../..)
#
# Repoet ligger to ulike steder avhengig av imagets alder:
#   nyere: ~/scripts/miljostasjon-device  -> parent = ~/scripts, grandparent = ~
#   eldre: ~/miljostasjon-device          -> parent = ~,         scripts = ~/scripts

set -eu

SRC=/repo_scripts
PARENT=/repo_parent
GRANDPARENT=/repo_grandparent

if [ ! -f "$PARENT/miljostasjon-device/docker-compose.yml" ]; then
    echo "Fant ikke repoet i forventet mappe; hopper over synkronisering."
    exit 0
fi

if [ -f "$PARENT/startup.sh" ]; then
    HOME_DIR=$GRANDPARENT
    SCRIPTS_DIR=$PARENT
elif [ -f "$PARENT/scripts/startup.sh" ]; then
    HOME_DIR=$PARENT
    SCRIPTS_DIR="$PARENT/scripts"
else
    echo "Fant ikke startup.sh ved siden av eller under repoet; hopper over synkronisering."
    exit 0
fi
DESKTOP_DIR="$HOME_DIR/Desktop"

OWNER=$(stat -c %u:%g "$HOME_DIR")

# Kopier til temp-fil og flytt på plass (atomisk). startup.sh kjører mens
# dette skjer, og bash leser scriptet fortløpende fra fila; en vanlig cp
# over fila kunne fått det kjørende scriptet til å lese halvskrevet innhold.
install_file() {
    src=$1
    dst_dir=$2
    mode=$3
    name=$(basename "$src")
    tmp="$dst_dir/.$name.tmp"
    cp "$src" "$tmp"
    chown "$OWNER" "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$dst_dir/$name"
}

for f in "$SRC"/*; do
    [ -f "$f" ] || continue
    case "$f" in
        *.sh) install_file "$f" "$SCRIPTS_DIR" 755 ;;
        *)    install_file "$f" "$SCRIPTS_DIR" 644 ;;
    esac
done
echo "Synkroniserte config/scripts til $SCRIPTS_DIR"

mkdir -p "$DESKTOP_DIR"
chown "$OWNER" "$DESKTOP_DIR"
for f in "$SRC"/*.desktop; do
    [ -f "$f" ] || continue
    install_file "$f" "$DESKTOP_DIR" 755
done
echo "Oppdaterte snarveier i $DESKTOP_DIR"
