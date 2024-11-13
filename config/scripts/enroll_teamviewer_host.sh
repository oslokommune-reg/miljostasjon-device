#!/bin/bash

# Your TeamViewer script token
source ./teamviewer.env

#!/bin/bash

# Configuration
TEAMVIEWER_CONFIG="/opt/teamviewer/config/global.conf"
TEAMVIEWER_SERVICE="teamviewerd.service"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Function to wait for TeamViewer daemon to be fully running
wait_for_teamviewer() {
    echo "Waiting for TeamViewer service to start..."
    while ! systemctl is-active --quiet $TEAMVIEWER_SERVICE; do
        sleep 2
    done
    # Additional wait to ensure the daemon is fully initialized
    sleep 5
}

# Stop TeamViewer service if running
systemctl stop $TEAMVIEWER_SERVICE

# Accept EULA
mkdir -p /opt/teamviewer/config/
touch /opt/teamviewer/config/global.conf
echo "TeamViewer.General.EulaAccepted = 1" >> "$TEAMVIEWER_CONFIG"
echo "TeamViewer.General.EulaAcceptedRevision = 29" >> "$TEAMVIEWER_CONFIG"

# Set assignment ID in config
if [ ! -f "$TEAMVIEWER_CONFIG" ]; then
    mkdir -p "$(dirname "$TEAMVIEWER_CONFIG")"
    touch "$TEAMVIEWER_CONFIG"
fi

# Update or add assignment ID
if grep -q "Assignment.AssignmentID" "$TEAMVIEWER_CONFIG"; then
    sed -i "s/Assignment.AssignmentID.*/Assignment.AssignmentID = $TEAMVIEWER_ASSIGNMENT_ID/" "$TEAMVIEWER_CONFIG"
else
    echo "Assignment.AssignmentID = $TEAMVIEWER_ASSIGNMENT_ID" >> "$TEAMVIEWER_CONFIG"
fi

# Set additional convenient settings
cat >> "$TEAMVIEWER_CONFIG" << EOF
Security.AccessControl = 1
Security.UseCustomConfig = 1
Automation.AccessControlMode = 1
EOF

# Start TeamViewer service
systemctl start $TEAMVIEWER_SERVICE

# Wait for service to be fully running
wait_for_teamviewer

echo "TeamViewer has been configured with assignment ID: $TEAMVIEWER_ASSIGNMENT_ID"
echo "The device will automatically appear in your TeamViewer account's device list"

# Display TeamViewer ID for reference
teamviewer info | grep "TeamViewer ID"