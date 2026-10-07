"""
Database setup for Phantom TG Harvester.
Supports dual-layer persistence:
1. Fast local SQLite engine for zero-latency operations & Telethon compatibility.
2. Cloud sync with Supabase PostgreSQL for multi-tenant, cloud-persistent deployment (Render/Vercel).
"""

import aiosqlite
import os
import json
import base64
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phantom_harvester.db")
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_supabase_client = None


def get_supabase_client():
    """Get or initialize Supabase client if configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    
    url = os.getenv("SUPABASE_URL", SUPABASE_URL)
    key = os.getenv("SUPABASE_KEY", SUPABASE_KEY)
    
    if url and key:
        try:
            from supabase import create_client
            _supabase_client = create_client(url, key)
            return _supabase_client
        except Exception as e:
            print(f"[Supabase] Init error: {e}")
            return None
    return None


async def get_db():
    """Get local database connection."""
    db = await aiosqlite.connect(DB_PATH, timeout=30.0)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Initialize database tables and sync cloud state."""
    db = await aiosqlite.connect(DB_PATH, timeout=30.0)
    
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            session_file TEXT,
            proxy_type TEXT,
            proxy_host TEXT,
            proxy_port INTEGER,
            proxy_username TEXT,
            proxy_password TEXT,
            status TEXT DEFAULT 'inactive',
            messages_sent_today INTEGER DEFAULT 0,
            invites_sent_today INTEGER DEFAULT 0,
            last_used TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            flood_wait_until TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS parsed_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            source_chat TEXT,
            last_online TIMESTAMP,
            is_active_writer INTEGER DEFAULT 0,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS send_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            send_type TEXT DEFAULT 'users',
            repeat_interval INTEGER DEFAULT 0,
            targets_file TEXT,
            message_text TEXT NOT NULL,
            media_path TEXT,
            spintax_enabled INTEGER DEFAULT 0,
            messages_per_account INTEGER DEFAULT 35,
            delay_min INTEGER DEFAULT 45,
            delay_max INTEGER DEFAULT 120,
            status TEXT DEFAULT 'pending',
            total_sent INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            auto_responder_enabled INTEGER DEFAULT 0,
            auto_responder_keywords TEXT DEFAULT '[]',
            forward_to_account TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS invite_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_chat TEXT NOT NULL,
            invites_per_account INTEGER DEFAULT 15,
            delay_min INTEGER DEFAULT 30,
            delay_max INTEGER DEFAULT 60,
            status TEXT DEFAULT 'pending',
            total_invited INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS event_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT DEFAULT 'info',
            source TEXT,
            message TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            sent_total INTEGER DEFAULT 0,
            invited_total INTEGER DEFAULT 0,
            failed_total INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tiktok_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            cookie_data TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tiktok_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_path TEXT,
            description TEXT,
            status TEXT DEFAULT 'pending',
            total_accounts INTEGER,
            posted_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS license_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'active',
            activated_at TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Ensure today's stats row exists
    today = datetime.now().strftime("%Y-%m-%d")
    await db.execute(
        "INSERT OR IGNORE INTO daily_stats (date) VALUES (?)",
        (today,)
    )
    
    await db.commit()
    await db.close()

    # Cloud sync with Supabase (await hydration before serving traffic)
    try:
        await sync_from_supabase()
    except Exception as e:
        print(f"[Supabase] Startup sync error: {e}")


async def sync_from_supabase():
    """Pull persisted settings, accounts, and session binaries from Supabase."""
    sb = get_supabase_client()
    if not sb:
        return

    try:
        # 1. Sync Settings
        try:
            res = sb.table("settings").select("*").execute()
            if res.data:
                db = await get_db()
                for item in res.data:
                    k, v = item.get("key"), str(item.get("value", ""))
                    if k == "api_id":
                        os.environ["TG_API_ID"] = v
                    elif k == "api_hash":
                        os.environ["TG_API_HASH"] = v
                    await db.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (k, v)
                    )
                await db.commit()
                await db.close()
                print(f"[Supabase] Restored {len(res.data)} settings from cloud")
        except Exception as e:
            print(f"[Supabase] Settings sync note: {e}")

        # 2. Sync License Keys
        try:
            res = sb.table("license_keys").select("*").execute()
            if res.data:
                db = await get_db()
                for k in res.data:
                    await db.execute(
                        "INSERT OR IGNORE INTO license_keys (key, status, activated_at, expires_at, note) VALUES (?, ?, ?, ?, ?)",
                        (k.get("key"), k.get("status", "active"), k.get("activated_at"), k.get("expires_at"), k.get("note", ""))
                    )
                await db.commit()
                await db.close()
        except Exception as e:
            pass

        # 3. Sync Accounts and Restore .session files
        try:
            res = sb.table("accounts").select("*").execute()
            if res.data:
                db = await get_db()
                restored_sessions = 0
                for acc in res.data:
                    phone = acc.get("phone")
                    session_file = acc.get("session_file") or f"{phone.replace('+', '')}.session"
                    
                    # Restore session file binary if stored in base64
                    session_b64 = acc.get("session_data")
                    if session_b64:
                        target_path = os.path.join(SESSIONS_DIR, session_file)
                        if not os.path.exists(target_path):
                            try:
                                with open(target_path, "wb") as sf:
                                    sf.write(base64.b64decode(session_b64))
                                restored_sessions += 1
                            except Exception as write_err:
                                print(f"[Supabase] Error writing session file {session_file}: {write_err}")

                    # Upsert into local SQLite
                    cursor = await db.execute("SELECT id FROM accounts WHERE phone = ?", (phone,))
                    existing = await cursor.fetchone()
                    if existing:
                        await db.execute(
                            """UPDATE accounts SET 
                                session_file = ?, proxy_type = ?, proxy_host = ?, proxy_port = ?,
                                proxy_username = ?, proxy_password = ?, status = ?
                               WHERE id = ?""",
                            (
                                session_file, acc.get("proxy_type"), acc.get("proxy_host"),
                                acc.get("proxy_port"), acc.get("proxy_username"),
                                acc.get("proxy_password"), acc.get("status", "active"),
                                existing[0]
                            )
                        )
                    else:
                        await db.execute(
                            """INSERT INTO accounts 
                                (phone, session_file, proxy_type, proxy_host, proxy_port, proxy_username, proxy_password, status)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                phone, session_file, acc.get("proxy_type"), acc.get("proxy_host"),
                                acc.get("proxy_port"), acc.get("proxy_username"),
                                acc.get("proxy_password"), acc.get("status", "active")
                            )
                        )
                await db.commit()
                await db.close()
                print(f"[Supabase] Restored {len(res.data)} accounts ({restored_sessions} session files) from cloud")
        except Exception as e:
            print(f"[Supabase] Accounts sync note: {e}")

    except Exception as e:
        print(f"[Supabase] Sync general error: {e}")


def sync_to_supabase_async(table: str, data: Dict[str, Any], on_conflict: Optional[str] = None):
    """Fire-and-forget sync helper to Supabase."""
    sb = get_supabase_client()
    if not sb:
        return

    def _sync():
        try:
            if on_conflict:
                sb.table(table).upsert(data, on_conflict=on_conflict).execute()
            else:
                sb.table(table).upsert(data).execute()
        except Exception as e:
            # Table might not exist yet if schema was not run
            pass

    asyncio.get_event_loop().run_in_executor(None, _sync)


def backup_session_to_supabase(phone: str, session_file_name: str):
    """Back up a Telegram session binary file to Supabase in base64."""
    sb = get_supabase_client()
    if not sb:
        return

    session_path = os.path.join(SESSIONS_DIR, session_file_name)
    if not os.path.exists(session_path):
        return

    try:
        with open(session_path, "rb") as f:
            session_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        def _update():
            try:
                sb.table("accounts").upsert({
                    "phone": phone,
                    "session_file": session_file_name,
                    "session_data": session_b64,
                    "status": "active"
                }, on_conflict="phone").execute()
                print(f"[Supabase] Cloud backup saved for session {phone}")
            except Exception as e:
                pass

        asyncio.get_event_loop().run_in_executor(None, _update)
    except Exception as e:
        print(f"[Supabase] Failed to encode session for {phone}: {e}")


async def log_event(level: str, source: str, message: str, details: str = None):
    """Log an event to the local database and cloud Supabase."""
    try:
        db = await aiosqlite.connect(DB_PATH, timeout=30.0)
        await db.execute(
            "INSERT INTO event_logs (level, source, message, details) VALUES (?, ?, ?, ?)",
            (level, source, message, details)
        )
        await db.commit()
        await db.close()

        # Cloud sync
        sync_to_supabase_async("event_logs", {
            "level": level,
            "source": source,
            "message": message,
            "details": details or ""
        })
    except Exception as e:
        print(f"Failed to log event: {e}")
