# 🚀 Deployment Guide (Git Workflow)

This guide explains how to deploy updates to your VPS using the Git-based workflow.

## 📋 Prerequisites
- You are in the project folder: `cd ~/Downloads/OS`
- You have initialized the git repo (already done)

## 🔄 Workflow

### Step 1: Save & Push Changes to GitHub
Run this on your local machine to send code to the cloud.

```bash
git add .
git commit -m "Update bot version"
git push
```

### Step 2: Update the VPS
Run this script to make the VPS download the latest code and restart the bot.

```bash
./deploy_via_git.sh
```

---
*Note: You will be asked for the VPS password (check your notes).*
