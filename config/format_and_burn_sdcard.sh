mount | grep mmcblk0
sudo mkfs.vfat -F32 /dev/mmcblk0 -I


# Check that the hostname is not in the created_hostnames.txt file
if grep -q "^$1$" created_hostnames.txt 2>/dev/null; then
    echo "Error: Hostname $1 already exists. Either change hostname or remove it from the created_hostnames.txt file"
    exit 1

else
    if sudo sdm --burn /dev/mmcblk0 miljostasjon-pi.img --hostname "$1"; then
        VAR="$1"
        OUT="created_hostnames.txt"
        if [ ! -f "$OUT" ]; then
            mkdir -p "`dirname \"$OUT\"`" 2>/dev/null
        fi
        echo $VAR >> $OUT
    else
        echo "Error: SDM burn failed"
        exit 1
    fi
fi