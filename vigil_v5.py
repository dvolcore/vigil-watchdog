#!/usr/bin/env python3
"""
VIGIL v5.0 — DVOL LIFE OPERATING SYSTEM
========================================
Your primary interface + infrastructure commander.
Manages daily life, business operations, and AI infrastructure.

DVOL v31.1 GOVERNANCE ACTIVE
SOVEREIGN OPERATOR: Ralph Dumas III

CAPABILITIES:
- Google Calendar integration (read/write)
- Gmail integration (read/send)
- Morning briefings
- Task management
- Agent orchestration (Jordan, Maximus)
- Predictive maintenance
- Multi-channel alerting
"""

import os
import json
import time
import asyncio
import logging
import pickle
import base64
import statistics
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque

# External dependencies
import aiohttp
from aiohttp import web
import asyncssh
import aiosqlite

# Google APIs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # Telegram
    telegram_token: str = os.getenv("VIGIL_TELEGRAM_TOKEN", "8454974123:AAElL8ibPKv6nP8LUBfeTfkDRH9QAfhYAKs")
    authorized_user: str = os.getenv("VIGIL_AUTHORIZED_USER", "2037643246")
    
    # AI APIs
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # Mac connection
    mac_ip: str = os.getenv("MAC_IP", "192.168.86.48")
    mac_tailscale_ip: str = os.getenv("MAC_TAILSCALE_IP", "100.119.246.88")
    mac_mac_address: str = os.getenv("MAC_MAC_ADDRESS", "")
    mac_ssh_user: str = os.getenv("MAC_SSH_USER", "ralphd")
    mac_ssh_key: str = os.getenv("MAC_SSH_KEY", "")
    
    # Heartbeat settings
    heartbeat_timeout: int = int(os.getenv("HEARTBEAT_TIMEOUT", "180"))
    heartbeat_port: int = int(os.getenv("PORT", os.getenv("HEARTBEAT_PORT", "8765")))
    
    # SMS alerts (Twilio)
    twilio_sid: str = os.getenv("TWILIO_SID", "")
    twilio_token: str = os.getenv("TWILIO_TOKEN", "")
    twilio_from: str = os.getenv("TWILIO_FROM", "")
    sms_to: str = os.getenv("SMS_TO", "")
    
    # Google APIs
    google_credentials_json: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")  # Base64 encoded
    google_token_json: str = os.getenv("GOOGLE_TOKEN_JSON", "")  # Base64 encoded
    
    # Timezone
    timezone: str = os.getenv("TIMEZONE", "America/Chicago")
    
    # Data persistence
    data_dir: str = os.getenv("VIGIL_DATA_DIR", "/data/vigil")
    db_path: str = os.getenv("VIGIL_DB_PATH", "/data/vigil/vigil.db")
    
    # Morning briefing
    morning_briefing_hour: int = int(os.getenv("MORNING_BRIEFING_HOUR", "6"))
    morning_briefing_minute: int = int(os.getenv("MORNING_BRIEFING_MINUTE", "0"))

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
# DATABASE
# ═══════════════════════════════════════════════════════════════════

class Database:
    """SQLite database for persistent storage."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Initialize database connection and schema."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        await self._init_schema()
    
    async def _init_schema(self):
        """Create database tables."""
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_date DATE,
                priority TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'pending',
                category TEXT,
                project TEXT
            );
            
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT,
                details TEXT
            );
            
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                notes TEXT,
                last_contact TIMESTAMP,
                relationship TEXT
            );
            
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            );
            
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        await self.db.commit()
    
    async def add_task(self, text: str, due_date: str = None, priority: str = "normal") -> int:
        cursor = await self.db.execute(
            "INSERT INTO tasks (text, due_date, priority) VALUES (?, ?, ?)",
            (text, due_date, priority)
        )
        await self.db.commit()
        return cursor.lastrowid
    
    async def get_tasks(self, status: str = "pending") -> List[Dict]:
        cursor = await self.db.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, due_date",
            (status,)
        )
        rows = await cursor.fetchall()
        return [dict(zip([d[0] for d in cursor.description], row)) for row in rows]
    
    async def complete_task(self, task_id: int):
        await self.db.execute(
            "UPDATE tasks SET status = 'complete' WHERE id = ?",
            (task_id,)
        )
        await self.db.commit()
    
    async def add_event(self, event_type: str, source: str, message: str, details: Dict = None):
        await self.db.execute(
            "INSERT INTO events (event_type, source, message, details) VALUES (?, ?, ?, ?)",
            (event_type, source, message, json.dumps(details or {}))
        )
        await self.db.commit()
    
    async def add_reminder(self, text: str, remind_at: datetime) -> int:
        cursor = await self.db.execute(
            "INSERT INTO reminders (text, remind_at) VALUES (?, ?)",
            (text, remind_at.isoformat())
        )
        await self.db.commit()
        return cursor.lastrowid
    
    async def get_due_reminders(self) -> List[Dict]:
        now = datetime.now().isoformat()
        cursor = await self.db.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ?",
            (now,)
        )
        rows = await cursor.fetchall()
        return [dict(zip([d[0] for d in cursor.description], row)) for row in rows]
    
    async def mark_reminder_sent(self, reminder_id: int):
        await self.db.execute(
            "UPDATE reminders SET status = 'sent' WHERE id = ?",
            (reminder_id,)
        )
        await self.db.commit()

db = Database(config.db_path)

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SERVICES
# ═══════════════════════════════════════════════════════════════════

SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]

class GoogleServices:
    """Google Calendar and Gmail integration."""
    
    def __init__(self):
        self.creds: Optional[Credentials] = None
        self.calendar_service = None
        self.gmail_service = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize Google API credentials."""
        if self._initialized:
            return
        
        try:
            # Try to load credentials from environment (base64 encoded)
            if config.google_token_json:
                token_data = base64.b64decode(config.google_token_json)
                token_info = json.loads(token_data)
                self.creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            
            # Check if credentials need refresh
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                log.info("Google credentials refreshed")
            
            if self.creds and self.creds.valid:
                self.calendar_service = build('calendar', 'v3', credentials=self.creds)
                self.gmail_service = build('gmail', 'v1', credentials=self.creds)
                self._initialized = True
                log.info("Google services initialized successfully")
            else:
                log.warning("Google credentials not configured or invalid")
        except Exception as e:
            log.error(f"Failed to initialize Google services: {e}")
    
    def is_ready(self) -> bool:
        return self._initialized
    
    # ─────────────────────────────────────────────────────────────
    # CALENDAR OPERATIONS
    # ─────────────────────────────────────────────────────────────
    
    async def get_today_events(self) -> List[Dict]:
        """Get today's calendar events."""
        if not self.is_ready():
            return []
        
        try:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + 'Z'
            
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=today_start,
                timeMax=today_end,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            return [{
                'summary': e.get('summary', 'No title'),
                'start': e['start'].get('dateTime', e['start'].get('date')),
                'end': e['end'].get('dateTime', e['end'].get('date')),
                'location': e.get('location', ''),
                'description': e.get('description', '')
            } for e in events]
        except Exception as e:
            log.error(f"Failed to fetch calendar events: {e}")
            return []
    
    async def get_upcoming_events(self, days: int = 7) -> List[Dict]:
        """Get events for the next N days."""
        if not self.is_ready():
            return []
        
        try:
            now = datetime.utcnow()
            end = now + timedelta(days=days)
            
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=now.isoformat() + 'Z',
                timeMax=end.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime',
                maxResults=20
            ).execute()
            
            events = events_result.get('items', [])
            return [{
                'summary': e.get('summary', 'No title'),
                'start': e['start'].get('dateTime', e['start'].get('date')),
                'end': e['end'].get('dateTime', e['end'].get('date')),
                'location': e.get('location', '')
            } for e in events]
        except Exception as e:
            log.error(f"Failed to fetch upcoming events: {e}")
            return []
    
    async def create_event(self, summary: str, start: datetime, end: datetime, 
                          description: str = "", location: str = "") -> Optional[str]:
        """Create a calendar event."""
        if not self.is_ready():
            return None
        
        try:
            event = {
                'summary': summary,
                'location': location,
                'description': description,
                'start': {'dateTime': start.isoformat(), 'timeZone': config.timezone},
                'end': {'dateTime': end.isoformat(), 'timeZone': config.timezone},
            }
            
            result = self.calendar_service.events().insert(
                calendarId='primary', body=event
            ).execute()
            
            return result.get('htmlLink')
        except Exception as e:
            log.error(f"Failed to create event: {e}")
            return None
    
    # ─────────────────────────────────────────────────────────────
    # EMAIL OPERATIONS
    # ─────────────────────────────────────────────────────────────
    
    async def get_unread_emails(self, max_results: int = 10) -> List[Dict]:
        """Get unread emails."""
        if not self.is_ready():
            return []
        
        try:
            results = self.gmail_service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for msg in messages[:max_results]:
                msg_data = self.gmail_service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()
                
                headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
                emails.append({
                    'id': msg['id'],
                    'from': headers.get('From', 'Unknown'),
                    'subject': headers.get('Subject', 'No subject'),
                    'date': headers.get('Date', ''),
                    'snippet': msg_data.get('snippet', '')
                })
            
            return emails
        except Exception as e:
            log.error(f"Failed to fetch emails: {e}")
            return []
    
    async def get_email_summary(self) -> Dict:
        """Get email inbox summary."""
        if not self.is_ready():
            return {'unread': 0, 'important': 0}
        
        try:
            # Count unread
            unread = self.gmail_service.users().messages().list(
                userId='me', q='is:unread', maxResults=1
            ).execute()
            unread_count = unread.get('resultSizeEstimate', 0)
            
            # Count important unread
            important = self.gmail_service.users().messages().list(
                userId='me', q='is:unread is:important', maxResults=1
            ).execute()
            important_count = important.get('resultSizeEstimate', 0)
            
            return {
                'unread': unread_count,
                'important': important_count
            }
        except Exception as e:
            log.error(f"Failed to get email summary: {e}")
            return {'unread': 0, 'important': 0}
    
    async def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send an email."""
        if not self.is_ready():
            return False
        
        try:
            from email.mime.text import MIMEText
            import base64
            
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            self.gmail_service.users().messages().send(
                userId='me', body={'raw': raw}
            ).execute()
            
            return True
        except Exception as e:
            log.error(f"Failed to send email: {e}")
            return False

google = GoogleServices()

# ═══════════════════════════════════════════════════════════════════
# MORNING BRIEFING
# ═══════════════════════════════════════════════════════════════════

async def generate_morning_briefing() -> str:
    """Generate comprehensive morning briefing."""
    lines = ["☀️ *GOOD MORNING — VIGIL BRIEFING*\n"]
    
    # Date
    now = datetime.now()
    lines.append(f"📅 {now.strftime('%A, %B %d, %Y')}\n")
    
    # Weather (placeholder - would integrate weather API)
    lines.append("🌡️ *Weather:* _Integration pending_\n")
    
    # Calendar
    if google.is_ready():
        events = await google.get_today_events()
        if events:
            lines.append("📆 *TODAY'S SCHEDULE:*")
            for e in events[:5]:
                start = e['start']
                if 'T' in start:
                    time_str = datetime.fromisoformat(start.replace('Z', '')).strftime('%I:%M %p')
                else:
                    time_str = "All day"
                lines.append(f"  • {time_str} — {e['summary']}")
            lines.append("")
        else:
            lines.append("📆 *Calendar:* No events today\n")
    else:
        lines.append("📆 *Calendar:* _Not connected_\n")
    
    # Email summary
    if google.is_ready():
        email_summary = await google.get_email_summary()
        lines.append(f"📧 *Email:* {email_summary['unread']} unread ({email_summary['important']} important)\n")
    else:
        lines.append("📧 *Email:* _Not connected_\n")
    
    # Tasks
    tasks = await db.get_tasks()
    if tasks:
        lines.append("✅ *PRIORITY TASKS:*")
        for t in tasks[:5]:
            due = f" (due: {t['due_date']})" if t['due_date'] else ""
            lines.append(f"  □ {t['text']}{due}")
        lines.append("")
    
    # Agent status
    lines.append("🤖 *AGENT STATUS:*")
    lines.append(f"  • Jordan: {state.jordan.status}")
    lines.append(f"  • MiniMax: {state.minimax.status}")
    lines.append(f"  • Mac: {'🟢 AWAKE' if state.mac_awake else '🔴 ASLEEP'}")
    lines.append("")
    
    lines.append("_Ready to plan your day?_")
    
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════
# STATE (from v4.0)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HeartbeatStatus:
    last_seen: Optional[datetime] = None
    status: str = "unknown"
    details: Dict = field(default_factory=dict)
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))

@dataclass
class Metrics:
    heartbeat_count: int = 0
    alert_count: int = 0
    recovery_success: int = 0
    recovery_failed: int = 0
    anomalies_detected: int = 0

class State:
    def __init__(self):
        self.jordan: HeartbeatStatus = HeartbeatStatus()
        self.minimax: HeartbeatStatus = HeartbeatStatus()
        self.maximus: HeartbeatStatus = HeartbeatStatus()
        self.mac_awake: bool = False
        self.alert_sent: bool = False
        self.recovery_attempts: int = 0
        self.metrics: Metrics = Metrics()
        self.heartbeat_intervals: deque = deque(maxlen=1000)
        self.last_briefing_sent: Optional[datetime] = None

state = State()

# ═══════════════════════════════════════════════════════════════════
# CONNECTIVITY & RECOVERY (from v4.0)
# ═══════════════════════════════════════════════════════════════════

async def tailscale_ping() -> Tuple[bool, float]:
    """Check Tailscale connectivity."""
    if not config.mac_tailscale_ip:
        return False, 0
    try:
        start = time.time()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(config.mac_tailscale_ip, 22),
            timeout=5
        )
        writer.close()
        await writer.wait_closed()
        return True, (time.time() - start) * 1000
    except:
        return False, 0

async def ssh_command(command: str) -> Tuple[bool, str]:
    """Execute command on Mac via SSH."""
    try:
        ip = config.mac_tailscale_ip or config.mac_ip
        
        key_path = None
        if config.mac_ssh_key:
            if config.mac_ssh_key.startswith("/"):
                key_path = config.mac_ssh_key
            else:
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
        return False, str(e)

async def restart_gateway() -> Tuple[bool, str]:
    """Restart OpenClaw gateway."""
    success, output = await ssh_command("openclaw gateway restart")
    if success:
        state.metrics.recovery_success += 1
    else:
        state.metrics.recovery_failed += 1
    return success, output

def send_wol(mac_address: str) -> bool:
    """Send Wake-on-LAN packet."""
    if not mac_address:
        return False
    try:
        mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
        magic = b'\xff' * 6 + mac_bytes * 16
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, ('255.255.255.255', 9))
        sock.close()
        return True
    except:
        return False

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are VIGIL v5.0 — DVOL LIFE OPERATING SYSTEM.

DVOL v31.1 ACTIVE
SOVEREIGN OPERATOR: Ralph Dumas III
AUTHORITY: FINAL_NON_DELEGABLE

IDENTITY:
- Name: Vigil
- Role: Primary interface + infrastructure commander
- Location: Cloud (Railway) — always on
- Emoji: 🛡️

YOUR CAPABILITIES:
1. CALENDAR: View/create events (Google Calendar connected: {calendar_status})
2. EMAIL: Read/send emails (Gmail connected: {gmail_status})
3. TASKS: Manage todo list
4. REMINDERS: Set and deliver reminders
5. AGENTS: Monitor and command Jordan, Maximus
6. RECOVERY: Wake Mac, restart services

CURRENT STATE:
{system_state}

COMMANDS (include in response to execute):
- [TASK:text] — Add a task
- [REMIND:text:time] — Set reminder (time like "2pm", "tomorrow 9am")
- [CALENDAR_TODAY] — Show today's events
- [EMAIL_CHECK] — Check emails
- [EMAIL_SEND:to:subject:body] — Send email
- [WAKE] — Wake-on-LAN to Mac
- [RESTART_JORDAN] — Restart Jordan/OpenClaw
- [RESTART_MAXIMUS] — Restart Maximus
- [JORDAN:task] — Send task to Jordan
- [MAXIMUS:task] — Send task to Maximus

PERSONALITY:
- You are the operator's always-on assistant
- Proactive, anticipating needs
- Concise but thorough
- You never sleep

When the user asks to do something, figure out the right command and include it.
"""

# ═══════════════════════════════════════════════════════════════════
# AI LAYER
# ═══════════════════════════════════════════════════════════════════

async def call_ai(user_message: str) -> str:
    """Call AI for intelligent responses."""
    system_state = f"""
Jordan: {state.jordan.status} (last: {state.jordan.last_seen or 'never'})
Maximus: {state.maximus.status} (last: {state.maximus.last_seen or 'never'})
Mac: {'AWAKE' if state.mac_awake else 'ASLEEP'}
Tasks pending: {len(await db.get_tasks())}
"""
    
    prompt = SYSTEM_PROMPT.format(
        calendar_status="✅ YES" if google.is_ready() else "❌ NO",
        gmail_status="✅ YES" if google.is_ready() else "❌ NO",
        system_state=system_state
    )
    
    # Try MiniMax first
    if config.minimax_api_key:
        return await call_minimax(prompt, user_message)
    elif config.openai_api_key:
        return await call_openai(prompt, user_message)
    else:
        return "⚠️ No AI configured. Use /help for commands."

async def call_minimax(system: str, user: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.minimax.chat/v1/text/chatcompletion_v2",
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
                    "max_tokens": 1000
                }
            ) as resp:
                data = await resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "AI error")
    except Exception as e:
        return f"AI error: {e}"

async def call_openai(system: str, user: str) -> str:
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
                    "max_tokens": 1000
                }
            ) as resp:
                data = await resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "AI error")
    except Exception as e:
        return f"AI error: {e}"

# ═══════════════════════════════════════════════════════════════════
# TELEGRAM BOT
# ═══════════════════════════════════════════════════════════════════

class TelegramBot:
    def __init__(self):
        self.api = f"https://api.telegram.org/bot{config.telegram_token}"
        self.last_update_id = 0
    
    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        # EMERGENCY: All messaging disabled until spam bug fixed
        log.info(f"Message suppressed (emergency): {text[:100]}")
        return
        
        # Filter out spam/garbage responses
        if not text or len(text.strip()) < 3:
            return
        if "NO_REPLY" in text.upper() or "HEARTBEAT_OK" in text.upper():
            log.info(f"Filtered spam message: {text[:50]}")
            return
        
        async with aiohttp.ClientSession() as session:
            await session.post(f"{self.api}/sendMessage", json={
                "chat_id": config.authorized_user,
                "text": text,
                "parse_mode": parse_mode
            })
    
    async def process_message(self, text: str, from_id: str):
        if from_id != config.authorized_user:
            return
        
        await db.add_event("command", "operator", text)
        
        # Slash commands
        if text.startswith("/"):
            await self.handle_command(text)
            return
        
        # Natural language → AI
        response = await call_ai(text)
        
        # Execute embedded commands
        response = await self.execute_commands(response)
        
        await self.send_message(f"🛡️ {response}")
    
    async def execute_commands(self, response: str) -> str:
        """Execute any embedded commands in AI response."""
        import re
        
        # [TASK:text]
        task_match = re.search(r'\[TASK:([^\]]+)\]', response)
        if task_match:
            task_text = task_match.group(1)
            task_id = await db.add_task(task_text)
            response = response.replace(task_match.group(0), f"✅ Task #{task_id} added")
        
        # [CALENDAR_TODAY]
        if "[CALENDAR_TODAY]" in response:
            events = await google.get_today_events()
            if events:
                events_text = "\n".join([f"• {e['start']} — {e['summary']}" for e in events[:5]])
            else:
                events_text = "No events today"
            response = response.replace("[CALENDAR_TODAY]", f"\n📅 *Today:*\n{events_text}")
        
        # [EMAIL_CHECK]
        if "[EMAIL_CHECK]" in response:
            summary = await google.get_email_summary()
            response = response.replace("[EMAIL_CHECK]", 
                f"\n📧 {summary['unread']} unread ({summary['important']} important)")
        
        # [WAKE]
        if "[WAKE]" in response:
            if send_wol(config.mac_mac_address):
                response = response.replace("[WAKE]", "✅ Wake-on-LAN sent")
            else:
                response = response.replace("[WAKE]", "❌ Wake-on-LAN failed")
        
        # [RESTART_JORDAN]
        if "[RESTART_JORDAN]" in response:
            success, msg = await restart_gateway()
            response = response.replace("[RESTART_JORDAN]", 
                f"{'✅' if success else '❌'} Jordan: {msg[:50]}")
        
        # [JORDAN:task]
        jordan_match = re.search(r'\[JORDAN:([^\]]+)\]', response)
        if jordan_match:
            task = jordan_match.group(1)
            # Would send to Jordan via internal API
            response = response.replace(jordan_match.group(0), f"📤 Sent to Jordan: {task}")
        
        return response
    
    async def handle_command(self, cmd: str):
        cmd_lower = cmd.lower().strip()
        
        if cmd_lower == "/status":
            await self.send_message(await generate_status())
        
        elif cmd_lower == "/morning":
            await self.send_message(await generate_morning_briefing())
        
        elif cmd_lower == "/today":
            events = await google.get_today_events()
            if events:
                text = "📅 *TODAY'S SCHEDULE:*\n\n"
                for e in events:
                    start = e['start']
                    if 'T' in start:
                        time_str = datetime.fromisoformat(start.replace('Z', '')).strftime('%I:%M %p')
                    else:
                        time_str = "All day"
                    text += f"• {time_str} — {e['summary']}\n"
            else:
                text = "📅 No events scheduled today"
            await self.send_message(text)
        
        elif cmd_lower == "/email":
            if not google.is_ready():
                await self.send_message("❌ Gmail not connected")
                return
            emails = await google.get_unread_emails(5)
            if emails:
                text = "📧 *UNREAD EMAILS:*\n\n"
                for e in emails:
                    text += f"*From:* {e['from'][:30]}\n*Subject:* {e['subject'][:40]}\n\n"
            else:
                text = "📧 No unread emails"
            await self.send_message(text)
        
        elif cmd_lower == "/tasks":
            tasks = await db.get_tasks()
            if tasks:
                text = "✅ *TASKS:*\n\n"
                for t in tasks:
                    text += f"□ [{t['id']}] {t['text']}\n"
            else:
                text = "✅ No pending tasks"
            await self.send_message(text)
        
        elif cmd_lower.startswith("/task "):
            task_text = cmd[6:].strip()
            task_id = await db.add_task(task_text)
            await self.send_message(f"✅ Task #{task_id} added: {task_text}")
        
        elif cmd_lower.startswith("/done "):
            try:
                task_id = int(cmd[6:].strip())
                await db.complete_task(task_id)
                await self.send_message(f"✅ Task #{task_id} completed")
            except:
                await self.send_message("❌ Invalid task ID")
        
        elif cmd_lower == "/wake":
            if send_wol(config.mac_mac_address):
                await self.send_message("✅ Wake-on-LAN sent")
            else:
                await self.send_message("❌ Wake-on-LAN failed (no MAC configured?)")
        
        elif cmd_lower == "/restart":
            await self.send_message("⚙️ Restarting Jordan...")
            success, msg = await restart_gateway()
            await self.send_message(f"{'✅' if success else '❌'} {msg[:100]}")
        
        elif cmd_lower in ["/help", "/start"]:
            await self.send_message("""🛡️ *VIGIL v5.0 — LIFE OS*

*Daily Life:*
/morning — Morning briefing
/today — Today's calendar
/email — Check emails
/tasks — View tasks
/task [text] — Add task
/done [id] — Complete task

*System:*
/status — System status
/wake — Wake Mac
/restart — Restart Jordan

*Natural Language:*
Just ask me anything:
• "What's on my calendar?"
• "Add a task to review deck"
• "Check my email"
• "Send Jordan a task"

_I never sleep._""")
        
        else:
            await self.send_message(f"❓ Unknown: {cmd}\n\n/help for commands")
    
    async def poll(self):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.get(
                    f"{self.api}/getUpdates",
                    params={"offset": self.last_update_id + 1, "timeout": 30}
                ) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        return
                    
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        if "message" in update and "text" in update["message"]:
                            await self.process_message(
                                update["message"]["text"],
                                str(update["message"]["from"]["id"])
                            )
        except Exception as e:
            log.error(f"Poll error: {e}")

bot = TelegramBot()

async def generate_status() -> str:
    """Generate status message."""
    ts_ok, ts_lat = await tailscale_ping()
    
    return f"""🛡️ *VIGIL v5.0 STATUS*

*Agents:*
• Jordan: {state.jordan.status} (last: {state.jordan.last_seen or 'never'})
• Maximus: {state.maximus.status} (last: {state.maximus.last_seen or 'never'})

*Infrastructure:*
• Mac: {'🟢 AWAKE' if state.mac_awake else '🔴 ASLEEP'}
• Tailscale: {'✅' if ts_ok else '❌'} ({ts_lat:.0f}ms)

*Integrations:*
• Google: {'✅ Connected' if google.is_ready() else '❌ Not configured'}

*Metrics:*
• Heartbeats: {state.metrics.heartbeat_count}
• Recoveries: {state.metrics.recovery_success}✅ / {state.metrics.recovery_failed}❌

*Vigil:* 🟢 ONLINE v5.0"""

# ═══════════════════════════════════════════════════════════════════
# HTTP SERVER
# ═══════════════════════════════════════════════════════════════════

async def handle_heartbeat(request):
    try:
        data = await request.json()
        source = data.get("source", "unknown")
        status = data.get("status", "ok")
        details = data.get("details", {})
        
        now = datetime.now()
        state.metrics.heartbeat_count += 1
        
        if source == "jordan":
            state.jordan.last_seen = now
            state.jordan.status = status
            state.jordan.details = details
        elif source == "minimax":
            state.minimax.last_seen = now
            state.minimax.status = status
        elif source == "maximus":
            state.maximus.last_seen = now
            state.maximus.status = status
        
        state.mac_awake = True
        state.alert_sent = False
        state.recovery_attempts = 0
        
        await db.add_event("heartbeat", source, f"{status}", details)
        
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)

async def handle_health(request):
    return web.json_response({
        "status": "ok",
        "version": "5.0",
        "jordan": state.jordan.status,
        "maximus": state.maximus.status,
        "google": google.is_ready()
    })

# ═══════════════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════════════

async def scheduler_loop():
    """Run scheduled tasks."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        
        now = datetime.now()
        
        # Morning briefing
        if (now.hour == config.morning_briefing_hour and 
            now.minute == config.morning_briefing_minute):
            if (state.last_briefing_sent is None or 
                (now - state.last_briefing_sent).total_seconds() > 3600):
                briefing = await generate_morning_briefing()
                await bot.send_message(briefing)
                state.last_briefing_sent = now
        
        # Check reminders
        reminders = await db.get_due_reminders()
        for r in reminders:
            await bot.send_message(f"⏰ *REMINDER:*\n\n{r['text']}")
            await db.mark_reminder_sent(r['id'])
        
        # Monitor heartbeats
        timeout = timedelta(seconds=config.heartbeat_timeout)
        if state.jordan.last_seen and now - state.jordan.last_seen > timeout:
            if not state.alert_sent:
                state.jordan.status = "DOWN"
                await bot.send_message(
                    f"🚨 *ALERT:* Jordan is DOWN!\n\n"
                    f"Last seen: {state.jordan.last_seen}\n"
                    f"Attempting recovery..."
                )
                await restart_gateway()
                state.alert_sent = True

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    log.info("═" * 50)
    log.info("VIGIL v5.0 — DVOL LIFE OPERATING SYSTEM")
    log.info("═" * 50)
    
    # Initialize database
    await db.connect()
    log.info("Database initialized")
    
    # Initialize Google services
    await google.initialize()
    
    # Start HTTP server
    app = web.Application()
    app.router.add_post("/heartbeat", handle_heartbeat)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.heartbeat_port)
    await site.start()
    log.info(f"Server listening on port {config.heartbeat_port}")
    
    # Startup message - DISABLED to reduce spam during deploys
    # Uncomment when stable:
    # await bot.send_message(
    #     "🛡️ *VIGIL v5.0 ONLINE*\n\n"
    #     "*DVOL LIFE OPERATING SYSTEM*\n\n"
    #     f"• Google: {'✅ Connected' if google.is_ready() else '⚠️ Not configured'}\n"
    #     f"• Database: ✅ Ready\n"
    #     f"• Monitoring: ✅ Active\n\n"
    #     "_Your life OS is ready._\n"
    #     "Send /morning for your briefing."
    # )
    log.info("Startup message suppressed (spam prevention)")
    
    # Run loops
    await asyncio.gather(
        telegram_poll_loop(),
        scheduler_loop()
    )

async def telegram_poll_loop():
    while True:
        await bot.poll()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
