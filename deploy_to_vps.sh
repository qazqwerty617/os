#!/bin/bash

# Configuration
# Replace these with your VPS details
VPS_USER="root"
VPS_IP="207.180.212.179"
REMOTE_DIR="/root/mexc_pump_monitor"

echo "🚀 Deploying MEXC Pump Monitor to VPS ($VPS_IP)..."

# 1. IP Check Passed
echo "📡 Connecting to $VPS_USER@$VPS_IP..."

# 2. Create remote directory
echo "📂 Creating remote directory..."
ssh $VPS_USER@$VPS_IP "mkdir -p $REMOTE_DIR"

# 3. Copy files (excluding heavy/unnecessary folders)
echo "Ep📦 Uploading files..."
rsync -avz --exclude 'venv' --exclude '__pycache__' --exclude '.git' --exclude 'journal_data' --exclude 'learning_data' ./ $VPS_USER@$VPS_IP:$REMOTE_DIR

# 4. Install Docker if missing, open firewall, and start bot
echo "🐳 Checking for Docker on VPS..."
ssh -o StrictHostKeyChecking=no root@$VPS_IP << 'ENDSSH'
    # Install Docker if missing
    if ! command -v docker &> /dev/null; then
        echo "🐳 Installing Docker on VPS..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        # Install Compose Plugin explicitly just in case (retained from original)
        apt-get update && apt-get install -y docker-compose-plugin
    else
        echo "✅ Docker is already installed."
    fi
    
    # FIX FIREWALL: Open Dashboard Port
    echo "🔓 Opening Port 8081..."
    ufw allow 8081/tcp
    ufw reload
    
    # Start Bot
    echo "🚀 Starting Bot..."
    cd /root/mexc_pump_monitor
    docker compose down
    docker compose up -d --build
ENDSSH

echo "✅ DEPLOYMENT COMPLETE!"
echo "   Monitor logs command: ssh $VPS_USER@$VPS_IP 'cd $REMOTE_DIR && docker compose logs -f'"
