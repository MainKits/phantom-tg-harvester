"""
Account Manager API — manage Telegram accounts, sessions, and proxies.
"""

import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from datetime import datetime

from ..database import get_db, log_event, backup_session_to_supabase, sync_to_supabase_async

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


@router.get("/")
async def list_accounts():
    """Get all accounts with their statuses."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM accounts ORDER BY created_at DESC")
    rows = await cursor.fetchall()

    # If local cache is empty, pull immediately from Supabase cloud
    if not rows:
        from ..database import sync_from_supabase
        try:
            await sync_from_supabase()
            cursor = await db.execute("SELECT * FROM accounts ORDER BY created_at DESC")
            rows = await cursor.fetchall()
        except Exception:
            pass
    
    accounts = []
    for row in rows:
        accounts.append({
            "id": row[0],
            "phone": row[1],
            "session_file": row[2],
            "proxy_type": row[3],
            "proxy_host": row[4],
            "proxy_port": row[5],
            "proxy_username": row[6],
            "proxy_password": row[7],
            "status": row[8],
            "messages_sent_today": row[9],
            "invites_sent_today": row[10],
            "last_used": row[11],
            "created_at": row[12],
            "flood_wait_until": row[13],
        })
    
    await db.close()
    return {"accounts": accounts}


@router.post("/add")
async def add_account(
    phone: str = Form(...),
    proxy_type: Optional[str] = Form(None),
    proxy_host: Optional[str] = Form(None),
    proxy_port: Optional[int] = Form(None),
    proxy_username: Optional[str] = Form(None),
    proxy_password: Optional[str] = Form(None),
):
    """Add a new account manually."""
    db = await get_db()
    
    try:
        await db.execute(
            """INSERT INTO accounts 
            (phone, proxy_type, proxy_host, proxy_port, proxy_username, proxy_password, status) 
            VALUES (?, ?, ?, ?, ?, ?, 'inactive')""",
            (phone, proxy_type, proxy_host, proxy_port, proxy_username, proxy_password),
        )
        await db.commit()
        await log_event("info", "accounts", f"Account {phone} added")
    except Exception as e:
        await db.close()
        raise HTTPException(status_code=400, detail=str(e))
    
    await db.close()
    return {"success": True, "message": f"Account {phone} added"}


@router.post("/upload-sessions")
async def upload_sessions(files: list[UploadFile] = File(...)):
    """Upload .session files for bulk account import with automatic status verification."""
    from telethon import TelegramClient
    from ..services.telegram_engine import get_api_credentials
    
    imported = []
    db = await get_db()
    api_id, api_hash = await get_api_credentials()
    
    for file in files:
        if not file.filename.endswith(".session"):
            continue
        
        # Save session file
        dest = os.path.join(SESSIONS_DIR, file.filename)
        with open(dest, "wb") as f:
            content = await file.read()
            f.write(content)
        
        sname = file.filename.replace(".session", "")
        phone = sname
        status = "inactive"
        
        # Connect to verify if session is active
        if api_id and api_hash:
            try:
                client = TelegramClient(os.path.join(SESSIONS_DIR, sname), api_id, api_hash)
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    if me and me.phone:
                        phone = f"+{me.phone}"
                    status = "active"
                await client.disconnect()
            except Exception:
                pass
        
        try:
            # Check if this session or phone exists
            cursor = await db.execute("SELECT id FROM accounts WHERE session_file = ? OR phone = ?", (file.filename, phone))
            existing = await cursor.fetchone()
            if existing:
                await db.execute(
                    "UPDATE accounts SET phone = ?, session_file = ?, status = ? WHERE id = ?",
                    (phone, file.filename, status, existing[0])
                )
            else:
                await db.execute(
                    "INSERT INTO accounts (phone, session_file, status) VALUES (?, ?, ?)",
                    (phone, file.filename, status),
                )
            imported.append(phone)
            # Cloud backup to Supabase
            backup_session_to_supabase(phone, file.filename)
        except Exception:
            pass
    
    await db.commit()
    await log_event("info", "accounts", f"Імпортовано {len(imported)} сесій")
    await db.close()
    
    return {"success": True, "imported": len(imported), "phones": imported}


@router.put("/{account_id}/proxy")
async def update_proxy(
    account_id: int,
    proxy_type: str = Form(...),
    proxy_host: str = Form(...),
    proxy_port: int = Form(...),
    proxy_username: Optional[str] = Form(None),
    proxy_password: Optional[str] = Form(None),
):
    """Update proxy settings for an account."""
    db = await get_db()
    
    await db.execute(
        """UPDATE accounts SET 
        proxy_type = ?, proxy_host = ?, proxy_port = ?, 
        proxy_username = ?, proxy_password = ? 
        WHERE id = ?""",
        (proxy_type, proxy_host, proxy_port, proxy_username, proxy_password, account_id),
    )
    await db.commit()
    await db.close()
    
    return {"success": True}


@router.put("/{account_id}/status")
async def update_status(account_id: int, status: str = Form(...)):
    """Update account status."""
    valid_statuses = ["active", "inactive", "spam-block", "banned"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    db = await get_db()
    await db.execute("UPDATE accounts SET status = ? WHERE id = ?", (status, account_id))
    await db.commit()
    await db.close()
    
    return {"success": True}

@router.post("/{account_id}/check")
async def check_account(account_id: int):
    """Check account status via Telegram API and SpamBot."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    acc_row = await cursor.fetchone()
    if not acc_row:
        await db.close()
        raise HTTPException(status_code=404, detail="Account not found")
        
    account = {
        "id": acc_row[0], "phone": acc_row[1], "session_file": acc_row[2],
        "proxy_type": acc_row[3], "proxy_host": acc_row[4], "proxy_port": acc_row[5],
        "proxy_username": acc_row[6], "proxy_password": acc_row[7]
    }
    
    from ..services.telegram_engine import telegram_engine
    status = await telegram_engine.check_account_status(account)
    
    await db.execute("UPDATE accounts SET status = ? WHERE id = ?", (status, account_id))
    await db.commit()
    await db.close()
    
    return {"success": True, "status": status}


@router.delete("/{account_id}")
async def delete_account(account_id: int):
    """Delete an account and its session file."""
    db = await get_db()
    
    cursor = await db.execute("SELECT phone, session_file FROM accounts WHERE id = ?", (account_id,))
    row = await cursor.fetchone()
    
    if not row:
        await db.close()
        raise HTTPException(status_code=404, detail="Account not found")
        
    # First, ensure the client is disconnected to release file lock
    from ..services.telegram_engine import telegram_engine
    client = telegram_engine.get_client(account_id)
    if client:
        try:
            await client.disconnect()
        except:
            pass
        if account_id in telegram_engine._connected:
            telegram_engine._connected[account_id] = False
    
    # Delete session file if exists
    if row[1]:
        session_path = os.path.join(SESSIONS_DIR, row[1])
        if os.path.exists(session_path):
            try:
                os.remove(session_path)
            except Exception as e:
                # Log but do not fail completely
                await log_event("warn", "accounts", f"Could not remove session file: {str(e)}")
    
    await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    await db.commit()

    # Delete from Supabase cloud
    from ..database import get_supabase_client
    sb = get_supabase_client()
    if sb and row[0]:
        try:
            sb.table("accounts").delete().eq("phone", row[0]).execute()
        except Exception:
            pass

    await log_event("info", "accounts", f"Account {row[0]} deleted")
    await db.close()
    
    return {"success": True}


@router.post("/send-code")
async def send_auth_code(phone: str = Form(...)):
    """Send authorization code for manual account login."""
    from ..services.telegram_engine import telegram_engine
    
    db = await get_db()
    cursor = await db.execute("SELECT * FROM accounts WHERE phone = ?", (phone,))
    acc_row = await cursor.fetchone()
    
    proxy_dict = None
    if acc_row:
        proxy_dict = {
            "type": acc_row[3], "host": acc_row[4], "port": acc_row[5],
            "username": acc_row[6], "password": acc_row[7]
        }
    
    try:
        result = await telegram_engine.send_code(phone, proxy=proxy_dict)
        clean_phone = result.get("clean_phone", phone)
        
        # If phone was different, update in DB
        if acc_row and clean_phone != phone:
            await db.execute("UPDATE accounts SET phone = ? WHERE id = ?", (clean_phone, acc_row[0]))
            await db.commit()
            
        await db.close()
        await log_event("info", "accounts", f"Код авторизації надіслано на {clean_phone}")
        return {"success": True, "phone_code_hash": result["phone_code_hash"], "phone": clean_phone}
    except Exception as e:
        await db.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify-code")
async def verify_auth_code(
    phone: str = Form(...),
    code: str = Form(...),
    phone_code_hash: str = Form(...),
    password: Optional[str] = Form(None),
):
    """Verify authorization code and complete login."""
    from ..services.telegram_engine import telegram_engine
    
    try:
        result = await telegram_engine.sign_in(phone, code, phone_code_hash, password=password)
        if result.get("needs_2fa"):
            return {"needs_2fa": True, "message": result.get("message", "Введіть 2FA пароль")}
        
        clean_phone = result.get("phone", phone)
        session_file = clean_phone.replace("+", "") + ".session"
        
        # Add / update in database
        db = await get_db()
        cursor = await db.execute("SELECT id FROM accounts WHERE phone = ? OR phone = ?", (clean_phone, phone))
        row = await cursor.fetchone()
        if row:
            await db.execute(
                """UPDATE accounts SET phone = ?, session_file = ?, status = 'active' WHERE id = ?""",
                (clean_phone, session_file, row[0]),
            )
        else:
            await db.execute(
                """INSERT INTO accounts (phone, session_file, status) VALUES (?, ?, 'active')""",
                (clean_phone, session_file),
            )
        await db.commit()
        await db.close()

        # Cloud backup to Supabase
        backup_session_to_supabase(clean_phone, session_file)
        
        await log_event("info", "accounts", f"Акаунт {clean_phone} успішно авторизовано")
        return {"success": True, "user": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/join-chat")
async def join_chat(account_id: int = Form(...), chat_link: str = Form(...)):
    """Make an account join a channel or group by link/username."""
    from ..services.telegram_engine import telegram_engine

    db = await get_db()
    cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    acc_row = await cursor.fetchone()
    await db.close()

    if not acc_row:
        raise HTTPException(404, "Account not found")

    account = {
        "id": acc_row[0], "phone": acc_row[1], "session_file": acc_row[2],
        "proxy_type": acc_row[3], "proxy_host": acc_row[4], "proxy_port": acc_row[5],
        "proxy_username": acc_row[6], "proxy_password": acc_row[7]
    }

    try:
        await telegram_engine.connect_account(account)
        client = telegram_engine.get_client(account_id)
        if not client:
            raise HTTPException(400, "Акаунт не авторизований")
        await telegram_engine.join_chat(client, chat_link)
        await log_event("info", "accounts", f"{account['phone']} joined {chat_link}")
        return {"success": True}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/post-comment")
async def post_comment(
    account_id: int = Form(...),
    channel: str = Form(...),
    post_id: int = Form(...),
    text: str = Form(...)
):
    """Post a comment to a channel post via the linked discussion group."""
    from ..services.telegram_engine import telegram_engine

    db = await get_db()
    cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    acc_row = await cursor.fetchone()
    await db.close()

    if not acc_row:
        raise HTTPException(404, "Account not found")

    account = {
        "id": acc_row[0], "phone": acc_row[1], "session_file": acc_row[2],
        "proxy_type": acc_row[3], "proxy_host": acc_row[4], "proxy_port": acc_row[5],
        "proxy_username": acc_row[6], "proxy_password": acc_row[7]
    }

    try:
        await telegram_engine.connect_account(account)
        client = telegram_engine.get_client(account_id)
        if not client:
            raise HTTPException(400, "Акаунт не авторизований")
        await telegram_engine.post_comment(client, channel, post_id, text)
        await log_event("info", "accounts", f"{account['phone']} commented on {channel}:{post_id}")
        return {"success": True}
    except Exception as e:
        raise HTTPException(400, str(e))
