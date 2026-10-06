"""
Chat Finder API — search Telegram chats/groups/channels by keywords.
Supports filtering by type: groups, channels, or both.
"""
import os
import io
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from ..database import get_db, log_event

router = APIRouter(prefix="/api/chat-finder", tags=["chat-finder"])

_found_chats = []
_search_active = False


def _classify_chat(chat) -> str:
    """Determine if a Telethon entity is a group or channel."""
    from telethon.tl.types import Chat, Channel
    if isinstance(chat, Chat):
        return "group"
    elif isinstance(chat, Channel):
        if getattr(chat, 'megagroup', False) or getattr(chat, 'gigagroup', False):
            return "group"
        elif getattr(chat, 'broadcast', False):
            return "channel"
    return "unknown"


@router.post("/search")
async def search_chats(
    keywords: str = Form(...),
    min_members: int = Form(0),
    limit: int = Form(50),
    chat_type: str = Form("all"),  # "all" | "groups" | "channels"
):
    """Search for Telegram chats/groups by keywords using Telethon."""
    global _found_chats, _search_active

    if _search_active:
        raise HTTPException(409, "Search already in progress")

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        raise HTTPException(400, "No keywords provided")

    _search_active = True

    try:
        from ..services.telegram_engine import telegram_engine, get_api_credentials
        api_id, api_hash = await get_api_credentials()

        if not api_id or not api_hash:
            _search_active = False
            raise HTTPException(400, "API ID/Hash не налаштовані. Перейдіть у Account Manager → API Settings")

        db = await get_db()
        cursor = await db.execute("SELECT * FROM accounts WHERE status = 'active' LIMIT 1")
        account_row = await cursor.fetchone()
        await db.close()

        if not account_row:
            _search_active = False
            raise HTTPException(400, "Немає активних акаунтів. Авторизуйте хоча б один акаунт.")

        account = {
            "id": account_row[0], "phone": account_row[1],
            "session_file": account_row[2], "proxy_type": account_row[3],
            "proxy_host": account_row[4], "proxy_port": account_row[5],
            "proxy_username": account_row[6], "proxy_password": account_row[7],
        }

        try:
            await telegram_engine.connect_account(account)
        except Exception as e:
            _search_active = False
            raise HTTPException(400, f"Не вдалось підключити акаунт: {str(e)}")

        client = telegram_engine.get_client(account["id"])
        if not client:
            _search_active = False
            raise HTTPException(400, "Клієнт не підключений")

        results = []
        seen = set()

        from telethon.tl.functions.contacts import SearchRequest

        for keyword in kw_list:
            try:
                result = await client(SearchRequest(q=keyword, limit=min(limit, 100)))

                for chat in result.chats:
                    if chat.id in seen:
                        continue
                    seen.add(chat.id)

                    ctype = _classify_chat(chat)

                    # Apply type filter
                    if chat_type == "groups" and ctype != "group":
                        continue
                    if chat_type == "channels" and ctype != "channel":
                        continue

                    members = getattr(chat, 'participants_count', None) or 0
                    if min_members and members < min_members:
                        continue

                    username = getattr(chat, 'username', None)
                    title = getattr(chat, 'title', None) or str(chat.id)

                    type_label = {
                        "group": "💬 Чат/Група",
                        "channel": "📢 Канал",
                        "unknown": "❓ Невідомо",
                    }.get(ctype, ctype)

                    results.append({
                        "id": chat.id,
                        "title": title,
                        "username": username,
                        "link": f"https://t.me/{username}" if username else None,
                        "members": members,
                        "keyword": keyword,
                        "type": ctype,
                        "type_label": type_label,
                    })

            except Exception as e:
                await log_event("warn", "chat-finder", f"Search error for '{keyword}': {str(e)}")

        _found_chats = results
        _search_active = False

        groups_count = sum(1 for r in results if r["type"] == "group")
        channels_count = sum(1 for r in results if r["type"] == "channel")
        await log_event("info", "chat-finder",
                        f"Found {len(results)} results ({groups_count} groups, {channels_count} channels) "
                        f"for: {', '.join(kw_list)}")

        return {
            "success": True, "total": len(results), "chats": results,
            "groups_count": groups_count, "channels_count": channels_count,
        }

    except HTTPException:
        _search_active = False
        raise
    except Exception as e:
        _search_active = False
        raise HTTPException(500, f"Search error: {str(e)}")


@router.get("/results")
async def get_results():
    return {"chats": _found_chats, "total": len(_found_chats)}


@router.post("/save")
async def save_selected(
    chat_ids: str = Form(""),
):
    """Save selected chat links to a file."""
    global _found_chats

    if chat_ids == "all":
        selected = _found_chats
    else:
        ids = set(int(x.strip()) for x in chat_ids.split(",") if x.strip())
        selected = [c for c in _found_chats if c["id"] in ids]

    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
    os.makedirs(save_dir, exist_ok=True)

    from datetime import datetime
    filename = f"chats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join(save_dir, filename)

    lines = []
    for chat in selected:
        if chat.get("link"):
            lines.append(chat["link"])
        elif chat.get("username"):
            lines.append(f"https://t.me/{chat['username']}")
        else:
            lines.append(f"# {chat['title']} (ID: {chat['id']}, no public link)")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    await log_event("info", "chat-finder", f"Saved {len(lines)} chat links to {filename}")
    return {"success": True, "filename": filename, "path": filepath, "count": len(lines)}


@router.get("/export")
async def export_chats():
    """Export all found chats as downloadable .txt file."""
    global _found_chats

    lines = []
    for chat in _found_chats:
        link = chat.get("link") or (f"https://t.me/{chat['username']}" if chat.get("username") else "")
        if link:
            lines.append(f"{link}  # {chat.get('type_label', '')} | {chat.get('title', '')} | {chat.get('members', 0)} members")

    if not lines:
        raise HTTPException(400, "No chats to export")

    content = "\n".join(lines)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=found_chats.txt"},
    )


@router.delete("/clear")
async def clear_results():
    global _found_chats
    _found_chats = []
    return {"success": True}
