# config.sh

# Repository configuration
REPO_NAME="miljostasjon-device"
REPO_URL="https://github.com/oslokommune-reg/${REPO_NAME}.git"


export DEVICE_ID=$(cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2)

echo "Running from device ${DEVICE_ID}"