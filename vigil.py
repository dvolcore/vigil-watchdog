#!/usr/bin/env python3
"""
VIGIL v4.0 — ENHANCED EXTERNAL SMART WATCHDOG
==============================================
Monitors Jordan and MiniMax from an external always-on device.
Provides intelligent conversation, auto-recovery, predictive alerts.

DVOL v31.1 GOVERNANCE ACTIVE
SOVEREIGN OPERATOR: Ralph Dumas III

ENHANCEMENTS v4.0:
- Tailscale integration for secure remote access
- Predictive maintenance with pattern analysis
- Multi-channel alerting (Telegram + SMS backup)
- Automated backup verification
- Custom recovery scripts per service
- Real-time metrics and analytics
"""

import os
import json
import time
import asyncio
import logging
import subprocess
import statistics
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque

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
    
    # Mac connection - supports both direct IP and Tailscale
    mac_ip: str = os.getenv("MAC_IP", "192.168.86.48")
    mac_tailscale_ip: str = os.getenv("MAC_TAILSCALE_IP", "100.119.246.88")
    mac_mac_address: str = os.getenv("MAC_MAC_ADDRESS", "")  # For Wake-on-LAN
    mac_ssh_user: str = os.getenv("MAC_SSH_USER", "ralphd")
    mac_ssh_key: str = os.getenv("MAC_SSH_KEY", "")  # Base64 encoded key or path
    
    # Heartbeat settings
    heartbeat_timeout: int = int(os.getenv("HEARTBEAT_TIMEOUT", "180"))  # 3 minutes
    heartbeat_port: int = int(os.getenv("PORT", os.getenv("HEARTBEAT_PORT", "8765")))
    
    # Alert settings
    twilio_sid: str = os.getenv("TWILIO_SID", "")
    twilio_token: str = os.getenv("TWILIO_TOKEN", "")
    twilio_from: str = os.getenv("TWILIO_FROM", "")
    sms_to: str = os.getenv("SMS_TO", "")
    
    # Predictive maintenance
    enable_ml: bool = os.getenv("ENABLE_ML", "true").lower() == "true"
    anomaly_threshold: float = float(os.getenv("ANOMALY_THRESHOLD", "2.0"))  # std devs
    
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
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))

@dataclass 
class Event:
    timestamp: datetime
    event_type: str  # heartbeat, alert, recovery, command, prediction, etc.
    source: str      # jordan, minimax, vigil, operator
    message: str
    details: Dict = field(default_factory=dict)

@dataclass
class Metrics:
    """Real-time metrics for monitoring."""
    heartbeat_count: int = 0
    alert_count: int = 0
    recovery_success: int = 0
    recovery_failed: int = 0
    uptime_percentage: float = 100.0
    avg_response_time: float = 0.0
    anomalies_detected: int = 0
    
class State:
    def __init__(self):
        self.jordan: HeartbeatStatus = HeartbeatStatus()
        self.minimax: HeartbeatStatus = HeartbeatStatus()
        self.mac_awake: bool = False
        self.events: List[Event] = []
        self.alert_sent: bool = False
        self.recovery_attempts: int = 0
        self.metrics: Metrics = Metrics()
        
        # Predictive maintenance data
        self.heartbeat_intervals: deque = deque(maxlen=1000)
        self.failure_patterns: List[Dict] = []
        self.predicted_issues: List[str] = []
        
        # Backup tracking
        self.last_backup_check: Optional[datetime] = None
        self.backup_status: str = "unknown"
        
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
# PREDICTIVE MAINTENANCE / ML LITE
# ═══════════════════════════════════════════════════════════════════

class PredictiveEngine:
    """Pattern analysis for predictive maintenance."""
    
    def __init__(self, state: State):
        self.state = state
        
    def record_heartbeat_interval(self, interval_seconds: float):
        """Record time between heartbeats for analysis."""
        self.state.heartbeat_intervals.append(interval_seconds)
        
    def detect_anomaly(self, current_interval: float) -> Tuple[bool, str]:
        """Detect if current heartbeat interval is anomalous."""
        if len(self.state.heartbeat_intervals) < 10:
            return False, "Insufficient data"
        
        intervals = list(self.state.heartbeat_intervals)
        mean = statistics.mean(intervals)
        stdev = statistics.stdev(intervals) if len(intervals) > 1 else 0
        
        if stdev == 0:
            return False, "No variance"
        
        z_score = (current_interval - mean) / stdev
        
        if abs(z_score) > config.anomaly_threshold:
            self.state.metrics.anomalies_detected += 1
            reason = f"Interval {current_interval:.1f}s is {z_score:.1f} std devs from mean {mean:.1f}s"
            return True, reason
        
        return False, "Normal"
    
    def predict_failure(self) -> Optional[str]:
        """Analyze patterns to predict potential failures."""
        recent_events = self.state.get_recent_events(6)
        
        # Pattern 1: Increasing response times
        if len(self.state.jordan.response_times) >= 10:
            times = list(self.state.jordan.response_times)
            recent_avg = statistics.mean(times[-5:])
            older_avg = statistics.mean(times[-10:-5])
            if recent_avg > older_avg * 1.5:
                return "⚠️ Response times increasing - potential degradation"
        
        # Pattern 2: Frequent brief outages
        brief_outages = [e for e in recent_events if e.event_type == "failure"]
        if len(brief_outages) >= 3:
            return "⚠️ Multiple brief outages detected - system may be unstable"
        
        # Pattern 3: Recovery attempts increasing
        if self.state.recovery_attempts >= 2:
            return "⚠️ Multiple recovery attempts - underlying issue likely"
        
        return None

predictor = PredictiveEngine(state)

# ═══════════════════════════════════════════════════════════════════
# MULTI-CHANNEL ALERTING
# ═══════════════════════════════════════════════════════════════════

class AlertManager:
    """Multi-channel alerting with escalation."""
    
    def __init__(self):
        self.alert_history: deque = deque(maxlen=100)
        self.escalation_level: int = 0
        
    async def send_alert(self, message: str, level: str = "warning"):
        """Send alert through appropriate channels based on level."""
        
        # Level 1: Telegram only
        await bot.send_message(f"🚨 *VIGIL ALERT*\n\n{message}")
        state.add_event("alert", "vigil", message)
        state.metrics.alert_count += 1
        
        # Level 2: Add SMS for critical
        if level == "critical" and config.twilio_sid:
            await self.send_sms(f"VIGIL CRITICAL: {message[:140]}")
            
        self.alert_history.append({
            "time": datetime.now(),
            "message": message,
            "level": level
        })
    
    async def send_sms(self, message: str):
        """Send SMS via Twilio."""
        if not all([config.twilio_sid, config.twilio_token, config.twilio_from, config.sms_to]):
            log.warning("SMS not configured")
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(config.twilio_sid, config.twilio_token)
                await session.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_sid}/Messages.json",
                    auth=auth,
                    data={
                        "From": config.twilio_from,
                        "To": config.sms_to,
                        "Body": message
                    }
                )
            log.info(f"SMS sent: {message[:50]}...")
        except Exception as e:
            log.error(f"SMS failed: {e}")

alerts = AlertManager()

# ═══════════════════════════════════════════════════════════════════
# DVOL SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are VIGIL v4.0, an enhanced external smart watchdog agent.

DVOL v31.1 ACTIVE
SOVEREIGN OPERATOR: Ralph Dumas III
AUTHORITY: FINAL_NON_DELEGABLE

IDENTITY:
- Name: Vigil
- Role: External System Monitor, Recovery Agent, Predictive Analyst
- Location: Running on always-on cloud infrastructure (Railway)
- Emoji: 🛡️

MISSION:
You are the safety net that NEVER sleeps. You monitor Jordan (OpenClaw) and MiniMax 
from outside the Mac. You now have ENHANCED capabilities:

ENHANCED CAPABILITIES (v4.0):
1. Tailscale integration - secure tunnel to Mac from anywhere
2. Predictive maintenance - detect issues BEFORE they cause outages
3. Multi-channel alerts - Telegram + SMS for critical issues
4. Automated backup verification - ensure data safety
5. Custom recovery scripts - service-specific recovery procedures
6. Real-time analytics - track patterns and performance

CURRENT SYSTEM STATE:
{system_state}

METRICS:
{metrics}

PREDICTIONS:
{predictions}

RECENT EVENTS (last 24h):
{recent_events}

COMMANDS YOU CAN EXECUTE:
- [WAKE] - Send Wake-on-LAN to Mac
- [RESTART] - Restart OpenClaw gateway
- [RESTART_MINIMAX] - Restart MiniMax agent
- [CHECK_BACKUP] - Verify backup status
- [DIAGNOSTICS] - Run full system diagnostics
- [TAILSCALE_PING] - Test Tailscale connectivity

When user asks you to do something, include the appropriate [COMMAND] tag in your response.

PERSONALITY:
- Vigilant and proactive (not just reactive)
- Predicts problems before they happen
- Direct and efficient  
- Never sleeps, never fails
- Your loyalty is absolute
"""

# ═══════════════════════════════════════════════════════════════════
# TAILSCALE CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════

async def tailscale_ping() -> Tuple[bool, float]:
    """Check Tailscale connectivity and measure latency."""
    if not config.mac_tailscale_ip:
        return False, 0
    
    try:
        start = time.time()
        proc = await asyncio.create_subprocess_exec(
            'ping', '-c', '1', '-W', '5', config.mac_tailscale_ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.wait()
        latency = (time.time() - start) * 1000  # ms
        return proc.returncode == 0, latency
    except Exception as e:
        log.error(f"Tailscale ping failed: {e}")
        return False, 0

async def get_best_ssh_ip() -> str:
    """Get the best IP for SSH connection (Tailscale preferred)."""
    # Try Tailscale first
    success, latency = await tailscale_ping()
    if success:
        log.info(f"Using Tailscale IP ({latency:.0f}ms latency)")
        return config.mac_tailscale_ip
    
    # Fall back to direct IP
    return config.mac_ip

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

async def ssh_command(command: str) -> Tuple[bool, str]:
    """Execute command on Mac via SSH (Tailscale or direct)."""
    try:
        ip = await get_best_ssh_ip()
        
        # Handle base64-encoded key from env
        key_path = None
        if config.mac_ssh_key:
            if config.mac_ssh_key.startswith("/") or config.mac_ssh_key.startswith("~"):
                key_path = os.path.expanduser(config.mac_ssh_key)
            else:
                # Base64 encoded key - write to temp file
                import base64
                import tempfile
                key_data = base64.b64decode(config.mac_ssh_key)
                with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
                    f.write(key_data)
                    key_path = f.name
                os.chmod(key_path, 0o600)
        
        connect_kwargs = {
            "host": ip,
            "username": config.mac_ssh_user,
            "known_hosts": None
        }
        
        if key_path:
            connect_kwargs["client_keys"] = [key_path]
        
        async with asyncssh.connect(**connect_kwargs) as conn:
            result = await conn.run(command, check=False)
            return result.exit_status == 0, result.stdout or result.stderr
            
    except Exception as e:
        log.error(f"SSH command failed: {e}")
        return False, str(e)

# ═══════════════════════════════════════════════════════════════════
# RECOVERY SCRIPTS
# ═══════════════════════════════════════════════════════════════════

RECOVERY_SCRIPTS = {
    "gateway": [
        "openclaw gateway restart",
        "launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway",
        "pkill -f 'openclaw gateway' && sleep 2 && openclaw gateway start"
    ],
    "minimax": [
        "pkill -f 'MiniMax Agent' && sleep 2 && open -a 'MiniMax Agent'",
    ],
    "caffeinate": [
        "pkill caffeinate; nohup caffeinate -dims &"
    ],
    "full_restart": [
        "openclaw gateway restart",
        "sleep 5",
        "pkill -f 'MiniMax Agent' && sleep 2 && open -a 'MiniMax Agent'"
    ]
}

async def run_recovery(target: str) -> Tuple[bool, str]:
    """Run recovery scripts for a specific target."""
    scripts = RECOVERY_SCRIPTS.get(target, [])
    if not scripts:
        return False, f"No recovery scripts for {target}"
    
    state.add_event("recovery", "vigil", f"Running {target} recovery scripts")
    
    for script in scripts:
        success, output = await ssh_command(script)
        if success:
            state.metrics.recovery_success += 1
            return True, f"Recovery successful: {script}"
    
    state.metrics.recovery_failed += 1
    return False, f"All recovery scripts failed for {target}"

async def restart_gateway() -> Tuple[bool, str]:
    """Restart OpenClaw gateway via SSH."""
    return await run_recovery("gateway")

async def restart_minimax() -> Tuple[bool, str]:
    """Restart MiniMax agent via SSH."""
    return await run_recovery("minimax")

# ═══════════════════════════════════════════════════════════════════
# BACKUP VERIFICATION
# ═══════════════════════════════════════════════════════════════════

async def check_backup_status() -> Tuple[bool, str]:
    """Check if recent backups exist."""
    success, output = await ssh_command(
        "ls -la ~/.openclaw/backups/*.json 2>/dev/null | tail -5"
    )
    
    if success and output.strip():
        state.backup_status = "ok"
        state.last_backup_check = datetime.now()
        return True, f"Backups found:\n{output}"
    
    state.backup_status = "missing"
    return False, "No backups found!"

async def run_diagnostics() -> str:
    """Run comprehensive system diagnostics."""
    results = []
    
    # Check Tailscale
    ts_ok, ts_latency = await tailscale_ping()
    results.append(f"Tailscale: {'✅' if ts_ok else '❌'} ({ts_latency:.0f}ms)")
    
    # Check gateway
    gw_ok, gw_out = await ssh_command("pgrep -l openclaw")
    results.append(f"Gateway: {'✅' if gw_ok else '❌'}")
    
    # Check MiniMax
    mm_ok, mm_out = await ssh_command("pgrep -l 'MiniMax Agent'")
    results.append(f"MiniMax: {'✅' if mm_ok else '❌'}")
    
    # Check caffeinate
    caf_ok, caf_out = await ssh_command("pgrep caffeinate")
    results.append(f"Caffeinate: {'✅' if caf_ok else '❌'}")
    
    # Check disk space
    disk_ok, disk_out = await ssh_command("df -h / | tail -1 | awk '{print $5}'")
    results.append(f"Disk usage: {disk_out.strip() if disk_ok else '❌'}")
    
    # Check backups
    bk_ok, bk_out = await check_backup_status()
    results.append(f"Backups: {'✅' if bk_ok else '❌'}")
    
    return "\n".join(results)

# ═══════════════════════════════════════════════════════════════════
# MAC AWAKE CHECK
# ═══════════════════════════════════════════════════════════════════

async def check_mac_awake() -> bool:
    """Check if Mac is responding to ping."""
    # Try Tailscale first
    success, _ = await tailscale_ping()
    if success:
        return True
    
    # Try direct IP
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
Tailscale IP: {config.mac_tailscale_ip}
Recovery attempts: {state.recovery_attempts}
Alert sent: {state.alert_sent}
Backup status: {state.backup_status}
"""
    
    # Build metrics
    metrics_text = f"""
Heartbeats received: {state.metrics.heartbeat_count}
Alerts sent: {state.metrics.alert_count}
Recovery success/fail: {state.metrics.recovery_success}/{state.metrics.recovery_failed}
Anomalies detected: {state.metrics.anomalies_detected}
"""
    
    # Build predictions
    prediction = predictor.predict_failure()
    predictions_text = prediction or "No issues predicted"
    
    # Build recent events summary
    recent = state.get_recent_events(24)
    events_text = "\n".join([
        f"- [{e.timestamp.strftime('%H:%M')}] {e.source}: {e.message}"
        for e in recent[-20:]  # Last 20 events
    ]) or "No recent events"
    
    prompt = SYSTEM_PROMPT.format(
        system_state=system_state,
        metrics=metrics_text,
        predictions=predictions_text,
        recent_events=events_text
    )
    
    # Try MiniMax first, fall back to OpenAI
    if config.minimax_api_key:
        return await call_minimax(prompt, user_message)
    elif config.openai_api_key:
        return await call_openai(prompt, user_message)
    else:
        return "⚠️ No AI API configured. Use slash commands: /status, /wake, /restart, /logs, /predict, /diag"

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
        
        # Execute any commands in response
        if "[WAKE]" in response:
            send_wol(config.mac_mac_address)
            response = response.replace("[WAKE]", "").strip()
            response += "\n\n✅ Wake-on-LAN sent"
        
        if "[RESTART]" in response:
            success, msg = await restart_gateway()
            response = response.replace("[RESTART]", "").strip()
            response += f"\n\n{'✅' if success else '❌'} Gateway: {msg}"
        
        if "[RESTART_MINIMAX]" in response:
            success, msg = await restart_minimax()
            response = response.replace("[RESTART_MINIMAX]", "").strip()
            response += f"\n\n{'✅' if success else '❌'} MiniMax: {msg}"
        
        if "[CHECK_BACKUP]" in response:
            success, msg = await check_backup_status()
            response = response.replace("[CHECK_BACKUP]", "").strip()
            response += f"\n\n{'✅' if success else '❌'} Backups: {msg}"
        
        if "[DIAGNOSTICS]" in response:
            diag = await run_diagnostics()
            response = response.replace("[DIAGNOSTICS]", "").strip()
            response += f"\n\n📊 Diagnostics:\n{diag}"
        
        if "[TAILSCALE_PING]" in response:
            success, latency = await tailscale_ping()
            response = response.replace("[TAILSCALE_PING]", "").strip()
            response += f"\n\n{'✅' if success else '❌'} Tailscale: {latency:.0f}ms"
        
        await self.send_message(f"🛡️ {response}")
    
    async def handle_command(self, cmd: str):
        """Handle slash commands."""
        cmd = cmd.lower().strip()
        
        if cmd == "/status":
            status = f"""🛡️ *VIGIL v4.0 STATUS*

*Jordan:* {state.jordan.status}
  Last seen: {state.jordan.last_seen or 'never'}

*MiniMax:* {state.minimax.status}
  Last seen: {state.minimax.last_seen or 'never'}

*Mac:* {'🟢 AWAKE' if state.mac_awake else '🔴 POSSIBLY ASLEEP'}
*Tailscale:* {config.mac_tailscale_ip}

*Metrics:*
  Heartbeats: {state.metrics.heartbeat_count}
  Anomalies: {state.metrics.anomalies_detected}
  Recoveries: {state.metrics.recovery_success}✅ {state.metrics.recovery_failed}❌

*Vigil:* 🟢 ONLINE
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
        
        elif cmd == "/predict":
            prediction = predictor.predict_failure()
            if prediction:
                await self.send_message(f"🔮 *Prediction:*\n\n{prediction}")
            else:
                await self.send_message("🔮 No issues predicted. Systems look stable.")
        
        elif cmd == "/diag":
            await self.send_message("🔍 Running diagnostics...")
            diag = await run_diagnostics()
            await self.send_message(f"📊 *Diagnostics:*\n\n```\n{diag}\n```")
        
        elif cmd == "/backup":
            success, msg = await check_backup_status()
            await self.send_message(f"{'✅' if success else '❌'} *Backup Status:*\n\n{msg}")
        
        elif cmd == "/ping":
            ts_ok, ts_lat = await tailscale_ping()
            await self.send_message(
                f"🏓 PONG — Vigil v4.0\n"
                f"Tailscale: {'✅' if ts_ok else '❌'} {ts_lat:.0f}ms"
            )
        
        elif cmd in ["/help", "/start"]:
            help_text = """🛡️ *VIGIL v4.0 — ENHANCED WATCHDOG*

*Commands:*
/status — System overview
/wake — Wake-on-LAN to Mac
/restart — Restart Jordan gateway
/logs — Recent events
/predict — Failure predictions
/diag — Full diagnostics
/backup — Check backup status
/ping — Connectivity test

*Natural Language:*
Just ask:
- "What happened last night?"
- "Run diagnostics"
- "Restart everything"
- "Is the system healthy?"

*Features v4.0:*
✅ Tailscale secure tunnel
✅ Predictive maintenance
✅ Multi-channel alerts
✅ Automated recovery

_I never sleep. I predict problems._
"""
            await self.send_message(help_text)
        
        else:
            await self.send_message(f"❓ Unknown: {cmd}\n\nSend /help")
    
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
        state.metrics.heartbeat_count += 1
        
        # Calculate interval for anomaly detection
        if source == "jordan" and state.jordan.last_seen:
            interval = (now - state.jordan.last_seen).total_seconds()
            predictor.record_heartbeat_interval(interval)
            is_anomaly, reason = predictor.detect_anomaly(interval)
            if is_anomaly:
                state.add_event("anomaly", source, reason)
        
        if source == "jordan":
            state.jordan.last_seen = now
            state.jordan.status = status
            state.jordan.details = details
            if "response_time" in details:
                state.jordan.response_times.append(details["response_time"])
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

async def handle_health(request):
    """Health check endpoint."""
    return web.json_response({
        "status": "ok",
        "version": "4.0",
        "jordan": state.jordan.status,
        "minimax": state.minimax.status,
        "uptime": state.metrics.heartbeat_count
    })

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
        
        # Check for predictions
        if config.enable_ml:
            prediction = predictor.predict_failure()
            if prediction and not state.alert_sent:
                state.add_event("prediction", "vigil", prediction)
                await bot.send_message(f"🔮 *Predictive Alert:*\n\n{prediction}")
        
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
                await alerts.send_alert(
                    f"Jordan is DOWN and Mac appears to be ASLEEP!\n\n"
                    f"Last heartbeat: {state.jordan.last_seen or 'never'}\n\n"
                    f"Attempting Wake-on-LAN...",
                    level="critical"
                )
                send_wol(config.mac_mac_address)
                state.recovery_attempts += 1
            else:
                # Mac is awake but Jordan is down - try restart
                await alerts.send_alert(
                    f"Jordan is DOWN but Mac is AWAKE!\n\n"
                    f"Last heartbeat: {state.jordan.last_seen or 'never'}\n\n"
                    f"Attempting service restart...",
                    level="warning"
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
    log.info("═" * 50)
    log.info("VIGIL v4.0 — ENHANCED EXTERNAL SMART WATCHDOG")
    log.info("═" * 50)
    log.info("DVOL v31.1 ACTIVE")
    log.info(f"Monitoring Mac at {config.mac_ip} / {config.mac_tailscale_ip}")
    log.info(f"Predictive maintenance: {'ENABLED' if config.enable_ml else 'DISABLED'}")
    
    # Create data directory
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)
    
    # Start heartbeat HTTP server
    app = web.Application()
    app.router.add_post("/heartbeat", handle_heartbeat)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)  # Root also returns health
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.heartbeat_port)
    await site.start()
    log.info(f"Heartbeat server listening on port {config.heartbeat_port}")
    
    # Send startup message
    await bot.send_message(
        "🛡️ *VIGIL v4.0 ONLINE*\n\n"
        "Enhanced external watchdog active.\n"
        "DVOL v31.1 integrated.\n\n"
        "✅ Tailscale integration\n"
        "✅ Predictive maintenance\n"
        "✅ Multi-channel alerts\n"
        "✅ Automated recovery\n\n"
        f"📡 Monitoring: `{config.mac_ip}`\n"
        f"🔒 Tailscale: `{config.mac_tailscale_ip}`\n"
        f"⏱️ Timeout: {config.heartbeat_timeout}s\n\n"
        "_I never sleep. I predict problems._"
    )
    state.add_event("startup", "vigil", "Vigil v4.0 started with enhanced capabilities")
    
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
