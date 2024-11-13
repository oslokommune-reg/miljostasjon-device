#!/bin/bash

# Function to display usage/help message
show_help() {
    echo "Usage: $(basename $0) --path DEVICE_PATH --hostname HOSTNAME"
    echo
    echo "Format SD card and burn image with custom hostname"
    echo
    echo "Options:"
    echo "  --path        Specify the device path (e.g., mmcblk0)"
    echo "  --hostname    Specify the hostname for the device"
    echo "  --help        Display this help message"
    echo
    echo "Example:"
    echo "  $(basename $0) --path mmcblk0 --hostname pi-station-01"
    exit 1
}

# Function to check if user is root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "Error: This script must be run as root (use sudo)"
        exit 1
    fi
}

# Function to validate device path
validate_device() {
    local device=$1
    
    # Remove '/dev/' prefix if present
    device=${device#/dev/}
    
    # Check if device exists
    if [ ! -b "/dev/$device" ]; then
        echo "Error: Device /dev/$device does not exist"
        echo "Available devices:"
        lsblk
        exit 1
    fi
}

# Function to validate hostname
validate_hostname() {
    local hostname=$1
    
    # Check hostname format (letters, numbers, hyphens, no spaces)
    if ! [[ $hostname =~ ^[a-zA-Z0-9-]+$ ]]; then
        echo "Error: Invalid hostname format. Use only letters, numbers, and hyphens"
        exit 1
    fi
}

# Initialize variables
SD_CARD=""
HOSTNAME=""
HOSTNAMES_FILE="created_hostnames.txt"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --path)
            if [ -n "$2" ]; then
                SD_CARD=$2
                shift 2
            else
                echo "Error: --path requires a device path"
                show_help
            fi
            ;;
        --hostname)
            if [ -n "$2" ]; then
                HOSTNAME=$2
                shift 2
            else
                echo "Error: --hostname requires a value"
                show_help
            fi
            ;;
        --help)
            show_help
            ;;
        *)
            echo "Error: Unknown option $1"
            show_help
            ;;
    esac
done

# Check if required parameters are provided
if [ -z "$SD_CARD" ] || [ -z "$HOSTNAME" ]; then
    echo "Error: Both --path and --hostname are required"
    show_help
fi

# Main execution
check_root
validate_device "$SD_CARD"
validate_hostname "$HOSTNAME"

# Check if device is mounted
if mount | grep -q "/dev/$SD_CARD"; then
    echo "Device is currently mounted. Attempting to unmount..."
    sudo umount /dev/${SD_CARD}* 2>/dev/null || {
        echo "Error: Failed to unmount device"
        exit 1
    }
fi

# Check for existing hostname
if grep -q "^$HOSTNAME$" "$HOSTNAMES_FILE" 2>/dev/null; then
    echo "Error: Hostname $HOSTNAME already exists. Either change hostname or remove it from $HOSTNAMES_FILE"
    exit 1
fi

echo "Preparing to format /dev/$SD_CARD and set hostname to $HOSTNAME..."
echo "WARNING: This will erase ALL data on /dev/$SD_CARD"
read -p "Continue? (y/N): " confirm
if [[ "$confirm" != [yY] ]]; then
    exit 1
fi

# Create new partition table and partition
echo "Creating partition table..."
sudo fdisk /dev/${SD_CARD} << EOF
o
n
p
1


t
b
w
EOF

# Format the partition as FAT32
echo "Formatting partition as FAT32..."
sudo mkfs.vfat -F 32 /dev/${SD_CARD}1

# Verify the formatting
echo "Verifying format..."
sudo fsck.vfat /dev/${SD_CARD}1

# Burn image with SDM
echo "Burning image with hostname $HOSTNAME..."
if sudo sdm --burn /dev/$SD_CARD miljostasjon-pi.img --hostname "$HOSTNAME"; then
    # Create hostnames file directory if it doesn't exist
    mkdir -p "$(dirname "$HOSTNAMES_FILE")" 2>/dev/null
    
    # Add hostname to tracking file
    echo "$HOSTNAME" >> "$HOSTNAMES_FILE"
    echo "Success! Image burned with hostname $HOSTNAME"
else
    echo "Error: SDM burn failed"
    exit 1
fi

echo "Process complete!"