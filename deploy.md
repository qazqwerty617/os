# 🚀 Deployment Guide (VPS)

## 1. Prepare VPS (Ubuntu/Debian)
Login to your VPS and install Docker & Git:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install -y docker-compose-plugin
```

## 2. Upload Files
You can use `scp` or `FileZilla` to upload your bot folder to `/root/mexc_bot`.
Or if you use git:
```bash
git clone <your-repo-url> mexc_bot
cd mexc_bot
```

## 3. Configuration
Create your `.env` file on the VPS:
```bash
cp .env.example .env
nano .env
```
Paste your API keys inside (if you have them).

## 4. Launch 🚀
Start the bot in background mode:

```bash
docker compose up -d --build
```

## 5. Control
Check logs:
```bash
docker compose logs -f
```

Stop bot:
```bash
docker compose down
```

Restart bot:
```bash
docker compose restart
```

## 🛡️ Security Tips
- Don't expose port 8080 publicly unless you set up Nginx + SSL.
- Use a firewall (`ufw`) to block unwanted ports.
