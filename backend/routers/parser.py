"""
Parser API — collect audience from Telegram chats using Telethon.
"""
import asyncio
import csv
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional

from ..database import get_db, log_event

router = APIRouter(prefix="/api/parser", tags=["parser"])

_parsing_active = False
_parsing_progress = {"total": 0, "parsed": 0, "status": "idle", "current_chat": ""}
_parse_task = None


async def _do_parse(links, online_filter, active_writers_only, skip_admins, skip_bots):
    """Background parsing coroutine that fetches users from chats via Telethon."""
    global _parsing_active, _parsing_progress

    from ..services.telegram_engine import telegram_engine, get_api_credentials

    api_id, api_hash = await get_api_credentials()
    if not api_id or not api_hash:
        _parsing_progress = {"total": 0, "parsed": 0, "status": "error", "current_chat": "API not configured"}
        _parsing_active = False
        return

    # Get active account
    db = await get_db()
    cursor = await db.execute("SELECT * FROM accounts WHERE status = 'active' LIMIT 1")
    row = await cursor.fetchone()
    await db.close()

    if not row:
        _parsing_progress["status"] = "error"
        _parsing_progress["current_chat"] = "No active accounts"
        _parsing_active = False
        return

    account = {
        "id": row[0], "phone": row[1], "session_file": row[2],
        "proxy_type": row[3], "proxy_host": row[4], "proxy_port": row[5],
        "proxy_username": row[6], "proxy_password": row[7],
    }

    try:
        await telegram_engine.connect_account(account)
    except Exception as e:
        _parsing_progress["status"] = "error"
        _parsing_progress["current_chat"] = str(e)
        _parsing_active = False
        return

    client = telegram_engine.get_client(account["id"])
    if not client:
        _parsing_progress["status"] = "error"
        _parsing_active = False
        return

    from telethon.tl.types import UserStatusOnline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth

    total_parsed = 0

    for i, link in enumerate(links):
        if not _parsing_active:
            break

        chat_name = link.strip().split("/")[-1].lstrip("@")
        _parsing_progress["current_chat"] = chat_name
        _parsing_progress["total"] = len(links)

        try:
            entity = await client.get_entity(link.strip())
            participants = await client.get_participants(entity, limit=500)

            users_to_insert = []

            for user in participants:
                if not _parsing_active:
                    break
                if skip_bots and user.bot:
                    continue
                if user.deleted:
                    continue

                # Check online filter
                last_online_str = ""
                is_recent = False
                status = user.status
                if isinstance(status, UserStatusOnline):
                    last_online_str = "Online"
                    is_recent = True
                elif isinstance(status, UserStatusRecently):
                    last_online_str = "Нещодавно"
                    is_recent = True
                elif isinstance(status, UserStatusLastWeek):
                    last_online_str = "Цього тижня"
                    is_recent = online_filter and online_filter >= 168
                elif isinstance(status, UserStatusLastMonth):
                    last_online_str = "Цього місяця"
                    is_recent = False
                elif hasattr(status, 'was_online') and status and status.was_online:
                    dt = status.was_online
                    last_online_str = dt.strftime("%d.%m.%Y %H:%M")
                    if online_filter:
                        import datetime
                        cutoff = datetime.datetime.now(datetime.timezone.utc) - timedelta(hours=online_filter)
                        is_recent = dt > cutoff
                    else:
                        is_recent = True
                else:
                    last_online_str = "Невідомо"
                    is_recent = not online_filter  # pass if no filter

                if online_filter and not is_recent:
                    continue
                
                users_to_insert.append((
                    user.id, user.username, user.first_name, user.last_name,
                    chat_name, last_online_str, 0
                ))

            if users_to_insert:
                db = await get_db()
                try:
                    await db.executemany(
                        """INSERT OR IGNORE INTO parsed_users
                        (user_id, username, first_name, last_name, source_chat, last_online, is_active_writer)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        users_to_insert
                    )
                    await db.commit()
                    total_parsed += len(users_to_insert)
                except Exception as e:
                    await log_event("warn", "parser", f"DB insert error: {str(e)}")
                finally:
                    await db.close()

            _parsing_progress["parsed"] = total_parsed
            await log_event("info", "parser", f"Parsed {chat_name}: got users (total: {total_parsed})")

        except Exception as e:
            await log_event("warn", "parser", f"Error parsing {chat_name}: {str(e)}")

        # Small delay between chats
        await asyncio.sleep(2)

    _parsing_progress["status"] = "done" if _parsing_active else "stopped"
    _parsing_progress["parsed"] = total_parsed
    _parsing_active = False
    await log_event("info", "parser", f"Parsing complete: {total_parsed} users collected")


@router.post("/start")
async def start_parsing(
    chat_links: str = Form(...),
    online_filter: Optional[str] = Form(None),
    active_writers_only: str = Form("false"),
    skip_admins: str = Form("true"),
    skip_bots: str = Form("true"),
):
    """Start parsing users from specified chats."""
    global _parsing_active, _parsing_progress, _parse_task

    if _parsing_active:
        raise HTTPException(409, "Parsing is already in progress")

    links = [l.strip() for l in chat_links.replace(",", "\n").split("\n") if l.strip()]
    if not links:
        raise HTTPException(400, "No chat links provided")

    of = int(online_filter) if online_filter and online_filter.isdigit() else None
    awo = active_writers_only.lower() in ("true", "1")
    sa = skip_admins.lower() in ("true", "1")
    sb = skip_bots.lower() in ("true", "1")

    _parsing_active = True
    _parsing_progress = {"total": len(links), "parsed": 0, "status": "running", "current_chat": ""}

    # Launch background task
    _parse_task = asyncio.create_task(_do_parse(links, of, awo, sa, sb))

    await log_event("info", "parser", f"Started parsing {len(links)} chats")
    return {"success": True, "message": f"Parsing started for {len(links)} chats"}


@router.get("/status")
async def get_parsing_status():
    return _parsing_progress


@router.post("/stop")
async def stop_parsing():
    global _parsing_active
    _parsing_active = False
    _parsing_progress["status"] = "stopped"
    await log_event("info", "parser", "Parsing stopped by user")
    return {"success": True}


@router.post("/upload-links")
async def upload_links_file(file: UploadFile = File(...)):
    """Upload a .txt file with chat links (one per line)."""
    content = await file.read()
    text = content.decode("utf-8")
    links = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("#")]
    return {"success": True, "links": links, "count": len(links)}


@router.get("/users")
async def get_parsed_users(limit: int = 100, offset: int = 0, source: Optional[str] = None):
    db = await get_db()
    if source:
        cursor = await db.execute(
            "SELECT * FROM parsed_users WHERE source_chat = ? ORDER BY parsed_at DESC LIMIT ? OFFSET ?",
            (source, limit, offset))
    else:
        cursor = await db.execute(
            "SELECT * FROM parsed_users ORDER BY parsed_at DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = await cursor.fetchall()
    users = []
    for row in rows:
        users.append({
            "id": row[0], "user_id": row[1], "username": row[2],
            "first_name": row[3], "last_name": row[4], "phone": row[5],
            "source_chat": row[6], "last_online": row[7],
            "is_active_writer": bool(row[8]), "parsed_at": row[9],
        })
    cursor = await db.execute("SELECT COUNT(*) FROM parsed_users")
    total = (await cursor.fetchone())[0]
    await db.close()
    return {"users": users, "total": total}


@router.get("/export/txt")
async def export_txt():
    db = await get_db()
    cursor = await db.execute("SELECT username, user_id FROM parsed_users")
    rows = await cursor.fetchall()
    await db.close()
    lines = [f"@{row[0]}" if row[0] else str(row[1]) for row in rows]
    content = "\n".join(lines)
    return StreamingResponse(io.BytesIO(content.encode("utf-8")), media_type="text/plain",
                             headers={"Content-Disposition": "attachment; filename=parsed_users.txt"})


@router.get("/export/csv")
async def export_csv():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM parsed_users")
    rows = await cursor.fetchall()
    await db.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "source_chat", "last_online", "active_writer"])
    for row in rows:
        writer.writerow([row[1], row[2], row[3], row[4], row[6], row[7], row[8]])
    content = output.getvalue()
    return StreamingResponse(io.BytesIO(content.encode("utf-8")), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=parsed_users.csv"})


@router.delete("/users")
async def clear_parsed_users():
    db = await get_db()
    await db.execute("DELETE FROM parsed_users")
    await db.commit()
    await db.close()
    await log_event("info", "parser", "Parsed users database cleared")
    return {"success": True}
