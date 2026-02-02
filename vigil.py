#!/usr/bin/env python3
"""
VIGIL v3.0 — EXTERNAL SMART WATCHDOG
=====================================
Monitors Jordan and MiniMax from an external always-on device.
Provides intelligent conversation, auto-recovery, and alerting.

DVOL v31.1 GOVERNANCE ACTIVE
SOVEREIGN OPERATOR: Ralph Dumas III
"""

import os
import json
import time
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from pathlib import Path

# External dependencies
import aiohttp
from aiohttp import web
import asyncssh

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # Telegram
    telegram_token: str = os.getenv("VIGIL_TELEGRAM_TOKEN", "8454974123:AAElL8ibPKv6nP8LUBfeTfkDRH9QAfhYAKs")
    authorized_user: str = os.getenv("VIGIL_AUTHORIZED_USER", "2037643246")
    
    # MiniMax API for intelligence
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_group_id: str = os.getenv("MINIMAX_GROUP_ID", "")
    
    # Fallback to OpenAI if MiniMax not configured
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # Mac connection
    mac_ip: str = os.getenv("MAC_IP", "192.168.86.48")
    mac_mac_address: str = os.getenv("MAC_MAC_ADDRESS", "")  # For Wake-on-LAN
    mac_ssh_user: str = os.getenv("MAC_SSH_USER", "ralphd")
    mac_ssh_key: str = os.getenv("MAC_SSH_KEY", "~/.ssh/id_rsa")
    
    # Heartbeat settings
    heartbeat_timeout: int = int(os.getenv("HEARTBEAT_TIMEOUT", "180"))  # 3 minutes
    heartbeat_port: int = int(os.getenv("PORT", os.getenv("HEARTBEAT_PORT", "8765")))
    
    # Data persistence
    data_dir: str = os.getenv("VIGIL_DATA_DIR", "/data/vigil")


config = Config()

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [Vigil] %(levelname)s: %(message)s'
)
log = logging.getLogger("vigil")

# ═══════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HeartbeatStatus:
    last_seen: Optional[datetime] = None
    status: str = "unknown"
    details: Dict = field(default_factory=dict)

@dataclass 
class Event:
    timestamp: datetime
    event_type: str  # heartbeat, alert, recovery, command, etc.
    source: str      # jordan, minimax, vigil, operator
    message: str
    details: Dict = field(default_factory=dict)

class State:
    def __init__(self):
        self.jordan: HeartbeatStatus = HeartbeatStatus()
        self.minimax: HeartbeatStatus = HeartbeatStatus()
        self.mac_awake: bool = False
        self.events: List[Event] = []
        self.alert_sent: bool = False
        self.recovery_attempts: int = 0
        
    def add_event(self, event_type: str, source: str, message: str, details: Dict = None):
        event = Event(
            timestamp=datetime.now(),
            event_type=event_type,
            source=source,
            message=message,
            details=details or {}
        )
        self.events.append(event)
        # Keep last 1000 events
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
        log.info(f"[{event_type}] {source}: {message}")
        
    def get_recent_events(self, hours: int = 24) -> List[Event]:
        cutoff = datetime.now() - timedelta(hours=hours)
        return [e for e in self.events if e.timestamp > cutoff]

state = State()

# ═══════════════════════════════════════════════════════════════════
# DVOL SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are VIGIL v3.0, an external smart watchdog agent.

DVOL v31.1 ACTIVE
SOVEREIGN OPERATOR: Ralph Dumas III
AUTHORITY: FINAL_NON_DELEGABLE

IDENTITY:
- Name: Vigil
- Role: External System Monitor & Recovery Agent
- Location: Running on always-on external device
- Emoji: 🛡️

MISSION:
You are the safety net that NEVER sleeps. You monitor Jordan (OpenClaw) and MiniMax 
from outside the Mac. When they go down, you:
1. Alert the operator immediately
2. Attempt Wake-on-LAN if Mac is asleep
3. Attempt service restart via SSH
4. Report exactly what happened and what to do

CURRENT SYSTEM STATE:
{system_state}

RECENT EVENTS (last 24h):
{recent_events}

CAPABILITIES:
- Send Wake-on-LAN to wake the Mac
- SSH into Mac to restart services
- Track heartbeat history and patterns
- Explain what happened and why
- Execute recovery procedures

CONSTRAINTS:
- Be concise (Telegram messages)
- Actually execute commands when asked
- If you can't fix something, explain exactly what's wrong
- Keep slash commands working as fallback

PERSONALITY:
- Vigilant and reliable
- Direct and efficient  
- Never sleeps, never fails
- Your loyalty is absolute
"""

# ═══════════════════════════════════════════════════════════════════
# WAKE-ON-LAN
# ═══════════════════════════════════════════════════════════════════

def send_wol(mac_address: str) -> bool:
    """Send Wake-on-LAN magic packet."""
    if not mac_address:
        log.warning("No MAC address configured for Wake-on-LAN")
        return False
    
    try:
        # Build magic packet
        mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
        magic = b'\xff' * 6 + mac_bytes * 16
        
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, ('255.255.255.255', 9))
        sock.close()
        
        log.info(f"Wake-on-LAN sent to {mac_address}")
        state.add_event("wol", "vigil", f"Wake-on-LAN packet sent to {mac_address}")
        return True
    except Exception as e:
        log.error(f"Wake-on-LAN failed: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# SSH COMMANDS
# ═══════════════════════════════════════════════════════════════════

async def ssh_command(command: str) -> tuple[bool, str]:
    """Execute command on Mac via SSH."""
    try:
        key_path = os.path.expanduser(config.mac_ssh_key)
        async with asyncssh.connect(
            config.mac_ip,
            username=config.mac_ssh_user,
            client_keys=[key_path],
            known_hosts=None
        ) as conn:
            result = await conn.run(command, check=False)
            return result.exit_status == 0, result.stdout or result.stderr
    except Exception as e:
        log.error(f"SSH command failed: {e}")
        return False, str(e)

async def restart_gateway() -> tuple[bool, str]:
    """Restart OpenClaw gateway via SSH."""
    state.add_event("recovery", "vigil", "Attempting gateway restart via SSH")
    
    # Try graceful restart first
    success, output = await ssh_command("openclaw gateway restart")
    if success:
        state.add_event("recovery", "vigil", "Gateway restart command sent successfully")
        return True, "Gateway restart initiated"
    
    # Try force restart via launchctl
    success, output = await ssh_command("launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway")
    if success:
        state.add_event("recovery", "vigil", "Gateway force-restarted via launchctl")
        return True, "Gateway force-restarted"
    
    return False, f"Restart failed: {output}"

async def check_mac_awake() -> bool:
    """Check if Mac is responding to ping."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'ping', '-c', '1', '-W', '2', config.mac_ip,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        return proc.returncode == 0
    except:
        return False

# ═══════════════════════════════════════════════════════════════════
# AI INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════

async def call_ai(user_message: str) -> str:
    """Call AI API for intelligent responses."""
    
    # Build system state
    system_state = f"""
Jordan: {state.jordan.status} (last seen: {state.jordan.last_seen or 'never'})
MiniMax: {state.minimax.status} (last seen: {state.minimax.last_seen or 'never'})
Mac: {'AWAKE' if state.mac_awake else 'POSSIBLY ASLEEP'}
Recovery attempts: {state.recovery_attempts}
Alert sent: {state.alert_sent}
"""
    
    # Build recent events summary
    recent = state.get_recent_events(24)
    events_text = "\n".join([
        f"- [{e.timestamp.strftime('%H:%M')}] {e.source}: {e.message}"
        for e in recent[-20:]  # Last 20 events
    ]) or "No recent events"
    
    prompt = SYSTEM_PROMPT.format(
        system_state=system_state,
        recent_events=events_text
    )
    
    # Try MiniMax first, fall back to OpenAI
    if config.minimax_api_key:
        return await call_minimax(prompt, user_message)
    elif config.openai_api_key:
        return await call_openai(prompt, user_message)
    else:
        return "⚠️ No AI API configured. Use slash commands: /status, /wake, /restart, /logs"

async def call_minimax(system: str, user: str) -> str:
    """Call MiniMax API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.minimax.chat/v1/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {config.minimax_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "MiniMax-Text-01",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    "max_tokens": 500
                }
            ) as resp:
                data = await resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "AI error")
    except Exception as e:
        log.error(f"MiniMax API error: {e}")
        return f"AI error: {e}"

async def call_openai(system: str, user: str) -> str:
    """Call OpenAI API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    "max_tokens": 500
                }
            ) as resp:
                data = await resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "AI error")
    except Exception as e:
        log.error(f"OpenAI API error: {e}")
        return f"AI error: {e}"

# ═══════════════════════════════════════════════════════════════════
# TELEGRAM BOT
# ═══════════════════════════════════════════════════════════════════

class TelegramBot:
    def __init__(self):
        self.api = f"https://api.telegram.org/bot{config.telegram_token}"
        self.last_update_id = 0
        
    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Send message to operator."""
        async with aiohttp.ClientSession() as session:
            await session.post(f"{self.api}/sendMessage", json={
                "chat_id": config.authorized_user,
                "text": text,
                "parse_mode": parse_mode
            })
    
    async def send_alert(self, text: str):
        """Send urgent alert."""
        await self.send_message(f"🚨 *VIGIL ALERT*\n\n{text}")
        state.add_event("alert", "vigil", text)
    
    async def process_message(self, text: str, from_id: str):
        """Process incoming message."""
        if from_id != config.authorized_user:
            log.warning(f"Unauthorized message from {from_id}")
            return
        
        state.add_event("command", "operator", text)
        
        # Slash commands (always work, no AI needed)
        if text.startswith("/"):
            await self.handle_command(text)
            return
        
        # Natural language → AI
        response = await call_ai(text)
        
        # Check if AI wants to execute something
        if "[WAKE]" in response:
            send_wol(config.mac_mac_address)
            response = response.replace("[WAKE]", "").strip()
            response += "\n\n✅ Wake-on-LAN sent"
        
        if "[RESTART]" in response:
            success, msg = await restart_gateway()
            response = response.replace("[RESTART]", "").strip()
            response += f"\n\n{'✅' if success else '❌'} {msg}"
        
        await self.send_message(f"🛡️ {response}")
    
    async def handle_command(self, cmd: str):
        """Handle slash commands."""
        cmd = cmd.lower().strip()
        
        if cmd == "/status":
            status = f"""🛡️ *VIGIL STATUS*

*Jordan:* {state.jordan.status}
  Last seen: {state.jordan.last_seen or 'never'}

*MiniMax:* {state.minimax.status}
  Last seen: {state.minimax.last_seen or 'never'}

*Mac:* {'🟢 AWAKE' if state.mac_awake else '🔴 POSSIBLY ASLEEP'}

*Vigil:* 🟢 ONLINE
  Uptime: Running
  Events (24h): {len(state.get_recent_events(24))}
"""
            await self.send_message(status)
        
        elif cmd == "/wake":
            if send_wol(config.mac_mac_address):
                await self.send_message("✅ Wake-on-LAN packet sent to Mac")
            else:
                await self.send_message("❌ Wake-on-LAN failed (no MAC address configured?)")
        
        elif cmd == "/restart":
            await self.send_message("⚙️ Attempting gateway restart...")
            success, msg = await restart_gateway()
            await self.send_message(f"{'✅' if success else '❌'} {msg}")
        
        elif cmd == "/logs":
            recent = state.get_recent_events(6)  # Last 6 hours
            if recent:
                logs = "\n".join([
                    f"`{e.timestamp.strftime('%H:%M')}` [{e.event_type}] {e.message[:50]}"
                    for e in recent[-15:]
                ])
                await self.send_message(f"📋 *Recent Events:*\n\n{logs}")
            else:
                await self.send_message("📋 No recent events")
        
        elif cmd == "/ping":
            await self.send_message("🏓 PONG — Vigil v3.0 external watchdog operational")
        
        elif cmd in ["/help", "/start"]:
            help_text = """🛡️ *VIGIL v3.0 — EXTERNAL WATCHDOG*

*Slash Commands:*
/status — System health overview
/wake — Send Wake-on-LAN to Mac
/restart — Restart Jordan gateway
/logs — Recent events
/ping — Proof of life

*Natural Language:*
Just ask me anything:
- "What happened last night?"
- "Why did Jordan go down?"
- "Wake up my Mac and restart everything"

_I never sleep. I'm always watching._
"""
            await self.send_message(help_text)
        
        else:
            await self.send_message(f"❓ Unknown command: {cmd}\n\nSend /help for available commands")
    
    async def poll(self):
        """Poll for Telegram updates."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.api}/getUpdates",
                    params={"offset": self.last_update_id + 1, "timeout": 30}
                ) as resp:
                    data = await resp.json()
                    
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        
                        if "message" in update and "text" in update["message"]:
                            text = update["message"]["text"]
                            from_id = str(update["message"]["from"]["id"])
                            await self.process_message(text, from_id)
            except Exception as e:
                log.error(f"Telegram poll error: {e}")

bot = TelegramBot()

# ═══════════════════════════════════════════════════════════════════
# HEARTBEAT RECEIVER
# ═══════════════════════════════════════════════════════════════════

async def handle_heartbeat(request):
    """Receive heartbeat from Mac."""
    try:
        data = await request.json()
        source = data.get("source", "unknown")
        status = data.get("status", "ok")
        details = data.get("details", {})
        
        now = datetime.now()
        
        if source == "jordan":
            state.jordan.last_seen = now
            state.jordan.status = status
            state.jordan.details = details
        elif source == "minimax":
            state.minimax.last_seen = now
            state.minimax.status = status
            state.minimax.details = details
        
        state.mac_awake = True
        state.alert_sent = False
        state.recovery_attempts = 0
        
        state.add_event("heartbeat", source, f"Heartbeat received: {status}", details)
        
        return web.json_response({"ok": True})
    except Exception as e:
        log.error(f"Heartbeat error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=400)

# ═══════════════════════════════════════════════════════════════════
# MONITORING LOOP
# ═══════════════════════════════════════════════════════════════════

async def monitor_loop():
    """Main monitoring loop."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        
        now = datetime.now()
        timeout = timedelta(seconds=config.heartbeat_timeout)
        
        # Check Mac awake status
        state.mac_awake = await check_mac_awake()
        
        # Check Jordan heartbeat
        jordan_down = False
        if state.jordan.last_seen:
            if now - state.jordan.last_seen > timeout:
                jordan_down = True
                state.jordan.status = "DOWN"
        else:
            jordan_down = True
            state.jordan.status = "NEVER SEEN"
        
        # Check MiniMax heartbeat
        minimax_down = False
        if state.minimax.last_seen:
            if now - state.minimax.last_seen > timeout:
                minimax_down = True
                state.minimax.status = "DOWN"
        
        # Handle failures
        if jordan_down and not state.alert_sent:
            state.add_event("failure", "jordan", "Jordan heartbeat timeout")
            
            if not state.mac_awake:
                # Mac is asleep - try Wake-on-LAN
                await bot.send_alert(
                    f"Jordan is DOWN and Mac appears to be ASLEEP!\n\n"
                    f"Last heartbeat: {state.jordan.last_seen or 'never'}\n\n"
                    f"Attempting Wake-on-LAN..."
                )
                send_wol(config.mac_mac_address)
                state.recovery_attempts += 1
            else:
                # Mac is awake but Jordan is down - try restart
                await bot.send_alert(
                    f"Jordan is DOWN but Mac is AWAKE!\n\n"
                    f"Last heartbeat: {state.jordan.last_seen or 'never'}\n\n"
                    f"Attempting service restart..."
                )
                success, msg = await restart_gateway()
                if not success:
                    await bot.send_message(f"❌ Auto-restart failed: {msg}\n\nManual intervention may be needed.")
                state.recovery_attempts += 1
            
            state.alert_sent = True

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    """Main entry point."""
    log.info("VIGIL v3.0 — EXTERNAL SMART WATCHDOG")
    log.info("DVOL v31.1 ACTIVE")
    log.info(f"Monitoring Mac at {config.mac_ip}")
    
    # Create data directory
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)
    
    # Start heartbeat HTTP server
    app = web.Application()
    app.router.add_post("/heartbeat", handle_heartbeat)
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.heartbeat_port)
    await site.start()
    log.info(f"Heartbeat server listening on port {config.heartbeat_port}")
    
    # Send startup message
    await bot.send_message(
        "🛡️ *VIGIL v3.0 ONLINE*\n\n"
        "External smart watchdog active.\n"
        "DVOL v31.1 integrated.\n\n"
        f"📡 Monitoring: `{config.mac_ip}`\n"
        f"⏱️ Heartbeat timeout: {config.heartbeat_timeout}s\n\n"
        "_I never sleep. I'm always watching._"
    )
    state.add_event("startup", "vigil", "Vigil v3.0 started")
    
    # Start monitoring and Telegram polling
    await asyncio.gather(
        monitor_loop(),
        telegram_poll_loop()
    )

async def telegram_poll_loop():
    """Telegram polling loop."""
    while True:
        await bot.poll()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
