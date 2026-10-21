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
    message_text: str = Form(""),
    targets_file: str = Form(""),
    targets_text: Optional[str] = Form(None),
    media_file: Optional[UploadFile] = File(None),
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
    if spintax_enabled and message_text:
        v = validate_spintax(message_text)
        if not v["valid"]:
            raise HTTPException(400, detail=f"Spintax error: {v['error']}")

    media_path = None
    if media_file and media_file.filename:
        import time
        ext = os.path.splitext(media_file.filename)[1]
        safe_name = f"media_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
        dest = os.path.join(MEDIA_DIR, safe_name)
        with open(dest, "wb") as f:
            f.write(await media_file.read())
        media_path = dest

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
        (send_type, repeat_interval, targets_file, message_text, media_path, spintax_enabled,
         messages_per_account, delay_min, delay_max, auto_responder_enabled,
         auto_responder_keywords, forward_to_account)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (send_type, repeat_interval, targets_file, message_text, media_path, int(spintax_enabled),
         messages_per_account, delay_min, delay_max, int(auto_responder_enabled),
         auto_responder_keywords, forward_to_account),
    )
    task_id = cursor.lastrowid
    await db.commit()
    await db.close()

    variations = count_variations(message_text) if (spintax_enabled and message_text) else 1
    await log_event("info", "sender",
                    f"Send task #{task_id} created ({variations} variations, type: {send_type}, media: {bool(media_path)})")
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


async def _mark_spam_block(account_id: int, reason: str = "Спам-блок від Telegram"):
    db = await get_db()
    cursor = await db.execute("SELECT phone FROM accounts WHERE id = ?", (account_id,))
    row = await cursor.fetchone()
    phone = row[0] if row else f"#{account_id}"
    await db.execute("UPDATE accounts SET status = 'spam-block' WHERE id = ?", (account_id,))
    await db.commit()
    await db.close()
    await log_event("alert", "sender", f"⚠️ Акаунт {phone} отримав спам-блок: {reason}")
    try:
        from .system import add_system_alert
        add_system_alert("spam-block", phone, f"Акаунт {phone} отримав спам-блок від Telegram!", reason)
    except Exception:
        pass


async def _mark_banned(account_id: int, reason: str = "Акаунт заблоковано Telegram"):
    db = await get_db()
    cursor = await db.execute("SELECT phone FROM accounts WHERE id = ?", (account_id,))
    row = await cursor.fetchone()
    phone = row[0] if row else f"#{account_id}"
    await db.execute("UPDATE accounts SET status = 'banned' WHERE id = ?", (account_id,))
    await db.commit()
    await db.close()
    await log_event("alert", "sender", f"🚫 Акаунт {phone} заблоковано: {reason}")
    try:
        from .system import add_system_alert
        add_system_alert("banned", phone, f"Акаунт {phone} заблоковано Telegram!", reason)
    except Exception:
        pass


async def _check_is_real_spamblock(client, account: dict) -> bool:
    """Verify with official @SpamBot if account actually has an active spam-block."""
    try:
        await client.send_message("spambot", "/start")
        reply_text = ""
        for _ in range(5):
            await asyncio.sleep(1.5)
            messages = await client.get_messages("spambot", limit=1)
            if messages and not messages[0].out:
                reply_text = messages[0].message.lower()
                break

        if reply_text:
            good_words = [
                "no limits", "free from any restrictions", "good news",
                "свободен", "вільний", "ограничений нет", "обмежень немає",
                "not limited", "working well", "free as a bird"
            ]
            if any(w in reply_text for w in good_words):
                return False
            if any(w in reply_text for w in ["limited", "annoying", "moderators", "ограничен", "обмежен"]):
                return True
    except Exception:
        pass
    return False


async def _do_send_task(task_id: int):
    """Background worker: sends messages in parallel across multiple accounts with target partitioning."""
    from ..services.telegram_engine import telegram_engine
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.errors import (
        FloodWaitError, SlowModeWaitError, UserPrivacyRestrictedError, PeerFloodError,
        UserDeactivatedBanError, PhoneNumberBannedError,
        UsernameNotOccupiedError, UsernameInvalidError,
        InviteHashInvalidError, InviteHashExpiredError,
        UserAlreadyParticipantError, InviteRequestSentError,
        ChannelPrivateError, ChannelInvalidError,
        UserBannedInChannelError, InputUserDeactivatedError,
        ChatWriteForbiddenError, ChatAdminRequiredError
    )

    db = await get_db()
    cursor = await db.execute("SELECT * FROM send_tasks WHERE id = ?", (task_id,))
    task = await cursor.fetchone()
    await db.close()
    if not task:
        return

    try:
        # Use named column access from aiosqlite.Row
        send_type        = task["send_type"] if "send_type" in task.keys() else "users"
        repeat_interval  = int((task["repeat_interval"] if "repeat_interval" in task.keys() else 0) or 0)
        targets_file     = str((task["targets_file"] if "targets_file" in task.keys() else "") or "")
        message_text     = str(task["message_text"] if "message_text" in task.keys() else "")
        media_path       = str(task["media_path"] if "media_path" in task.keys() else "") or None
        if media_path and not os.path.exists(media_path):
            media_path = None
        spintax_enabled  = bool(task["spintax_enabled"] if "spintax_enabled" in task.keys() else True)
        per_account      = int((task["messages_per_account"] if "messages_per_account" in task.keys() else 35) or 35)
        delay_min        = int((task["delay_min"] if "delay_min" in task.keys() else 45) or 45)
        delay_max        = int((task["delay_max"] if "delay_max" in task.keys() else 120) or 120)
    except Exception as parse_e:
        await log_event("error", "sender", f"Task #{task_id} config parsing error: {parse_e}")
        return

    # Load targets
    targets = []
    if targets_file:
        path = os.path.join(EXPORTS_DIR, targets_file.strip())
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                targets = [l.strip() for l in f if l.strip()]

    if not targets:
        await log_event("warn", "sender", f"Task #{task_id}: no targets found in {targets_file}")
        db = await get_db()
        await db.execute("UPDATE send_tasks SET status = 'done' WHERE id = ?", (task_id,))
        await db.commit()
        await db.close()
        return

    await log_event("info", "sender", f"Task #{task_id}: {len(targets)} targets, type={send_type}, media={'yes' if media_path else 'no'}")

    async def _increment_stats(task_id: int, success: bool):
        """Update live statistics in send_tasks and daily_stats safely."""
        db_up = None
        try:
            db_up = await get_db()
            today_str = datetime.now().strftime("%Y-%m-%d")
            await db_up.execute("INSERT OR IGNORE INTO daily_stats (date) VALUES (?)", (today_str,))
            if success:
                await db_up.execute("UPDATE send_tasks SET total_sent = total_sent + 1 WHERE id = ?", (task_id,))
                await db_up.execute("UPDATE daily_stats SET messages_sent = messages_sent + 1 WHERE date = ?", (today_str,))
            else:
                await db_up.execute("UPDATE send_tasks SET total_failed = total_failed + 1 WHERE id = ?", (task_id,))
                await db_up.execute("UPDATE daily_stats SET errors_count = errors_count + 1 WHERE date = ?", (today_str,))
            await db_up.commit()
        except Exception as up_err:
            print(f"[Sender] Stats update warning: {up_err}")
        finally:
            if db_up:
                await db_up.close()

    targets_lock = asyncio.Lock()

    async def _remove_dead_target(target_val: str, reason: str, phone: str = ""):
        """Permanently remove unreachable/inactive/invalid target from in-memory queue and targets file."""
        prefix = f"[{phone}] " if phone else ""
        await log_event("warn", "sender", f"{prefix}🗑️ Чат видалено з бази: {target_val} ({reason})")
        async with targets_lock:
            # Remove from in-memory targets list
            try:
                while target_val in targets:
                    targets.remove(target_val)
            except Exception:
                pass

            # Remove from targets_file on disk
            if targets_file:
                try:
                    fpath = os.path.join(EXPORTS_DIR, targets_file.strip())
                    if os.path.exists(fpath):
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = [l.strip() for l in f if l.strip()]
                        new_lines = [l for l in lines if l != target_val and l != target_val.strip()]
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write("\n".join(new_lines) + ("\n" if new_lines else ""))
                except Exception as e_rm:
                    print(f"[Sender] Error removing dead target from file: {e_rm}")

    async def _send_for_account(account: dict, my_targets: list):
        """Worker function for one account sending to its distributed targets concurrently."""
        connected = False
        try:
            connected = await telegram_engine.connect_account(account)
            client = telegram_engine.get_client(account["id"])
        except Exception as e:
            await log_event("warn", "sender", f"Task #{task_id}: failed to connect {account['phone']}: {e}")
            return

        if not connected or not client:
            await log_event("warn", "sender", f"Task #{task_id}: account {account['phone']} not authorized")
            return

        sent_this_account = 0
        consecutive_flood_waits = 0
        for target in my_targets:
            if task_id not in _active_task_loops:
                break
            if sent_this_account >= per_account:
                break

            target_str = str(target).strip()
            if not target_str:
                continue

            try:
                # 40s timeout so no single chat can freeze the worker
                async with asyncio.timeout(40.0):
                    msg = parse_spintax(message_text) if (spintax_enabled and message_text) else message_text

                    if send_type == "users":
                        clean_u = target_str
                        if "t.me/" in clean_u:
                            clean_u = clean_u.split("t.me/")[-1].split("/")[0].split("?")[0]
                        clean_u = clean_u.lstrip("@")
                        if clean_u.isdigit():
                            clean_u = int(clean_u)
                        entity = await client.get_entity(clean_u)
                        if media_path and os.path.exists(media_path):
                            try:
                                await client.send_message(entity, msg, file=media_path)
                            except Exception as m_err:
                                m_str = str(m_err).lower()
                                if "media" in m_str or "photo" in m_str or "file" in m_str:
                                    await client.send_message(entity, msg)
                                else:
                                    raise m_err
                        else:
                            await client.send_message(entity, msg)

                    elif send_type == "chats":
                        clean_c = target_str
                        entity = None
                        if "t.me/+" in clean_c or "joinchat/" in clean_c or "/+" in clean_c:
                            if "t.me/+" in clean_c:
                                invite_hash = clean_c.split("t.me/+")[1]
                            elif "joinchat/" in clean_c:
                                invite_hash = clean_c.split("joinchat/")[1]
                            else:
                                invite_hash = clean_c.split("/+")[1]
                            invite_hash = invite_hash.split("/")[0].split("?")[0].strip()

                            from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
                            from telethon.tl.types import ChatInviteAlready

                            try:
                                imp = await client(ImportChatInviteRequest(invite_hash))
                                await asyncio.sleep(2)
                                if hasattr(imp, 'chats') and imp.chats:
                                    entity = imp.chats[0]
                            except UserAlreadyParticipantError:
                                try:
                                    chk = await client(CheckChatInviteRequest(invite_hash))
                                    if hasattr(chk, 'chat'):
                                        entity = chk.chat
                                except Exception:
                                    pass
                            except InviteRequestSentError:
                                await _increment_stats(task_id, success=False)
                                await log_event("info", "sender", f"[{account['phone']}] → {target_str}: надіслано запит на вступ (очікує схвалення адміном каналу)")
                                continue
                            except (InviteHashInvalidError, InviteHashExpiredError) as inv_err:
                                raise inv_err

                            if not entity:
                                try:
                                    entity = await client.get_entity(clean_c)
                                except Exception:
                                    pass
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

                        # Auto-handle bot captchas and sponsor channel requirements after joining
                        try:
                            await telegram_engine.handle_captcha_and_subscriptions(client, entity)
                        except Exception:
                            pass

                        try:
                            if media_path and os.path.exists(media_path):
                                try:
                                    await client.send_message(entity, msg, file=media_path)
                                except Exception as m_err:
                                    m_str = str(m_err).lower()
                                    if "media" in m_str or "photo" in m_str or "file" in m_str:
                                        await client.send_message(entity, msg)
                                    else:
                                        raise m_err
                            else:
                                await client.send_message(entity, msg)
                        except Exception as send_err:
                            err_str = str(send_err)
                            handled_write_error = False
                            if "ChatWriteForbidden" in err_str or "ChannelPrivate" in err_str or "ChatAdminRequired" in err_str:
                                # Attempt solving bot captcha / sponsor subscription in case write was gated
                                try:
                                    did_solve = await telegram_engine.handle_captcha_and_subscriptions(client, entity)
                                    if did_solve:
                                        await asyncio.sleep(2)
                                        if media_path and os.path.exists(media_path):
                                            try:
                                                await client.send_message(entity, msg, file=media_path)
                                                handled_write_error = True
                                            except Exception:
                                                pass
                                        else:
                                            await client.send_message(entity, msg)
                                            handled_write_error = True
                                except Exception:
                                    pass

                            if not handled_write_error:
                                if "ChatWriteForbidden" in err_str or "ChannelPrivate" in err_str or "ChatAdminRequired" in err_str:
                                    post_id = 1
                                    async for m in client.iter_messages(entity, limit=1):
                                        post_id = m.id
                                        break
                                    try:
                                        await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                                    except Exception as comm_err:
                                        raise Exception(f"PERM_NO_WRITE: канал закритий (немає доступу для запису або коментарів: {comm_err})")
                                else:
                                    raise send_err

                    elif send_type == "comments":
                        clean_t = target_str
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
                        try:
                            await telegram_engine.post_comment(client, channel, post_id, msg, file=media_path)
                        except Exception as c_err:
                            c_str = str(c_err).lower()
                            if "msg_id_invalid" in c_str or "chatwriteforbidden" in c_str or "chatadminrequired" in c_str or "channelprivate" in c_str:
                                raise Exception(f"PERM_NO_WRITE: коментарі недоступні або вимкнені: {c_err}")
                            raise c_err

                    elif send_type == "combo":
                        clean_t = target_str
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
                            try:
                                await telegram_engine.post_comment(client, channel, post_id, msg, file=media_path)
                            except Exception as c_err:
                                c_str = str(c_err).lower()
                                if "msg_id_invalid" in c_str or "chatwriteforbidden" in c_str or "chatadminrequired" in c_str or "channelprivate" in c_str:
                                    raise Exception(f"PERM_NO_WRITE: коментарі недоступні або вимкнені: {c_err}")
                                raise c_err
                        else:
                            entity = None
                            if "t.me/+" in clean_t or "joinchat/" in clean_t or "/+" in clean_t:
                                if "t.me/+" in clean_t:
                                    invite_hash = clean_t.split("t.me/+")[1]
                                elif "joinchat/" in clean_t:
                                    invite_hash = clean_t.split("joinchat/")[1]
                                else:
                                    invite_hash = clean_t.split("/+")[1]
                                invite_hash = invite_hash.split("/")[0].split("?")[0].strip()

                                from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
                                from telethon.tl.types import ChatInviteAlready

                                try:
                                    imp = await client(ImportChatInviteRequest(invite_hash))
                                    await asyncio.sleep(2)
                                    if hasattr(imp, 'chats') and imp.chats:
                                        entity = imp.chats[0]
                                except UserAlreadyParticipantError:
                                    try:
                                        chk = await client(CheckChatInviteRequest(invite_hash))
                                        if hasattr(chk, 'chat'):
                                            entity = chk.chat
                                    except Exception:
                                        pass
                                except InviteRequestSentError:
                                    await _increment_stats(task_id, success=False)
                                    await log_event("info", "sender", f"[{account['phone']}] → {target_str}: надіслано запит на вступ (очікує схвалення адміном каналу)")
                                    continue
                                except (InviteHashInvalidError, InviteHashExpiredError) as inv_err:
                                    raise inv_err

                            if not entity:
                                from telethon.tl.types import Channel
                                entity = await client.get_entity(clean_t)

                            from telethon.tl.types import Channel
                            if isinstance(entity, Channel) and entity.broadcast:
                                post_id = 1
                                async for m in client.iter_messages(entity, limit=1):
                                    post_id = m.id
                                    break
                                try:
                                    await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                                except Exception as comm_err:
                                    raise Exception(f"PERM_NO_WRITE: канал закритий (немає доступу для запису або коментарів: {comm_err})")
                            else:
                                try:
                                    await client(JoinChannelRequest(entity))
                                    await asyncio.sleep(2)
                                except Exception:
                                    pass
                                try:
                                    await telegram_engine.handle_captcha_and_subscriptions(client, entity)
                                except Exception:
                                    pass

                                try:
                                    if media_path and os.path.exists(media_path):
                                        try:
                                            await client.send_message(entity, msg, file=media_path)
                                        except Exception as m_err:
                                            m_str = str(m_err).lower()
                                            if "media" in m_str or "photo" in m_str or "file" in m_str:
                                                await client.send_message(entity, msg)
                                            else:
                                                raise m_err
                                    else:
                                        await client.send_message(entity, msg)
                                except Exception as send_err:
                                    err_str = str(send_err)
                                    handled_write_error = False
                                    if "ChatWriteForbidden" in err_str or "ChannelPrivate" in err_str or "ChatAdminRequired" in err_str:
                                        try:
                                            did_solve = await telegram_engine.handle_captcha_and_subscriptions(client, entity)
                                            if did_solve:
                                                await asyncio.sleep(2)
                                                if media_path and os.path.exists(media_path):
                                                    try:
                                                        await client.send_message(entity, msg, file=media_path)
                                                        handled_write_error = True
                                                    except Exception:
                                                        pass
                                                else:
                                                    await client.send_message(entity, msg)
                                                    handled_write_error = True
                                        except Exception:
                                            pass

                                    if not handled_write_error:
                                        if "ChatWriteForbidden" in err_str or "ChannelPrivate" in err_str or "ChatAdminRequired" in err_str:
                                            post_id = 1
                                            async for m in client.iter_messages(entity, limit=1):
                                                post_id = m.id
                                                break
                                            try:
                                                await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                                            except Exception as comm_err:
                                                raise Exception(f"PERM_NO_WRITE: канал закритий (немає доступу для запису або коментарів: {comm_err})")
                                        else:
                                            raise send_err

                sent_this_account += 1
                consecutive_flood_waits = 0
                await log_event("info", "sender", f"[{account['phone']}] → {target_str}: ✓")
                await _increment_stats(task_id, success=True)

                delay = random.randint(delay_min, delay_max)
                await asyncio.sleep(delay)

            except SlowModeWaitError as e:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: увімкнено SlowMode ({e.seconds}s), пропускаємо цей канал")
                await asyncio.sleep(2)
                continue

            except FloodWaitError as e:
                await _increment_stats(task_id, success=False)
                # FloodWait is a temporary cooldown on a specific action/channel, NOT necessarily an account-wide block!
                if e.seconds <= 60:
                    await log_event("info", "sender", f"[{account['phone']}] FloodWait {e.seconds}s — очікуємо...")
                    await asyncio.sleep(e.seconds + 2)
                    continue
                else:
                    consecutive_flood_waits += 1
                    # If FloodWait is triggered only on this channel/action, don't kill the account for all other channels!
                    if consecutive_flood_waits >= 2:
                        await log_event("warn", "sender", f"[{account['phone']}] Повторний FloodWait {e.seconds}s на кількох каналах поспіль (загальний ліміт дій Telegram для акаунта). Пропускаємо цей акаунт для поточної задачі.")
                        break
                    else:
                        await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: FloodWait {e.seconds}s (ліміт у цьому каналі/дії). Пропускаємо цей канал і переходимо до наступних.")
                        await asyncio.sleep(3)
                        continue

            except PeerFloodError:
                # PeerFlood: check with official @SpamBot before claiming spam-block!
                is_real = await _check_is_real_spamblock(client, account)
                if is_real:
                    await log_event("warn", "sender", f"[{account['phone']}] PeerFlood — підтверджено спам-блок через @SpamBot")
                    await _mark_spam_block(account["id"], "Підтверджено @SpamBot")
                else:
                    await log_event("warn", "sender", f"[{account['phone']}] PeerFlood (тимчасовий ліміт дій) — в @SpamBot чисто. Зупиняємо акаунт на поточну задачу, статус залишається Active.")
                break

            except (UserDeactivatedBanError, PhoneNumberBannedError) as e:
                await log_event("error", "sender", f"[{account['phone']}] Акаунт заблоковано Telegram: {e}")
                await _mark_banned(account["id"], account["phone"], str(e))
                break

            except (UsernameNotOccupiedError, UsernameInvalidError) as e:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Недійсний або неіснуючий username", account["phone"])
                await asyncio.sleep(1)
                continue

            except (InviteHashInvalidError, InviteHashExpiredError) as e:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Посилання на чат недійсне або прострочене", account["phone"])
                await asyncio.sleep(1)
                continue

            except ChannelPrivateError:
                # Private channel: account might not have joined yet or needs an invite link. DO NOT delete from base!
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: приватний канал (акаунт не є учасником або потрібне посилання-запрошення), пропуск без видалення")
                await asyncio.sleep(1)
                continue

            except ChannelInvalidError:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Канал не існує або видалений", account["phone"])
                await asyncio.sleep(1)
                continue

            except UserBannedInChannelError as e:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Заборонено писати в цьому чаті (бан або обмеження)", account["phone"])
                await asyncio.sleep(1)
                continue

            except InputUserDeactivatedError as e:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Акаунт користувача видалено", account["phone"])
                await asyncio.sleep(1)
                continue

            except (ChatWriteForbiddenError, ChatAdminRequiredError) as e:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Закритий канал (писати можуть лише адміни, коментарі відсутні)", account["phone"])
                await asyncio.sleep(1)
                continue

            except ValueError as e:
                err_lower = str(e).lower()
                await _increment_stats(task_id, success=False)
                if "cannot find any entity" in err_lower or "no user has" in err_lower:
                    await _remove_dead_target(target_str, "Чат або юзернейм не знайдено в Telegram", account["phone"])
                else:
                    await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: {str(e)[:120]}")
                await asyncio.sleep(1)
                continue

            except UserPrivacyRestrictedError:
                await _increment_stats(task_id, success=False)
                await _remove_dead_target(target_str, "Приватні налаштування (заборона повідомлень не від контактів)", account["phone"])
                await asyncio.sleep(1)
                continue

            except TimeoutError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: таймаут (>40s), пропуск")

            except Exception as e:
                err_text = str(e).lower()
                # Check for dead channel markers
                if "perm_no_write" in err_text or "chatwriteforbidden" in err_text or "chatadminrequired" in err_text:
                    await _increment_stats(task_id, success=False)
                    await _remove_dead_target(target_str, "Канал закрито (немає доступу до запису чи коментарів)", account["phone"])
                    await asyncio.sleep(1)
                    continue

                if "cannot find any entity" in err_text:
                    await _increment_stats(task_id, success=False)
                    await _remove_dead_target(target_str, "Чат не знайдено", account["phone"])
                    await asyncio.sleep(1)
                    continue

                # Check for real account-level ban
                if "user_deactivated" in err_text or "phone_number_banned" in err_text:
                    await log_event("error", "sender", f"[{account['phone']}] Заблоковано: {e}")
                    await _mark_banned(account["id"], account["phone"], str(e))
                    break

                # Only if Telegram explicitly reports mutual contacts restriction on PMs
                if send_type == "users" and "mutual contacts" in err_text:
                    is_real = await _check_is_real_spamblock(client, account)
                    if is_real:
                        await log_event("warn", "sender", f"[{account['phone']}] Спам-блок підтверджено: тільки взаємні контакти")
                        await _mark_spam_block(account["id"], "Тільки взаємні контакти")
                        break

                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: {str(e)[:120]}")
                await asyncio.sleep(2)

    while task_id in _active_task_loops:
        db = await get_db()
        accounts = await _get_active_accounts(db)
        await db.close()

        if not accounts:
            await log_event("warn", "sender", f"Task #{task_id}: no active accounts available")
            break

        # Distribute targets across active accounts and run concurrently in parallel threads/workers
        workers = []
        for i, account in enumerate(accounts):
            acc_targets = [t for idx, t in enumerate(targets) if idx % len(accounts) == i]
            if acc_targets:
                workers.append(_send_for_account(account, acc_targets))

        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

        # If one-time mode or users send type
        if send_type == "users" or repeat_interval <= 0:
            break

        await log_event("info", "sender", f"Task #{task_id} sleeping {repeat_interval} min before next iteration")
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
        msg = r["message_text"] if "message_text" in r.keys() else str(r[4] or "")
        tasks.append({
            "id": r["id"],
            "send_type": r["send_type"] if "send_type" in r.keys() else "users",
            "repeat_interval": r["repeat_interval"] if "repeat_interval" in r.keys() else 0,
            "targets_file": r["targets_file"] if "targets_file" in r.keys() else "",
            "message_text": msg[:80] + "..." if len(msg) > 80 else msg,
            "spintax_enabled": bool(r["spintax_enabled"] if "spintax_enabled" in r.keys() else True),
            "messages_per_account": r["messages_per_account"] if "messages_per_account" in r.keys() else 35,
            "delay_min": r["delay_min"] if "delay_min" in r.keys() else 45,
            "delay_max": r["delay_max"] if "delay_max" in r.keys() else 120,
            "status": r["status"] if "status" in r.keys() else "pending",
            "media_path": r["media_path"] if "media_path" in r.keys() else None,
            "total_sent": r["total_sent"] if "total_sent" in r.keys() else 0,
            "total_failed": r["total_failed"] if "total_failed" in r.keys() else 0,
            "created_at": str(r["created_at"] if "created_at" in r.keys() else "")
        })
    return {"tasks": tasks}


@router.get("/active-task")
async def get_active_task():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM send_tasks WHERE status = 'running' ORDER BY id DESC LIMIT 1")
    row = await cursor.fetchone()
    if not row:
        await db.close()
        return {"active": False, "task": None}
    
    # Check if really running in memory
    if row["id"] not in _active_task_loops:
        await db.execute("UPDATE send_tasks SET status = 'stopped' WHERE id = ?", (row["id"],))
        await db.commit()
        await db.close()
        return {"active": False, "task": None}

    await db.close()
    msg = row["message_text"] if "message_text" in row.keys() else ""
    t_file = row["targets_file"] if "targets_file" in row.keys() else ""
    targets_txt = ""
    targets_cnt = 0
    if t_file:
        fpath = os.path.join(EXPORTS_DIR, str(t_file).strip())
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f if l.strip()]
                targets_txt = "\n".join(lines)
                targets_cnt = len(lines)
            except Exception:
                pass

    return {
        "active": True,
        "targets_text": targets_txt,
        "targets_count": targets_cnt,
        "task": {
            "id": row["id"],
            "send_type": row["send_type"] if "send_type" in row.keys() else "users",
            "repeat_interval": row["repeat_interval"] if "repeat_interval" in row.keys() else 0,
            "targets_file": t_file,
            "message_text": msg,
            "media_path": row["media_path"] if "media_path" in row.keys() else None,
            "spintax_enabled": bool(row["spintax_enabled"] if "spintax_enabled" in row.keys() else True),
            "messages_per_account": row["messages_per_account"] if "messages_per_account" in row.keys() else 35,
            "delay_min": row["delay_min"] if "delay_min" in row.keys() else 45,
            "delay_max": row["delay_max"] if "delay_max" in row.keys() else 120,
            "status": row["status"] if "status" in row.keys() else "running",
            "total_sent": row["total_sent"] if "total_sent" in row.keys() else 0,
            "total_failed": row["total_failed"] if "total_failed" in row.keys() else 0,
            "created_at": str(row["created_at"] if "created_at" in row.keys() else "")
        }
    }


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
