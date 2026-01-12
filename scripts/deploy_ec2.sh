#!/bin/bash

# PhiBlock EC2 Deployment Script (For Demo Purposes)
# This script installs Docker, Docker Compose, and starts the app.

set -e  # Exit on error

echo "🚀 Starting PhiBlock Deployment..."

# 1. Update system and install dependencies
echo "📦 Checking dependencies..."
# We don't force a full yum update for demo to avoid package conflicts on AL2023
# We check if docker/unzip exist, if not, we try to install them
if ! command -v docker &> /dev/null || ! command -v unzip &> /dev/null; then
    echo "🛠️ Installing missing packages..."
    sudo yum install -y docker unzip || true
fi

# Ensure curl is available (usually curl-minimal is present on AL2023)
if ! command -v curl &> /dev/null; then
    sudo yum install -y curl-minimal || true
fi



# 2. Start Docker service
echo "🐳 Starting Docker..."
if command -v systemctl &> /dev/null; then
    sudo systemctl start docker
    sudo systemctl enable docker
else
    sudo service docker start
fi
sudo usermod -a -G docker ec2-user

# 3. Install Docker Compose (if not already present)
if ! command -v docker-compose &> /dev/null; then
    echo "🏗️ Installing Docker Compose..."
    # Determine Architecture
    ARCH=$(uname -m)
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$ARCH" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 3b. Install Docker Buildx plugin (required for modern docker-compose)
echo "🔧 Ensuring Docker Buildx is available..."
if ! docker buildx version &> /dev/null; then
    # Map architecture to Docker's naming convention
    ARCH=$(uname -m)
    case $ARCH in
        x86_64) BUILDX_ARCH="amd64" ;;
        aarch64) BUILDX_ARCH="arm64" ;;
        *) BUILDX_ARCH="amd64" ;;
    esac
    
    echo "📥 Downloading Docker Buildx for $BUILDX_ARCH..."
    sudo mkdir -p /usr/libexec/docker/cli-plugins
    sudo curl -sSL "https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-${BUILDX_ARCH}" \
        -o /usr/libexec/docker/cli-plugins/docker-buildx
    sudo chmod +x /usr/libexec/docker/cli-plugins/docker-buildx
    echo "✅ Docker Buildx installed"
fi



# 4. Prepare Application
echo "📂 Unpacking PhiBlock..."
ZIP_PATH="$HOME/phiblock.zip"

if [ ! -f "$ZIP_PATH" ]; then
    echo "❌ Error: $ZIP_PATH not found! Upload must have failed."
    exit 1
fi

# Use sudo for removal because docker volumes might have created root-owned files/folders
if [ -d "$HOME/phiblock_temp" ]; then 
    echo "clearing old files..."
    sudo rm -rf "$HOME/phiblock_temp"
fi

mkdir -p "$HOME/phiblock_temp"

# Try to install unzip again just in case, but don't fail if already there
sudo yum install -y unzip > /dev/null 2>&1 || true

if ! command -v unzip &> /dev/null; then
    echo "❌ Error: 'unzip' is not installed and could not be installed automatically."
    exit 1
fi

unzip -o -q "$ZIP_PATH" -d "$HOME/phiblock_temp"
cd "$HOME/phiblock_temp"

# Verify directory content
if [ ! -f "docker-compose.yml" ]; then
    echo "⚠️ Warning: docker-compose.yml not found in temp root. Checking subdirectories..."
    # If the user zipped the folder instead of contents, move everything up
    INNER_DIR=$(ls -d */ | head -n 1)
    if [ -n "$INNER_DIR" ] && [ -f "${INNER_DIR}docker-compose.yml" ]; then
        echo "Moving files from $INNER_DIR to current directory..."
        mv ${INNER_DIR}* .
        mv ${INNER_DIR}.* . 2>/dev/null || true
    fi
fi


# 5. Configure Environment
echo "⚙️ Configuring environment..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    # Generate a random secret key for the demo
    SECRET_KEY=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)
    sed -i "s/your-secret-key-here-change-in-production/$SECRET_KEY/" .env
    echo "✅ Created .env with generated SECRET_KEY"
fi

# 6. Build and Start
echo "🚀 Building and starting containers..."
sudo /usr/local/bin/docker-compose down || true
sudo /usr/local/bin/docker-compose up -d --build

# 7. Wait for API to be ready
echo "⏳ Waiting for API to start..."
MAX_RETRIES=30
COUNT=0
until $(curl -sfg http://localhost:8000/v1/health > /dev/null); do
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "❌ API failed to start in time. Check logs with 'docker-compose logs'"
        exit 1
    fi
    printf "."
    sleep 2
    COUNT=$((COUNT+1))
done

# Get Public IP via IMDSv2
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)

echo -e "\n✅ Deployment Complete!"
echo "🌐 URL: http://$PUBLIC_IP:8000"
echo "📚 API Docs: http://$PUBLIC_IP:8000/docs"

