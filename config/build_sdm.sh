# Read environment variable for password
echo "Setting environment variables from device.env"
set -a # Automatically export all variables
source "device.env"
set +a

SRC_IMAGE_NAME="2024-11-19-raspios-bookworm-arm64.img"

rm miljostasjon-pi.img
echo "Removed old image from working directory"

cp ./images/$SRC_IMAGE_NAME miljostasjon-pi.img
echo "Copied $SRC_IMAGE_NAME from ./images to working directory"


sudo sdm --customize miljostasjon-pi.img \
    --extend --xmb 2048 \
    --plugin user:"adduser=miljostasjon|password=$DEVICE_PWD" \
    --plugin user:"deluser=pi" \
    --plugin disables:"piwiz|wifi|bluetooth" \
    --plugin bootconfig:"section=[all]|arm_freq=900|arm_freq_max=900" \
    --plugin raspiconfig:"boot_behavior=B4" \
    --plugin L10n:"keymap=no|locale=en_US.UTF-8 UTF-8|timezone=Europe/Oslo" \
    --plugin graphics:"graphics=X11" \
    --plugin apps:"apps=python3,python3-pip,git|name=core" \
    --plugin copydir:"from=scripts|to=/home/miljostasjon" \
    --plugin copyfile:"from=dev.env|to=/home/miljostasjon|chmod=7" \
    --plugin copyfile:"from=prod.env|to=/home/miljostasjon|chmod=7" \
    --plugin copyfile:"from=teamviewer.env|to=/home/miljostasjon|chmod=7" \
    --plugin runatboot:"script=scripts/install_docker.sh" \
    --plugin runatboot:"script=scripts/install_teamviewer.sh|sudoswitches=-H|output=/var/log/install_teamviewer.log" \
    --plugin runatboot:"script=scripts/bootstrap.sh|user=miljostasjon|sudoswitches=-H|output=/var/log/bootstrap.log" \
    --expand-root \
    --regen-ssh-host-keys \
    --restart