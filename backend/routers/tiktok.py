from fastapi import APIRouter, HTTPException, Form, UploadFile, File, BackgroundTasks
from typing import List
import os
import json
import uuid
import asyncio
from ..database import get_db, log_event
from .media import MEDIA_DIR, cleanup_file
from tiktok_uploader.upload import upload_video

router = APIRouter(prefix="/api/tiktok", tags=["tiktok"])

COOKIES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_cookies")
os.makedirs(COOKIES_DIR, exist_ok=True)

@router.get("/accounts")
async def list_accounts():
    db = await get_db()
    cursor = await db.execute("SELECT id, username, status, created_at FROM tiktok_accounts")
    rows = await cursor.fetchall()
    await db.close()
    return [{"id": r[0], "username": r[1], "status": r[2], "created_at": r[3]} for r in rows]

@router.post("/accounts")
async def add_account(username: str = Form(...), cookies: str = Form(...)):
    # Validate cookies are JSON
    try:
        json.loads(cookies)
    except:
        raise HTTPException(400, "Invalid cookies format. Must be JSON.")
        
    db = await get_db()
    await db.execute(
        "INSERT INTO tiktok_accounts (username, cookie_data) VALUES (?, ?)",
        (username, cookies)
    )
    await db.commit()
    await db.close()
    return {"success": True}

@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int):
    db = await get_db()
    await db.execute("DELETE FROM tiktok_accounts WHERE id = ?", (account_id,))
    await db.commit()
    await db.close()
    return {"success": True}

async def _do_tiktok_post(video_path: str, description: str, account_ids: List[int], aggressiveness: int, frame_style: str):
    """Background task to uniqualize and post to multiple TikTok accounts."""
    from .media import uniqualize_media_logic # I need to extract logic from media.py
    
    db = await get_db()
    
    for acc_id in account_ids:
        cursor = await db.execute("SELECT username, cookie_data FROM tiktok_accounts WHERE id = ?", (acc_id,))
        acc = await cursor.fetchone()
        if not acc: continue
        
        username, cookie_data = acc
        
        # 1. Create unique version of the video for this account
        unique_video_path = await uniqualize_media_logic(video_path, aggressiveness, frame_style)
        
        # 2. Save cookies to temp file
        cookie_path = os.path.join(COOKIES_DIR, f"{uuid.uuid4()}.json")
        with open(cookie_path, "w") as f:
            f.write(cookie_data)
            
        try:
            await log_event("info", "tiktok", f"Starting upload for @{username}")
            
            # 3. Upload using tiktok-uploader (runs in a separate thread/process potentially)
            # Since upload_video is likely synchronous, we wrap it
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: upload_video(
                unique_video_path,
                description=description,
                cookies=cookie_path,
                browser="chromium"
            ))
            
            await log_event("info", "tiktok", f"Successfully posted to @{username}")
        except Exception as e:
            await log_event("error", "tiktok", f"Failed to post to @{username}: {str(e)}")
        finally:
            if os.path.exists(cookie_path): os.remove(cookie_path)
            if os.path.exists(unique_video_path): os.remove(unique_video_path)
            
    await db.close()
    if os.path.exists(video_path): os.remove(video_path)

@router.post("/auto-post")
async def auto_post(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: str = Form(...),
    account_ids: str = Form(...), # JSON string of IDs
    aggressiveness: int = Form(1),
    frame_style: str = Form("none")
):
    try:
        ids = json.loads(account_ids)
    except:
        raise HTTPException(400, "Invalid account IDs")
        
    # Save original video to temp
    task_id = str(uuid.uuid4())
    orig_path = os.path.join(MEDIA_DIR, f"orig_{task_id}_{file.filename}")
    content = await file.read()
    with open(orig_path, "wb") as f:
        f.write(content)
        
    background_tasks.add_task(_do_tiktok_post, orig_path, description, ids, aggressiveness, frame_style)
    return {"success": True, "message": f"Started posting to {len(ids)} accounts"}
