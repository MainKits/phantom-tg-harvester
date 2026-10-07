"""
Sender API — mass messaging with spintax, rotation across accounts, media support.
Supports: direct user messages, chat/group broadcasting, comment posting.
"""
import os
import json
import asyncio
import random
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from ..database import get_db, log_event
from ..services.spintax import parse_spintax, validate_spintax, count_variations

router = APIRouter(prefix="/api/sender", tags=["sender"])

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")
EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

_active_task_loops: dict = {}


# ─── Task creation ────────────────────────────────────────────────────────────

@router.post("/create-task")
async def create_send_task(
    message_text: str = Form(...),
    targets_file: str = Form(""),
    targets_text: Optional[str] = Form(None),
    send_type: str = Form("users"),        # "users" | "chats" | "comments"
    repeat_interval: int = Form(0),
    spintax_enabled: bool = Form(True),
    messages_per_account: int = Form(35),
    delay_min: int = Form(45),
    delay_max: int = Form(120),
    auto_responder_enabled: bool = Form(False),
    auto_responder_keywords: str = Form('[]'),
    forward_to_account: Optional[str] = Form(None),
    comment_post_id: int = Form(0),        # for comments mode: post id to comment on
):
    if spintax_enabled:
        v = validate_spintax(message_text)
        if not v["valid"]:
            raise HTTPException(400, detail=f"Spintax error: {v['error']}")

    if targets_text and targets_text.strip():
        import time
        filename = f"targets_{int(time.time())}.txt"
        filepath = os.path.join(EXPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(targets_text.strip())
        targets_file = filename

    db = await get_db()
    
    # Verify active accounts exist
    acc_cur = await db.execute("SELECT COUNT(*) FROM accounts WHERE status = 'active'")
    acc_row = await acc_cur.fetchone()
    if not acc_row or acc_row[0] == 0:
        await db.close()
        raise HTTPException(400, detail="Немає активних акаунтів для розсилки. Додайте або авторизуйте акаунти у вкладці Account Manager.")

    cursor = await db.execute(
        """INSERT INTO send_tasks
        (send_type, repeat_interval, targets_file, message_text, spintax_enabled,
         messages_per_account, delay_min, delay_max, auto_responder_enabled,
         auto_responder_keywords, forward_to_account)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (send_type, repeat_interval, targets_file, message_text, int(spintax_enabled),
         messages_per_account, delay_min, delay_max, int(auto_responder_enabled),
         auto_responder_keywords, forward_to_account),
    )
    task_id = cursor.lastrowid
    await db.commit()
    await db.close()

    variations = count_variations(message_text) if spintax_enabled else 1
    await log_event("info", "sender",
                    f"Send task #{task_id} created ({variations} variations, type: {send_type})")
    return {
        "success": True, "task_id": task_id, "variations": variations,
        "preview": parse_spintax(message_text) if spintax_enabled else message_text
    }


@router.post("/upload-media")
async def upload_media(file: UploadFile = File(...)):
    dest = os.path.join(MEDIA_DIR, file.filename)
    with open(dest, "wb") as f:
        f.write(await file.read())
    return {"success": True, "path": dest, "filename": file.filename}


@router.post("/upload-base")
async def upload_user_base(file: UploadFile = File(...)):
    content = await file.read()
    
    text = None
    for enc in ("utf-8-sig", "utf-8", "windows-1251", "cp1251", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except Exception:
            pass
    if text is None:
        text = content.decode("utf-8", errors="ignore")

    users = [l.strip() for l in text.strip().split("\n") if l.strip()]

    import time
    filename = f"base_{int(time.time())}_{file.filename}"
    filepath = os.path.join(EXPORTS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(users))

    return {"success": True, "total_users": len(users), "filename": file.filename,
            "saved_filename": filename}


# ─── Core sending logic ───────────────────────────────────────────────────────

async def _get_active_accounts(db) -> list:
    """Fetch all active accounts from DB."""
    cursor = await db.execute(
        "SELECT * FROM accounts WHERE status = 'active' ORDER BY RANDOM()"
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "phone": r[1], "session_file": r[2],
         "proxy_type": r[3], "proxy_host": r[4], "proxy_port": r[5],
         "proxy_username": r[6], "proxy_password": r[7],
         "messages_sent_today": r[9]}
        for r in rows
    ]


async def _mark_spam_block(account_id: int):
    db = await get_db()
    await db.execute("UPDATE accounts SET status = 'spam-block' WHERE id = ?", (account_id,))
    await db.commit()
    await db.close()


async def _do_send_task(task_id: int):
    """Background worker: sends messages rotating between all active accounts."""
    from ..services.telegram_engine import telegram_engine
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, PeerFloodError

    db = await get_db()
    cursor = await db.execute("SELECT * FROM send_tasks WHERE id = ?", (task_id,))
    task = await cursor.fetchone()
    await db.close()
    if not task:
        return

    send_type        = task[1]
    repeat_interval  = task[2] or 0
    targets_file     = task[3]
    message_text     = task[4]
    spintax_enabled  = bool(task[5])
    per_account      = task[6] or 35
    delay_min        = task[7] or 45
    delay_max        = task[8] or 120

    # Load targets
    targets = []
    if targets_file:
        path = os.path.join(EXPORTS_DIR, targets_file)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                targets = [l.strip() for l in f if l.strip()]

    if not targets:
        await log_event("warn", "sender", f"Task #{task_id}: no targets found")
        db = await get_db()
        await db.execute("UPDATE send_tasks SET status = 'done' WHERE id = ?", (task_id,))
        await db.commit()
        await db.close()
        return

    await log_event("info", "sender", f"Task #{task_id}: {len(targets)} targets, type={send_type}")

    while task_id in _active_task_loops:
        db = await get_db()
        accounts = await _get_active_accounts(db)
        await db.close()

        if not accounts:
            await log_event("warn", "sender", f"Task #{task_id}: no active accounts available")
            break

        success_count = 0
        error_count = 0
        target_index = 0

        for account in accounts:
            if task_id not in _active_task_loops:
                break
            if target_index >= len(targets):
                break

            # Connect account
            try:
                await telegram_engine.connect_account(account)
                client = telegram_engine.get_client(account["id"])
            except Exception as e:
                await log_event("warn", "sender",
                                f"Task #{task_id}: failed to connect {account['phone']}: {e}")
                continue

            if not client:
                continue

            # This account will send 'per_account' messages
            sent_this_account = 0
            while sent_this_account < per_account and target_index < len(targets):
                if task_id not in _active_task_loops:
                    break

                target = targets[target_index]
                target_index += 1

                try:
                    msg = parse_spintax(message_text) if spintax_enabled else message_text

                    if send_type == "users":
                        clean_u = str(target).strip()
                        if "t.me/" in clean_u:
                            clean_u = clean_u.split("t.me/")[-1].split("/")[0].split("?")[0]
                        clean_u = clean_u.lstrip("@")
                        if clean_u.isdigit():
                            clean_u = int(clean_u)
                        entity = await client.get_entity(clean_u)
                        await client.send_message(entity, msg)

                    elif send_type == "chats":
                        clean_c = str(target).strip()
                        if "t.me/+" in clean_c or "joinchat/" in clean_c:
                            invite_hash = clean_c.split("t.me/+")[1] if "t.me/+" in clean_c else clean_c.split("joinchat/")[1]
                            invite_hash = invite_hash.split("/")[0].split("?")[0]
                            from telethon.tl.functions.messages import ImportChatInviteRequest
                            try:
                                await client(ImportChatInviteRequest(invite_hash))
                                await asyncio.sleep(2)
                            except Exception:
                                pass
                            entity = await client.get_entity(clean_c)
                        else:
                            if "t.me/" in clean_c:
                                clean_c = clean_c.split("t.me/")[-1].split("/")[0].split("?")[0]
                            clean_c = clean_c.lstrip("@")
                            if clean_c.isdigit():
                                clean_c = int(clean_c)
                            entity = await client.get_entity(clean_c)
                            try:
                                await client(JoinChannelRequest(entity))
                                await asyncio.sleep(2)
                            except Exception:
                                pass
                        await client.send_message(entity, msg)

                    elif send_type == "comments":
                        # Support: https://t.me/channel/123, @channel:123, or @channel (latest post)
                        clean_t = target.strip()
                        if "t.me/" in clean_t:
                            path_parts = clean_t.split("t.me/")[1].split("/")
                            channel = path_parts[0]
                            post_id = int(path_parts[1]) if len(path_parts) > 1 and path_parts[1].isdigit() else 1
                        elif ":" in clean_t:
                            parts = clean_t.rsplit(":", 1)
                            channel = parts[0]
                            post_id = int(parts[1]) if parts[1].isdigit() else 1
                        else:
                            channel = clean_t
                            entity = await client.get_entity(channel)
                            post_id = 1
                            async for m in client.iter_messages(entity, limit=1):
                                post_id = m.id
                                break
                        await telegram_engine.post_comment(client, channel, post_id, msg)

                    elif send_type == "combo":
                        # Combo mode: automatically detects whether target is a channel (comments) or a group (chat message)
                        clean_t = target.strip()
                        is_post_link = (("t.me/" in clean_t and "/" in clean_t.split("t.me/")[1] and clean_t.split("t.me/")[1].split("/")[1].isdigit()) or (":" in clean_t and clean_t.rsplit(":", 1)[1].isdigit()))
                        
                        if is_post_link:
                            if "t.me/" in clean_t:
                                path_parts = clean_t.split("t.me/")[1].split("/")
                                channel = path_parts[0]
                                post_id = int(path_parts[1])
                            else:
                                parts = clean_t.rsplit(":", 1)
                                channel = parts[0]
                                post_id = int(parts[1])
                            await telegram_engine.post_comment(client, channel, post_id, msg)
                        else:
                            from telethon.tl.types import Channel
                            entity = await client.get_entity(clean_t)
                            if isinstance(entity, Channel) and entity.broadcast:
                                post_id = 1
                                async for m in client.iter_messages(entity, limit=1):
                                    post_id = m.id
                                    break
                                await telegram_engine.post_comment(client, entity, post_id, msg)
                            else:
                                try:
                                    await client(JoinChannelRequest(entity))
                                    await asyncio.sleep(2)
                                except Exception:
                                    pass
                                await client.send_message(entity, msg)

                    success_count += 1
                    sent_this_account += 1
                    await log_event("info", "sender",
                                    f"[{account['phone']}] → {target}: ✓")

                    delay = random.randint(delay_min, delay_max)
                    await asyncio.sleep(delay)

                except FloodWaitError as e:
                    await log_event("warn", "sender",
                                    f"[{account['phone']}] FloodWait {e.seconds}s — marking spam-block")
                    await _mark_spam_block(account["id"])
                    break  # move to next account

                except PeerFloodError:
                    await log_event("warn", "sender",
                                    f"[{account['phone']}] PeerFlood — marking spam-block")
                    await _mark_spam_block(account["id"])
                    break

                except UserPrivacyRestrictedError:
                    error_count += 1
                    await log_event("warn", "sender",
                                    f"[{account['phone']}] → {target}: privacy restricted, skipping")

                except Exception as e:
                    error_count += 1
                    await log_event("warn", "sender",
                                    f"[{account['phone']}] → {target}: {str(e)[:120]}")
                    await asyncio.sleep(3)

        # Update stats
        db = await get_db()
        await db.execute(
            "UPDATE send_tasks SET total_sent = total_sent + ?, total_failed = total_failed + ? WHERE id = ?",
            (success_count, error_count, task_id)
        )
        await db.commit()
        await db.close()

        # If all targets done or one-time mode
        if target_index >= len(targets) or send_type == "users" or repeat_interval <= 0:
            break

        await log_event("info", "sender",
                        f"Task #{task_id} sleeping {repeat_interval} min before next iteration")
        for _ in range(repeat_interval * 60 // 5):
            if task_id not in _active_task_loops:
                break
            await asyncio.sleep(5)

    # Finalize
    if task_id in _active_task_loops:
        del _active_task_loops[task_id]
    db = await get_db()
    await db.execute("UPDATE send_tasks SET status = 'done' WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()
    await log_event("info", "sender", f"Task #{task_id} completed")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/{task_id}/start")
async def start_sending(task_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT id FROM send_tasks WHERE id = ?", (task_id,))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404, "Task not found")
    await db.execute("UPDATE send_tasks SET status = 'running' WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()

    if task_id not in _active_task_loops:
        _active_task_loops[task_id] = True
        asyncio.create_task(_do_send_task(task_id))

    await log_event("info", "sender", f"Send task #{task_id} started")
    return {"success": True}


@router.post("/{task_id}/stop")
async def stop_sending(task_id: int):
    _active_task_loops.pop(task_id, None)
    db = await get_db()
    await db.execute("UPDATE send_tasks SET status = 'stopped' WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()
    await log_event("info", "sender", f"Send task #{task_id} stopped")
    return {"success": True}


@router.get("/tasks")
async def list_tasks():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM send_tasks ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    tasks = []
    for r in rows:
        tasks.append({
            "id": r[0], "send_type": r[1], "repeat_interval": r[2],
            "targets_file": r[3], "message_text": r[4][:80] + "..." if len(r[4] or "") > 80 else r[4],
            "spintax_enabled": bool(r[5]), "messages_per_account": r[6],
            "delay_min": r[7], "delay_max": r[8],
            "status": r[11], "total_sent": r[12], "total_failed": r[13],
            "created_at": r[14]
        })
    return {"tasks": tasks}


@router.delete("/{task_id}")
async def delete_task(task_id: int):
    _active_task_loops.pop(task_id, None)
    db = await get_db()
    await db.execute("DELETE FROM send_tasks WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()
    return {"success": True}


@router.post("/preview-spintax")
async def preview_spintax(text: str = Form(...)):
    v = validate_spintax(text)
    if not v["valid"]:
        raise HTTPException(400, v["error"])
    return {"previews": [parse_spintax(text) for _ in range(5)],
            "total_variations": count_variations(text)}
