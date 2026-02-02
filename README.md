# VIGIL v3.0 — EXTERNAL SMART WATCHDOG

## Architecture

```
EXTERNAL (Always On)
└── Vigil v3.0
    ├── Runs on: Pi / Cloud / Always-on device
    ├── Monitors: Jordan + MiniMax heartbeats
    ├── Recovery: Wake-on-LAN + SSH restart
    ├── Intelligence: MiniMax API for conversation
    ├── Fallback: Slash commands always work
    └── Alerts: Telegram to your phone

YOUR MAC (Can Sleep)
├── Jordan (OpenClaw Primary)
├── MiniMax Agent
└── Heartbeat sender → Vigil (every 60s)

YOU (Phone)
└── Telegram ↔ Vigil
    ├── "What happened last night?" → Intelligent answer
    ├── "Wake up my Mac" → Vigil sends Wake-on-LAN
    ├── "/status" → Works even if AI broken
    └── "Restart Jordan" → Vigil SSHs and restarts
```

## Deployment Options

### Option 1: Raspberry Pi (RECOMMENDED)
- Best for Wake-on-LAN (same network)
- Low power, always on
- Full local network access

### Option 2: Cloud Server (Railway/Fly.io/Oracle Free)
- Always on
- Wake-on-LAN requires router port forwarding
- Or use Tailscale for direct network access

### Option 3: Old Phone/Tablet
- Termux on Android can run this
- Always charging = always on

## Setup Steps

1. Deploy Vigil to external device
2. Configure Mac's Wake-on-LAN (System Preferences → Energy)
3. Set up heartbeat sender on Mac (cron job)
4. Configure SSH access from Vigil → Mac
5. Test everything

## Files

- `vigil.py` — Main Vigil server
- `Dockerfile` — For containerized deployment
- `docker-compose.yml` — Easy deployment
- `heartbeat-sender.sh` — Runs on Mac, sends heartbeats
- `requirements.txt` — Python dependencies
