"""
Dashboard API — statistics and event logs.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Form
from datetime import datetime
import asyncio
import json

from ..database import get_db, log_event

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# WebSocket connections for live log streaming
_ws_connections: list = []


@router.get("/settings")
async def get_settings():
    """Get app settings (API credentials) from local SQLite or Supabase cloud."""
    db = await get_db()
    settings = {}
    cursor = await db.execute("SELECT key, value FROM settings")
    rows = await cursor.fetchall()
    for row in rows:
        settings[row[0]] = row[1]
    await db.close()

    # If missing in local DB, check Supabase cloud
    if not settings.get("api_id") or not settings.get("api_hash"):
        from ..database import get_supabase_client
        sb = get_supabase_client()
        if sb:
            try:
                res = sb.table("settings").select("*").execute()
                if res.data:
                    db = await get_db()
                    for item in res.data:
                        k, v = item.get("key"), str(item.get("value", ""))
                        if k and v:
                            settings[k] = v
                            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
                    await db.commit()
                    await db.close()
            except Exception as e:
                print(f"[Supabase] get_settings error: {e}")

    # Mask api_hash for security
    if "api_hash" in settings and settings["api_hash"]:
        settings["api_hash_masked"] = settings["api_hash"][:4] + "***" + settings["api_hash"][-4:]
    return {"settings": settings}


@router.post("/settings")
async def save_settings(
    api_id: str = Form(""),
    api_hash: str = Form(""),
):
    """Save app settings to both SQLite and Supabase cloud."""
    import os
    from ..database import sync_to_supabase_async

    clean_id = api_id.strip()
    clean_hash = api_hash.strip()

    db = await get_db()
    if clean_id:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('api_id', ?)", (clean_id,)
        )
        sync_to_supabase_async("settings", {"key": "api_id", "value": clean_id}, on_conflict="key")
        os.environ["TG_API_ID"] = clean_id

    if clean_hash:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('api_hash', ?)", (clean_hash,)
        )
        sync_to_supabase_async("settings", {"key": "api_hash", "value": clean_hash}, on_conflict="key")
        os.environ["TG_API_HASH"] = clean_hash

    await db.commit()
    await db.close()
    await log_event("info", "settings", "API credentials saved and synced to cloud")
    return {"success": True}


@router.get("/stats")
async def get_stats():
    """Get dashboard statistics."""
    db = await get_db()
    
    # Active accounts count
    cursor = await db.execute(
        "SELECT COUNT(*) as count FROM accounts WHERE status = 'active'"
    )
    row = await cursor.fetchone()
    active_accounts = row[0] if row else 0
    
    # Total accounts
    cursor = await db.execute("SELECT COUNT(*) as count FROM accounts")
    row = await cursor.fetchone()
    total_accounts = row[0] if row else 0
    
    # Today's stats
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = await db.execute(
        "SELECT * FROM daily_stats WHERE date = ?", (today,)
    )
    row = await cursor.fetchone()
    
    today_stats = {
        "messages_sent": row[1] if row and len(row) > 1 else 0,
        "invites_sent": row[2] if row and len(row) > 2 else 0,
        "errors_count": row[3] if row and len(row) > 3 else 0,
        "users_parsed": total_parsed,
    }
    
    # Spam-blocked accounts
    cursor = await db.execute(
        "SELECT COUNT(*) FROM accounts WHERE status = 'spam-block'"
    )
    row = await cursor.fetchone()
    spam_blocked = row[0] if row else 0
    
    # Banned accounts
    cursor = await db.execute(
        "SELECT COUNT(*) FROM accounts WHERE status = 'banned'"
    )
    row = await cursor.fetchone()
    banned = row[0] if row else 0
    
    # Total parsed users
    cursor = await db.execute("SELECT COUNT(*) FROM parsed_users")
    row = await cursor.fetchone()
    total_parsed = row[0] if row else 0
    
    await db.close()
    
    return {
        "active_accounts": active_accounts,
        "total_accounts": total_accounts,
        "spam_blocked": spam_blocked,
        "banned": banned,
        "total_parsed_users": total_parsed,
        "today": today_stats,
    }


@router.get("/logs")
async def get_logs(limit: int = 100, offset: int = 0):
    """Get recent event logs."""
    db = await get_db()
    
    cursor = await db.execute(
        "SELECT * FROM event_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    
    logs = []
    for row in rows:
        logs.append({
            "id": row[0],
            "level": row[1],
            "source": row[2],
            "message": row[3],
            "details": row[4],
            "created_at": row[5],
        })
    
    await db.close()
    return {"logs": logs}


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    _ws_connections.append(websocket)
    
    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)


async def broadcast_log(level: str, source: str, message: str, details: str = None):
    """Broadcast a log event to all connected WebSocket clients."""
    await log_event(level, source, message, details)
    
    event = {
        "level": level,
        "source": source,
        "message": message,
        "details": details,
        "created_at": datetime.now().isoformat(),
    }
    
    for ws in _ws_connections[:]:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            _ws_connections.remove(ws)
