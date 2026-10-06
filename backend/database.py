"""
SQLite database setup and models for Phantom TG Harvester.
Automatically creates the database file in the application directory.
"""

import aiosqlite
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phantom_harvester.db")


async def get_db():
    """Get database connection."""
    db = await aiosqlite.connect(DB_PATH, timeout=30.0)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Initialize database tables."""
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


async def log_event(level: str, source: str, message: str, details: str = None):
    """Log an event to the database."""
    try:
        db = await aiosqlite.connect(DB_PATH, timeout=30.0)
        await db.execute(
            "INSERT INTO event_logs (level, source, message, details) VALUES (?, ?, ?, ?)",
            (level, source, message, details)
        )
        await db.commit()
        await db.close()
    except Exception as e:
        print(f"Failed to log event: {e}")
