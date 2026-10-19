#!/bin/sh
# Kjøres i host-sync-containeren (se docker-compose.yml) hver gang
# startup.sh kjører `docker compose up`, altså ved hver oppstart.
#
# Kopierer config/scripts fra repoet til ~/scripts på verten og legger
# .desktop-snarveiene på skrivebordet. Slik når endringer i startup.sh,
# snarveier o.l. alle stasjoner via git, uten å flashe på nytt.
#
# Monteringer:
#   /repo_scripts  <- config/scripts i repoet (read-only)
#   /host_home     <- brukerens hjemmappe (repoet ligger i ~/scripts/miljostasjon-device)

set -eu

SRC=/repo_scripts
HOME_DIR=/host_home
SCRIPTS_DIR="$HOME_DIR/scripts"
DESKTOP_DIR="$HOME_DIR/Desktop"

# Sikkerhetssjekk: avbryt hvis monteringen ikke peker på forventet hjemmappe
if [ ! -f "$SCRIPTS_DIR/miljostasjon-device/docker-compose.yml" ]; then
    echo "Fant ikke $SCRIPTS_DIR/miljostasjon-device; hopper over synkronisering."
    exit 0
fi

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
