"""
Inviter API — invite users to Telegram channels/groups with multi-account rotation.
"""

import os
import asyncio
import random
from typing import Optional
from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from ..database import get_db, log_event

router = APIRouter(prefix="/api/inviter", tags=["inviter"])

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
os.makedirs(EXPORTS_DIR, exist_ok=True)

_active_invite_task_loops: dict = {}


@router.post("/upload-base")
async def upload_user_base(file: UploadFile = File(...)):
    content = await file.read()
    users = [l.strip() for l in content.decode("utf-8").strip().split("\n") if l.strip()]

    import time
    filename = f"invite_base_{int(time.time())}_{file.filename}"
    filepath = os.path.join(EXPORTS_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(users))

    return {"success": True, "total_users": len(users), "filename": file.filename,
            "saved_filename": filename}


@router.post("/create-task")
async def create_invite_task(
    target_chat: str = Form(...),
    targets_file: str = Form(""),
    targets_text: Optional[str] = Form(None),
    invites_per_account: int = Form(15),
    delay_min: int = Form(30),
    delay_max: int = Form(60),
):
    if targets_text and targets_text.strip():
        import time
        filename = f"inv_targets_{int(time.time())}.txt"
        filepath = os.path.join(EXPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(targets_text.strip())
        targets_file = filename

    db = await get_db()
    # Ensure targets_file column exists (migration safety)
    try:
        await db.execute("ALTER TABLE invite_tasks ADD COLUMN targets_file TEXT;")
        await db.commit()
    except Exception:
        pass

    cursor = await db.execute(
        """INSERT INTO invite_tasks
        (target_chat, targets_file, invites_per_account, delay_min, delay_max)
        VALUES (?, ?, ?, ?, ?)""",
        (target_chat, targets_file, invites_per_account, delay_min, delay_max),
    )
    task_id = cursor.lastrowid
    await db.commit()
    await db.close()
    await log_event("info", "inviter", f"Invite task #{task_id} created for {target_chat}")
    return {"success": True, "task_id": task_id}


async def _mark_spam_block(account_id: int):
    db = await get_db()
    await db.execute("UPDATE accounts SET status = 'spam-block' WHERE id = ?", (account_id,))
    await db.commit()
    await db.close()


async def _do_invite_task(task_id: int):
    """Background worker: invites users rotating between all active accounts."""
    from ..services.telegram_engine import telegram_engine
    from telethon.tl.functions.channels import InviteToChannelRequest
    from telethon.errors import (
        FloodWaitError, PeerFloodError, UserPrivacyRestrictedError,
        UserAlreadyParticipantError, InputUserDeactivatedError
    )

    db = await get_db()
    cursor = await db.execute(
        "SELECT target_chat, targets_file, invites_per_account, delay_min, delay_max FROM invite_tasks WHERE id = ?",
        (task_id,)
    )
    task_data = await cursor.fetchone()
    await db.close()

    if not task_data:
        return

    target_chat    = task_data[0]
    targets_file   = task_data[1]
    per_account    = task_data[2] or 15
    delay_min      = task_data[3] or 30
    delay_max      = task_data[4] or 60

    # Load users to invite
    targets = []
    if targets_file:
        path = os.path.join(EXPORTS_DIR, targets_file)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                targets = [l.strip() for l in f if l.strip()]

    if not targets:
        await log_event("warn", "inviter", f"Task #{task_id}: no users to invite")
        db = await get_db()
        await db.execute("UPDATE invite_tasks SET status = 'done' WHERE id = ?", (task_id,))
        await db.commit()
        await db.close()
        return

    await log_event("info", "inviter",
                    f"Task #{task_id}: {len(targets)} users → {target_chat}")

    success_count = 0
    error_count = 0
    target_index = 0

    while task_id in _active_invite_task_loops and target_index < len(targets):
        # Pick a fresh random active account each rotation
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE status = 'active' ORDER BY RANDOM() LIMIT 1"
        )
        acc_row = await cursor.fetchone()
        await db.close()

        if not acc_row:
            await log_event("warn", "inviter", f"Task #{task_id}: no active accounts left")
            break

        account = {
            "id": acc_row[0], "phone": acc_row[1], "session_file": acc_row[2],
            "proxy_type": acc_row[3], "proxy_host": acc_row[4], "proxy_port": acc_row[5],
            "proxy_username": acc_row[6], "proxy_password": acc_row[7]
        }

        try:
            await telegram_engine.connect_account(account)
            client = telegram_engine.get_client(account["id"])
        except Exception as e:
            await log_event("warn", "inviter",
                            f"Task #{task_id}: cannot connect {account['phone']}: {e}")
            continue

        if not client:
            continue

        # Resolve target channel once per account session
        try:
            clean_tc = target_chat.strip()
            if "t.me/" in clean_tc and not ("t.me/+" in clean_tc or "joinchat/" in clean_tc):
                clean_tc = clean_tc.split("t.me/")[-1].split("/")[0].split("?")[0]
            clean_tc = clean_tc.lstrip("@")
            if clean_tc.isdigit():
                clean_tc = int(clean_tc)
            channel_entity = await client.get_entity(clean_tc)
        except Exception as e:
            await log_event("warn", "inviter",
                            f"Task #{task_id}: cannot resolve {target_chat}: {e}")
            if "FloodWait" in str(e):
                await _mark_spam_block(account["id"])
            break

        sent_this_account = 0

        while (sent_this_account < per_account
               and target_index < len(targets)
               and task_id in _active_invite_task_loops):

            user_str = targets[target_index]
            target_index += 1

            try:
                clean_u = user_str.strip()
                if "t.me/" in clean_u:
                    clean_u = clean_u.split("t.me/")[-1].split("/")[0].split("?")[0]
                clean_u = clean_u.lstrip("@")
                if clean_u.isdigit():
                    clean_u = int(clean_u)
                user_entity = await client.get_entity(clean_u)
                await client(InviteToChannelRequest(channel_entity, [user_entity]))
                success_count += 1
                sent_this_account += 1
                await log_event("info", "inviter",
                                f"[{account['phone']}] invited {user_str} → {target_chat}")

                delay = random.randint(delay_min, delay_max)
                await asyncio.sleep(delay)

            except UserAlreadyParticipantError:
                await log_event("info", "inviter", f"{user_str} already in {target_chat}")

            except UserPrivacyRestrictedError:
                error_count += 1
                await log_event("warn", "inviter",
                                f"{user_str}: privacy restricted, skipping")

            except InputUserDeactivatedError:
                error_count += 1
                await log_event("warn", "inviter", f"{user_str}: account deactivated")

            except FloodWaitError as e:
                await log_event("warn", "inviter",
                                f"[{account['phone']}] FloodWait {e.seconds}s → spam-block")
                await _mark_spam_block(account["id"])
                break

            except PeerFloodError:
                await log_event("warn", "inviter",
                                f"[{account['phone']}] PeerFlood → spam-block")
                await _mark_spam_block(account["id"])
                break

            except Exception as e:
                error_count += 1
                await log_event("warn", "inviter",
                                f"[{account['phone']}] → {user_str}: {str(e)[:100]}")
                await asyncio.sleep(3)

    # Save final stats
    if task_id in _active_invite_task_loops:
        del _active_invite_task_loops[task_id]

    db = await get_db()
    await db.execute(
        "UPDATE invite_tasks SET status = 'done', total_invited = ?, total_failed = ? WHERE id = ?",
        (success_count, error_count, task_id)
    )
    await db.commit()
    await db.close()
    await log_event("info", "inviter",
                    f"Task #{task_id} done: {success_count} invited, {error_count} failed")


@router.post("/{task_id}/start")
async def start_inviting(task_id: int):
    db = await get_db()
    cursor = await db.execute("SELECT id FROM invite_tasks WHERE id = ?", (task_id,))
    if not await cursor.fetchone():
        await db.close()
        raise HTTPException(404, "Task not found")
    await db.execute("UPDATE invite_tasks SET status = 'running' WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()

    if task_id not in _active_invite_task_loops:
        _active_invite_task_loops[task_id] = True
        asyncio.create_task(_do_invite_task(task_id))

    await log_event("info", "inviter", f"Invite task #{task_id} started")
    return {"success": True}


@router.post("/{task_id}/stop")
async def stop_inviting(task_id: int):
    _active_invite_task_loops.pop(task_id, None)
    db = await get_db()
    await db.execute("UPDATE invite_tasks SET status = 'stopped' WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()
    await log_event("info", "inviter", f"Invite task #{task_id} stopped")
    return {"success": True}


@router.delete("/{task_id}")
async def delete_invite_task(task_id: int):
    _active_invite_task_loops.pop(task_id, None)
    db = await get_db()
    await db.execute("DELETE FROM invite_tasks WHERE id = ?", (task_id,))
    await db.commit()
    await db.close()
    return {"success": True}


@router.get("/tasks")
async def list_invite_tasks():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM invite_tasks ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0], "target_chat": row[1], "invites_per_account": row[2],
            "delay_min": row[3], "delay_max": row[4], "status": row[5],
            "total_invited": row[6], "total_failed": row[7],
            "targets_file": row[9] if len(row) > 9 else None,
            "created_at": row[8],
        })
    return {"tasks": tasks}
