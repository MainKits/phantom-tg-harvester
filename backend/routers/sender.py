"""
Sender API — mass messaging with spintax, rotation across accounts, media support.
Supports: direct user messages, chat/group broadcasting, comment posting.
"""
import os
import json
import asyncio
import random
import time
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
    """Background worker: sends messages in parallel across multiple accounts with dynamic shared queue."""
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
    target_retry_counts = {}

    async def _remove_dead_target(target_val: str, reason: str, phone: str = ""):
        """Mark target as skipped for this task run without touching user's target file on disk."""
        prefix = f"[{phone}] " if phone else ""
        await log_event("warn", "sender", f"{prefix}⚠️ Пропуск чату: {target_val} ({reason})")
        async with targets_lock:
            try:
                while target_val in targets:
                    targets.remove(target_val)
            except Exception:
                pass

    async def _add_new_target(new_target: str, phone: str = ""):
        """Add newly discovered sponsor channel/chat to targets list and targets file on disk."""
        new_target = str(new_target).strip()
        if not new_target:
            return
        prefix = f"[{phone}] " if phone else ""
        async with targets_lock:
            if new_target not in targets:
                targets.append(new_target)
                if targets_file:
                    try:
                        fpath = os.path.join(EXPORTS_DIR, targets_file.strip())
                        if os.path.exists(fpath):
                            with open(fpath, "a", encoding="utf-8") as f:
                                f.write(f"\n{new_target}")
                    except Exception as af_err:
                        print(f"[Sender] Error appending new target to file: {af_err}")
                await log_event("info", "sender", f"{prefix}➕ Додано спонсорський канал у базу розсилки: {new_target}")

    async def _resolve_target_entity(client, target_str: str):
        """
        Cleans and resolves any Telegram target into an entity.
        Handles invite links, URLs with trailing slashes, post links, numeric IDs.
        Returns: (entity, is_broadcast, is_post_link, post_id)
        """
        raw = str(target_str).strip()
        for ch in ["\u200b", "\ufeff", "\u00a0", "\r", "\n"]:
            raw = raw.replace(ch, "")
        raw = raw.strip()

        # Check for invite links (t.me/+, joinchat/, /+)
        if "t.me/+" in raw or "joinchat/" in raw or "/+" in raw:
            if "t.me/+" in raw:
                invite_hash = raw.split("t.me/+")[1]
            elif "joinchat/" in raw:
                invite_hash = raw.split("joinchat/")[1]
            else:
                invite_hash = raw.split("/+")[1]
            invite_hash = invite_hash.split("/")[0].split("?")[0].strip()

            from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
            try:
                imp = await client(ImportChatInviteRequest(invite_hash))
                await asyncio.sleep(1.5)
                if hasattr(imp, 'chats') and imp.chats:
                    ent = imp.chats[0]
                    return ent, getattr(ent, 'broadcast', False), False, None
            except UserAlreadyParticipantError:
                try:
                    chk = await client(CheckChatInviteRequest(invite_hash))
                    if hasattr(chk, 'chat'):
                        ent = chk.chat
                        return ent, getattr(ent, 'broadcast', False), False, None
                except Exception:
                    pass
            except InviteRequestSentError:
                raise
            except (InviteHashInvalidError, InviteHashExpiredError):
                raise

        # Clean URL prefixes
        clean = raw
        if "telegram.me/" in clean:
            clean = clean.replace("telegram.me/", "t.me/")
        if "https://" in clean:
            clean = clean.replace("https://", "")
        if "http://" in clean:
            clean = clean.replace("http://", "")
        if "tg://resolve?domain=" in clean:
            clean = clean.replace("tg://resolve?domain=", "")

        # Check for post link: e.g. t.me/channel/123 or channel:123
        is_post_link = False
        post_id = None
        if "t.me/" in clean and "/" in clean.split("t.me/")[1]:
            parts = clean.split("t.me/")[1].split("/")
            if len(parts) >= 2 and parts[1].split("?")[0].isdigit():
                clean = parts[0]
                is_post_link = True
                post_id = int(parts[1].split("?")[0])
        elif ":" in clean and clean.rsplit(":", 1)[1].isdigit():
            parts = clean.rsplit(":", 1)
            clean = parts[0]
            is_post_link = True
            post_id = int(parts[1])

        # Strip remaining path and query
        if "t.me/" in clean:
            clean = clean.split("t.me/")[1]
        clean = clean.split("/")[0].split("?")[0].strip()
        clean = clean.lstrip("@")

        if clean.startswith("-") and clean[1:].isdigit():
            target_param = int(clean)
        elif clean.isdigit():
            target_param = int(clean)
        else:
            target_param = clean

        entity = await client.get_entity(target_param)
        is_broadcast = getattr(entity, 'broadcast', False)
        return entity, is_broadcast, is_post_link, post_id

    async def _ensure_joined_channel(client, entity, log_fn=None):
        """
        Ensure client is in the channel/group if not already joined.
        Skips JoinChannelRequest if left is False (avoids join FloodWait).
        """
        is_left = getattr(entity, 'left', None)
        if is_left is False:
            return True

        from telethon.tl.functions.channels import JoinChannelRequest
        try:
            await client(JoinChannelRequest(entity))
            await asyncio.sleep(1.5)
            return True
        except UserAlreadyParticipantError:
            return True
        except FloodWaitError as fwe:
            if fwe.seconds <= 30:
                if log_fn:
                    await log_fn(f"Join FloodWait {fwe.seconds}s — очікуємо...")
                await asyncio.sleep(fwe.seconds + 2)
                try:
                    await client(JoinChannelRequest(entity))
                    return True
                except Exception:
                    pass
            raise fwe
        except Exception as je:
            j_str = str(je).lower()
            if "channelstoomuch" in j_str:
                raise je
            return False

    async def _send_for_account(account: dict, target_queue: asyncio.Queue, all_targets_ref: list, accounts_count: int):
        """Worker function for one account sending to shared target queue."""
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
        join_cooldown_until = 0

        _log_c = lambda txt: log_event("info", "sender", f"[{account['phone']}] {txt}")
        async def _on_s(ch_target: str):
            await _add_new_target(ch_target, account["phone"])
            if ch_target not in all_targets_ref:
                all_targets_ref.append(ch_target)
                await target_queue.put(ch_target)

        while task_id in _active_task_loops and not target_queue.empty() and sent_this_account < per_account:
            try:
                target = target_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            target_str = str(target).strip()
            if not target_str:
                continue

            try:
                # 40s timeout so no single chat can freeze the worker
                async with asyncio.timeout(40.0):
                    msg = parse_spintax(message_text) if (spintax_enabled and message_text) else message_text
                    entity, is_broadcast, is_post_link, post_id = await _resolve_target_entity(client, target_str)

                    if send_type == "users":
                        if media_path and os.path.exists(media_path):
                            try:
                                await client.send_message(entity, msg, file=media_path)
                            except Exception as m_err:
                                m_str = str(m_err).lower()
                                if "media" in m_str or "photo" in m_str or "file" in m_str or "rights" in m_str:
                                    await client.send_message(entity, msg)
                                else:
                                    raise m_err
                        else:
                            await client.send_message(entity, msg)

                    elif send_type == "comments":
                        if not is_post_link or not post_id:
                            post_id = 1
                            async for m in client.iter_messages(entity, limit=1):
                                post_id = m.id
                                break
                        try:
                            await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                        except Exception as c_err:
                            c_str = str(c_err).lower()
                            if "msg_id_invalid" in c_str or "chatwriteforbidden" in c_str or "chatadminrequired" in c_str or "channelprivate" in c_str:
                                raise Exception(f"PERM_NO_WRITE: коментарі недоступні або вимкнені: {c_err}")
                            raise c_err

                    else:  # "chats" or "combo"
                        if is_post_link and post_id:
                            # Explicit post link: comment directly
                            try:
                                await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                            except Exception as c_err:
                                c_str = str(c_err).lower()
                                if "msg_id_invalid" in c_str or "chatwriteforbidden" in c_str or "chatadminrequired" in c_str or "channelprivate" in c_str:
                                    raise Exception(f"PERM_NO_WRITE: коментарі недоступні або вимкнені: {c_err}")
                                raise c_err
                        elif is_broadcast:
                            # Broadcast channel without post link: try commenting on latest post
                            post_id = 1
                            async for m in client.iter_messages(entity, limit=1):
                                post_id = m.id
                                break
                            try:
                                await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                            except Exception as comm_err:
                                raise Exception(f"PERM_NO_WRITE: канал закритий (немає доступу для запису або коментарів: {comm_err})")
                        else:
                            # Group / Supergroup
                            needs_join = getattr(entity, 'left', None) is not False
                            if needs_join and time.time() < join_cooldown_until:
                                # Requeue for another account without join cooldown
                                retries = target_retry_counts.get(target_str, 0)
                                if retries < accounts_count:
                                    target_retry_counts[target_str] = retries + 1
                                    await target_queue.put(target_str)
                                    await asyncio.sleep(0.5)
                                    continue

                            # Ensure joined
                            try:
                                await _ensure_joined_channel(client, entity, log_fn=_log_c)
                            except FloodWaitError as j_fwe:
                                join_cooldown_until = time.time() + j_fwe.seconds
                                await log_event("warn", "sender", f"[{account['phone']}] Ліміт Telegram на вступ у нові канали (FloodWait {j_fwe.seconds}s). Акаунт переходить до чатів, де вже є учасником.")
                                retries = target_retry_counts.get(target_str, 0)
                                if retries < accounts_count:
                                    target_retry_counts[target_str] = retries + 1
                                    await target_queue.put(target_str)
                                    continue
                                else:
                                    raise j_fwe
                            except Exception as j_err:
                                if "channelstoomuch" in str(j_err).lower():
                                    await log_event("warn", "sender", f"[{account['phone']}] Досягнуто ліміт 500 груп (ChannelsTooMuchError).")
                                    retries = target_retry_counts.get(target_str, 0)
                                    if retries < accounts_count:
                                        target_retry_counts[target_str] = retries + 1
                                        await target_queue.put(target_str)
                                        continue

                            # Auto-handle bot captchas and sponsor channel requirements after joining
                            try:
                                await asyncio.sleep(1.5)
                                await telegram_engine.handle_captcha_and_subscriptions(client, entity, log_fn=_log_c, on_sponsor_channel=_on_s)
                            except Exception:
                                pass

                            # Send message
                            try:
                                if media_path and os.path.exists(media_path):
                                    try:
                                        await client.send_message(entity, msg, file=media_path)
                                    except Exception as m_err:
                                        m_str = str(m_err).lower()
                                        if "media" in m_str or "photo" in m_str or "file" in m_str or "rights" in m_str or "restrict" in m_str:
                                            await client.send_message(entity, msg)
                                        else:
                                            raise m_err
                                else:
                                    await client.send_message(entity, msg)
                            except Exception as send_err:
                                err_str = str(send_err)
                                handled = False
                                if "ChatWriteForbidden" in err_str or "ChatAdminRequired" in err_str:
                                    try:
                                        did_solve = await telegram_engine.handle_captcha_and_subscriptions(client, entity, log_fn=_log_c, on_sponsor_channel=_on_s)
                                        if did_solve:
                                            await asyncio.sleep(2)
                                            if media_path and os.path.exists(media_path):
                                                try:
                                                    await client.send_message(entity, msg, file=media_path)
                                                    handled = True
                                                except Exception:
                                                    await client.send_message(entity, msg)
                                                    handled = True
                                            else:
                                                await client.send_message(entity, msg)
                                                handled = True
                                    except Exception:
                                        pass

                                if not handled:
                                    if send_type == "combo" and is_broadcast:
                                        post_id = 1
                                        async for m in client.iter_messages(entity, limit=1):
                                            post_id = m.id
                                            break
                                        try:
                                            await telegram_engine.post_comment(client, entity, post_id, msg, file=media_path)
                                            handled = True
                                        except Exception:
                                            raise send_err
                                    else:
                                        raise send_err

                sent_this_account += 1
                consecutive_flood_waits = 0
                await log_event("info", "sender", f"[{account['phone']}] → {target_str}: ✓")
                await _increment_stats(task_id, success=True)

                delay = random.randint(delay_min, delay_max)
                await asyncio.sleep(delay)

            except InviteRequestSentError:
                await _increment_stats(task_id, success=False)
                await log_event("info", "sender", f"[{account['phone']}] → {target_str}: надіслано запит на вступ (очікує схвалення адміном)")
                await asyncio.sleep(1)
                continue

            except SlowModeWaitError as e:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: увімкнено SlowMode ({e.seconds}s), пропуск")
                await asyncio.sleep(2)
                continue

            except FloodWaitError as e:
                await _increment_stats(task_id, success=False)
                if e.seconds <= 60:
                    await log_event("info", "sender", f"[{account['phone']}] FloodWait {e.seconds}s — очікуємо...")
                    await asyncio.sleep(e.seconds + 2)
                    continue
                else:
                    consecutive_flood_waits += 1
                    if consecutive_flood_waits >= 2:
                        await log_event("warn", "sender", f"[{account['phone']}] Повторний FloodWait {e.seconds}s. Пропускаємо цей акаунт для поточної задачі.")
                        break
                    else:
                        await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: FloodWait {e.seconds}s (ліміт дій). Пропускаємо цей канал.")
                        await asyncio.sleep(3)
                        continue

            except PeerFloodError:
                is_real = await _check_is_real_spamblock(client, account)
                if is_real:
                    await log_event("warn", "sender", f"[{account['phone']}] PeerFlood — підтверджено спам-блок через @SpamBot")
                    await _mark_spam_block(account["id"], "Підтверджено @SpamBot")
                else:
                    await log_event("warn", "sender", f"[{account['phone']}] PeerFlood (тимчасовий ліміт дій) — в @SpamBot чисто. Зупиняємо цей акаунт на поточну задачу, статус Active.")
                break

            except (UserDeactivatedBanError, PhoneNumberBannedError) as e:
                await log_event("error", "sender", f"[{account['phone']}] Акаунт заблоковано Telegram: {e}")
                await _mark_banned(account["id"], account["phone"], str(e))
                break

            except (UsernameNotOccupiedError, UsernameInvalidError) as e:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: юзернейм або чат не знайдено в Telegram ({e}), пропуск")
                await asyncio.sleep(1)
                continue

            except (InviteHashInvalidError, InviteHashExpiredError) as e:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: посилання на чат недійсне або прострочене, пропуск")
                await asyncio.sleep(1)
                continue

            except ChannelPrivateError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: приватний канал (потрібне посилання-запрошення), пропуск")
                await asyncio.sleep(1)
                continue

            except ChannelInvalidError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: канал або чат недоступний для цього акаунта, пропуск")
                await asyncio.sleep(1)
                continue

            except UserBannedInChannelError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: акаунт обмежено в цьому чаті, пропуск")
                await asyncio.sleep(1)
                continue

            except InputUserDeactivatedError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: акаунт користувача видалено, пропуск")
                await asyncio.sleep(1)
                continue

            except (ChatWriteForbiddenError, ChatAdminRequiredError) as e:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: немає прав на запис (обмеження в чаті або тільки адміни), пропуск")
                await asyncio.sleep(1)
                continue

            except ValueError as e:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: не вдалося знайти сутність ({str(e)[:100]}), пропуск")
                await asyncio.sleep(1)
                continue

            except UserPrivacyRestrictedError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: приватні налаштування користувача, пропуск")
                await asyncio.sleep(1)
                continue

            except TimeoutError:
                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: таймаут (>40s), пропуск")
                await asyncio.sleep(1)
                continue

            except Exception as e:
                err_text = str(e).lower()
                if "cannot find any entity" in err_text:
                    await _increment_stats(task_id, success=False)
                    await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: чат не знайдено для цього акаунта, пропуск")
                    await asyncio.sleep(1)
                    continue

                if "user_deactivated" in err_text or "phone_number_banned" in err_text:
                    await log_event("error", "sender", f"[{account['phone']}] Заблоковано: {e}")
                    await _mark_banned(account["id"], account["phone"], str(e))
                    break

                if send_type == "users" and "mutual contacts" in err_text:
                    is_real = await _check_is_real_spamblock(client, account)
                    if is_real:
                        await log_event("warn", "sender", f"[{account['phone']}] Mutual contacts — підтверджено спам-блок @SpamBot")
                        await _mark_spam_block(account["id"], "Підтверджено @SpamBot")
                    else:
                        await log_event("warn", "sender", f"[{account['phone']}] Mutual contacts — в @SpamBot чисто. Зупиняємо цей акаунт на поточну задачу.")
                    break

                await _increment_stats(task_id, success=False)
                await log_event("warn", "sender", f"[{account['phone']}] → {target_str}: {str(e)[:120]}")
                await asyncio.sleep(1)

    while task_id in _active_task_loops:
        db = await get_db()
        accounts = await _get_active_accounts(db)
        await db.close()

        if not accounts:
            await log_event("warn", "sender", f"Task #{task_id}: no active accounts available")
            break

        # Shared concurrent queue for all accounts
        target_queue = asyncio.Queue()
        for t in targets:
            await target_queue.put(t)

        workers = []
        for account in accounts:
            workers.append(_send_for_account(account, target_queue, targets, len(accounts)))

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
