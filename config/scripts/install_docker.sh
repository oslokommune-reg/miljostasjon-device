# Install Docker with error handling
echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    if [ $? -eq 0 ]; then
        sudo sh get-docker.sh
        rm get-docker.sh
    else
        echo "Failed to download Docker installation script"
        exit 1
    fi
fi

# Install Docker Compose
echo "Installing Docker Compose..."
sudo apt install docker-compose-plugin -y