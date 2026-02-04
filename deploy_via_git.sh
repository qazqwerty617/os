#!/bin/bash
# VPS Deployment Script via Git
# Usage: ./deploy_via_git.sh

SERVER_IP="207.180.212.179"
REMOTE_DIR="/root/mexc_pump_monitor"
REPO_URL="https://github.com/qazqwerty617/os.git"

echo "🚀 Deploying via Git to $SERVER_IP..."

# 0. Upload secrets (.env) manually since it's not in git
echo "🔑 Uploading .env file..."
scp .env root@$SERVER_IP:$REMOTE_DIR/.env

# 1. Update VPS code
echo "📡 Pulling latest code on server..."
ssh root@$SERVER_IP "
    # Install git if missing
    if ! command -v git &> /dev/null; then
        apt-get update && apt-get install -y git
    fi

    # Clone or Pull
    if [ ! -d "$REMOTE_DIR" ]; then
        echo '📂 Cloning repository...'
        git clone $REPO_URL $REMOTE_DIR
    else
        echo '🔄 Updating repository...'
        cd $REMOTE_DIR
        
        # Handle migration from non-git folder
        if [ ! -d ".git" ]; then
            echo '⚠️  Converting to Git repo...'
            git init
            git remote add origin $REPO_URL
            git fetch --all
            git reset --hard origin/main
            git branch -M main
        else
            git reset --hard
            git pull
        fi
    fi
    
    # 2. Rebuild & Restart
    echo '🐳 Rebuilding containers...'
    cd $REMOTE_DIR
    
    # Create necessary dirs
    mkdir -p journal_data learning_data
    
    # Run Docker
    docker compose down
    docker compose up -d --build
    
    echo '✅ Deployment Complete!'
"

echo "📜 Done. Monitor logs with:"
echo "ssh root@$SERVER_IP 'cd $REMOTE_DIR && docker compose logs -f'"
