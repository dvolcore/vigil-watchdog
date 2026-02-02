# VIGIL v3.0 EXTERNAL WATCHDOG — SETUP GUIDE

## Overview

Vigil runs on an external always-on device and monitors your Mac remotely.
When Jordan or MiniMax go down, Vigil alerts you and can auto-recover.

## Prerequisites

Choose ONE deployment option:

### Option A: Raspberry Pi (RECOMMENDED)
- Best for Wake-on-LAN (same network)
- Get a Pi 4 or Pi Zero 2 W (~$35-55)
- Install Raspberry Pi OS Lite

### Option B: Cloud Server
- Railway.app (free tier)
- Fly.io (free tier)
- Oracle Cloud (free forever tier)
- Any VPS with Docker

### Option C: Old Android Phone
- Install Termux
- Run Python directly

---

## Step 1: Enable Wake-on-LAN on Your Mac

1. System Settings → Battery → Options
2. Enable "Wake for network access"
3. Get your Mac's MAC address:
   ```bash
   networksetup -getmacaddress en0
   ```
4. Note this address (format: aa:bb:cc:dd:ee:ff)

---

## Step 2: Enable SSH on Your Mac

1. System Settings → General → Sharing
2. Enable "Remote Login"
3. Test: `ssh ralphd@192.168.86.48`

---

## Step 3: Generate SSH Key for Vigil

On your Mac:
```bash
# Generate key pair for Vigil
ssh-keygen -t rsa -b 4096 -f ~/.ssh/vigil_key -N ""

# Add to authorized keys
cat ~/.ssh/vigil_key.pub >> ~/.ssh/authorized_keys

# Copy private key to Vigil (you'll need this)
cat ~/.ssh/vigil_key
```

---

## Step 4: Deploy Vigil

### On Raspberry Pi:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Clone Vigil files (or copy from Mac)
mkdir ~/vigil && cd ~/vigil
# Copy all files from vigil-external/ to here

# Create .env file
cat > .env << EOF
VIGIL_TELEGRAM_TOKEN=8454974123:AAElL8ibPKv6nP8LUBfeTfkDRH9QAfhYAKs
VIGIL_AUTHORIZED_USER=2037643246
MAC_IP=192.168.86.48
MAC_MAC_ADDRESS=YOUR_MAC_ADDRESS_HERE
MAC_SSH_USER=ralphd
OPENAI_API_KEY=your_key_here
EOF

# Copy SSH key
mkdir -p ~/.ssh
# Paste the vigil_key content into ~/.ssh/id_rsa

# Start Vigil
docker compose up -d
```

### On Railway/Fly.io:

1. Push files to GitHub repo
2. Connect to Railway/Fly
3. Set environment variables in dashboard
4. Deploy

---

## Step 5: Install Heartbeat Sender on Mac

```bash
# Copy heartbeat sender
cp heartbeat-sender.sh ~/.openclaw/sentinel/

# Edit to set Vigil's IP
nano ~/.openclaw/sentinel/heartbeat-sender.sh
# Change VIGIL_URL to your Pi/cloud IP:
# VIGIL_URL="http://192.168.86.XXX:8765/heartbeat"

# Add to crontab (runs every minute)
crontab -e
# Add this line:
# * * * * * /Users/ralphd/.openclaw/sentinel/heartbeat-sender.sh

# Test it
/Users/ralphd/.openclaw/sentinel/heartbeat-sender.sh
```

---

## Step 6: Test Everything

1. **Test Vigil is responding:**
   - Send `/ping` to @Virgil_Clawl_bot

2. **Test heartbeats arriving:**
   - Send `/status` — should show Jordan as "ok"

3. **Test Wake-on-LAN:**
   - Put Mac to sleep
   - Send `/wake` to Vigil
   - Mac should wake up

4. **Test restart:**
   - Kill gateway: `pkill -f "openclaw.*gateway"`
   - Send `/restart` to Vigil
   - Gateway should restart

5. **Test full recovery:**
   - Put Mac to sleep
   - Wait 3+ minutes
   - Vigil should alert you and attempt wake + restart

---

## Configuration Reference

| Variable | Description | Required |
|----------|-------------|----------|
| VIGIL_TELEGRAM_TOKEN | Vigil's Telegram bot token | Yes |
| VIGIL_AUTHORIZED_USER | Your Telegram user ID | Yes |
| MAC_IP | Your Mac's local IP | Yes |
| MAC_MAC_ADDRESS | Your Mac's MAC address (for WoL) | For wake |
| MAC_SSH_USER | SSH username on Mac | For restart |
| OPENAI_API_KEY | For AI intelligence | Recommended |
| MINIMAX_API_KEY | Alternative AI | Optional |
| HEARTBEAT_TIMEOUT | Seconds before alert (default: 180) | Optional |

---

## Troubleshooting

### Wake-on-LAN not working
- Ensure Mac is connected via Ethernet OR WiFi with "Wake for network access" enabled
- Some routers block WoL broadcasts — may need port forwarding for UDP port 9

### SSH not working
- Check firewall allows port 22
- Verify SSH key is correct
- Test manually: `ssh -i ~/.ssh/vigil_key ralphd@192.168.86.48`

### Heartbeats not arriving
- Check Mac can reach Vigil: `curl http://VIGIL_IP:8765/health`
- Check crontab is running: `crontab -l`
- Check heartbeat logs on Vigil

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL (Always On)                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    VIGIL v3.0                            │   │
│  │  • Runs on Pi / Cloud                                    │   │
│  │  • Receives heartbeats from Mac                          │   │
│  │  • Monitors Jordan + MiniMax                             │   │
│  │  • Sends Wake-on-LAN if Mac asleep                      │   │
│  │  • SSHs to restart services                              │   │
│  │  • AI-powered conversation                               │   │
│  │  • Alerts via Telegram                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│         ▲                    │                                   │
│         │ Heartbeats         │ Wake-on-LAN / SSH                │
│         │ (every 60s)        ▼                                   │
└─────────┼───────────────────────────────────────────────────────┘
          │
┌─────────┼───────────────────────────────────────────────────────┐
│         │              YOUR MAC (Can Sleep)                      │
│  ┌──────┴──────────────────────────────────────────────────┐   │
│  │  Heartbeat Sender (cron)                                 │   │
│  │  • Checks Jordan status                                  │   │
│  │  • Checks MiniMax status                                 │   │
│  │  • Sends to Vigil every minute                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Jordan (OpenClaw Primary)                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  MiniMax Agent                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │
          │ Telegram
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      YOU (Phone)                                 │
│  • Get alerts when things go down                               │
│  • "What happened last night?" → Intelligent answer             │
│  • "Wake up my Mac" → Vigil sends WoL                          │
│  • "/restart" → Vigil SSHs and restarts                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Get hardware**: Raspberry Pi 4 or Pi Zero 2 W
2. **Deploy Vigil**: Follow steps above
3. **Test thoroughly**: Before relying on it
4. **Consider Tailscale**: For easy remote access without port forwarding
