"""
License key management system for Phantom TG Harvester.
"""
import secrets
import string
from fastapi import APIRouter, HTTPException, Form
from datetime import datetime, timedelta
from typing import Optional
from ..database import get_db, get_supabase_client, sync_to_supabase_async

router = APIRouter(prefix="/api/license", tags=["license"])


def _generate_key() -> str:
    """Generate a key in format XXXX-XXXX-XXXX-XXXX."""
    chars = string.ascii_uppercase + string.digits
    groups = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
    return '-'.join(groups)


@router.post("/generate")
async def generate_key(
    days: int = Form(30),
    note: str = Form(""),
    master_token: str = Form(...)
):
    """Generate a new license key. Requires master admin token."""
    # Simple hardcoded master token — change this to something secret!
    MASTER_TOKEN = "phantom_master_2025"
    if master_token != MASTER_TOKEN:
        raise HTTPException(403, "Invalid master token")

    key = _generate_key()
    expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    db = await get_db()
    await db.execute(
        "INSERT INTO license_keys (key, expires_at, note) VALUES (?, ?, ?)",
        (key, expires_at, note)
    )
    await db.commit()
    await db.close()

    # Cloud sync to Supabase
    sync_to_supabase_async("license_keys", {
        "key": key,
        "status": "active",
        "expires_at": expires_at,
        "note": note or ""
    }, on_conflict="key")

    return {"key": key, "expires_at": expires_at, "days": days}


@router.get("/all")
async def list_keys(master_token: str):
    """List all license keys from Supabase cloud and local database."""
    MASTER_TOKEN = "phantom_master_2025"
    if master_token != MASTER_TOKEN:
        raise HTTPException(403, "Invalid master token")

    keys_map = {}

    # 1. Fetch from Supabase cloud if connected
    sb = get_supabase_client()
    if sb:
        try:
            res = sb.table("license_keys").select("*").execute()
            if res.data:
                for k in res.data:
                    k_str = k.get("key")
                    if k_str:
                        keys_map[k_str] = {
                            "key": k_str,
                            "status": k.get("status", "active"),
                            "activated_at": k.get("activated_at"),
                            "expires_at": str(k.get("expires_at", "")),
                            "note": k.get("note", ""),
                            "created_at": str(k.get("created_at", ""))
                        }
        except Exception as e:
            print(f"[Supabase] list_keys note: {e}")

    # 2. Fetch from local SQLite and merge
    try:
        db = await get_db()
        cursor = await db.execute(
            "SELECT key, status, activated_at, expires_at, note, created_at FROM license_keys ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        await db.close()

        for r in rows:
            k_str = r[0]
            if k_str not in keys_map:
                keys_map[k_str] = {
                    "key": k_str,
                    "status": r[1],
                    "activated_at": r[2],
                    "expires_at": r[3],
                    "note": r[4],
                    "created_at": r[5]
                }
    except Exception as e:
        print(f"[SQLite] list_keys error: {e}")

    # Return as list sorted with newest keys first
    result = list(keys_map.values())
    result.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return result


@router.post("/activate")
async def activate_key(key: str = Form(...)):
    """Activate a license key. Called on first login."""
    clean_key = key.strip()
    db = await get_db()

    # Master admin keys
    admin_keys = ["phantom_master_2025", "PHANTOM-PRO-2026", "PHANTOM-ADMIN", "TIM8-LK78-NX72-HDCY"]
    if clean_key in admin_keys:
        expires_at = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "INSERT OR REPLACE INTO license_keys (key, status, activated_at, expires_at, note) VALUES (?, 'active', ?, ?, 'Master Admin')",
            (clean_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at)
        )
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_license', ?)",
            (clean_key,)
        )
        await db.commit()
        await db.close()
        return {"success": True, "expires_at": expires_at, "message": "Адміністраторська ліцензія активована!"}

    cursor = await db.execute(
        "SELECT key, status, expires_at FROM license_keys WHERE key = ?",
        (clean_key,)
    )
    row = await cursor.fetchone()

    if not row:
        # Check Supabase cloud fallback
        sb = get_supabase_client()
        if sb:
            try:
                res = sb.table("license_keys").select("*").eq("key", clean_key).execute()
                if res.data:
                    k_data = res.data[0]
                    await db.execute(
                        "INSERT OR REPLACE INTO license_keys (key, status, activated_at, expires_at, note) VALUES (?, ?, ?, ?, ?)",
                        (k_data.get("key"), k_data.get("status", "active"), k_data.get("activated_at"), str(k_data.get("expires_at", "")), k_data.get("note", ""))
                    )
                    await db.commit()
                    row = (k_data.get("key"), k_data.get("status", "active"), str(k_data.get("expires_at", "")))
            except Exception as e:
                print(f"[Supabase] activate lookup error: {e}")

    if not row:
        await db.close()
        raise HTTPException(400, "Невірний ключ ліцензії")

    status, expires_at = row[1], row[2]

    if status == "revoked":
        await db.close()
        raise HTTPException(400, "Цей ключ заблоковано")

    # Check expiry
    try:
        if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
            await db.close()
            raise HTTPException(400, "Термін дії ключа закінчився")
    except Exception:
        pass

    # Mark as active
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE license_keys SET status = 'active', activated_at = ? WHERE key = ?",
        (now_str, clean_key)
    )
    # Store in settings as active license
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_license', ?)",
        (clean_key,)
    )
    await db.commit()
    await db.close()

    # Sync back to Supabase
    sync_to_supabase_async("license_keys", {
        "key": clean_key,
        "status": "active",
        "activated_at": now_str
    }, on_conflict="key")
    sync_to_supabase_async("settings", {
        "key": "active_license",
        "value": clean_key
    }, on_conflict="key")

    return {"success": True, "expires_at": expires_at, "message": "Ліцензія активована!"}


@router.get("/status")
async def get_status(key: Optional[str] = None):
    """Check current license status for web client or local system."""
    admin_keys = ["phantom_master_2025", "PHANTOM-PRO-2026", "PHANTOM-ADMIN", "TIM8-LK78-NX72-HDCY"]
    
    # 1. If key is passed by web client
    if key and key.strip():
        clean_key = key.strip()
        if clean_key in admin_keys:
            return {"licensed": True, "key": clean_key, "expires_at": "2036-12-31 23:59:59"}

        db = await get_db()
        cursor = await db.execute(
            "SELECT expires_at, status FROM license_keys WHERE key = ?",
            (clean_key,)
        )
        lic = await cursor.fetchone()

        if not lic:
            # Check Supabase cloud
            sb = get_supabase_client()
            if sb:
                try:
                    res = sb.table("license_keys").select("*").eq("key", clean_key).execute()
                    if res.data:
                        k_data = res.data[0]
                        lic = (str(k_data.get("expires_at", "")), k_data.get("status", "active"))
                        await db.execute(
                            "INSERT OR REPLACE INTO license_keys (key, status, activated_at, expires_at, note) VALUES (?, ?, ?, ?, ?)",
                            (k_data.get("key"), k_data.get("status", "active"), k_data.get("activated_at"), str(k_data.get("expires_at", "")), k_data.get("note", ""))
                        )
                        await db.commit()
                except Exception as e:
                    print(f"[Supabase] get_status lookup note: {e}")

        await db.close()

        if not lic:
            return {"licensed": False}

        expires_at, status = lic[0], lic[1]
        if status == "revoked":
            return {"licensed": False, "reason": "revoked"}

        try:
            if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
                return {"licensed": False, "reason": "expired"}
        except Exception:
            pass

        return {"licensed": True, "key": clean_key, "expires_at": expires_at}

    # 2. Fallback to settings.active_license (for Electron desktop app)
    db = await get_db()
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'active_license'"
    )
    row = await cursor.fetchone()

    if not row:
        await db.close()
        return {"licensed": False}

    active_key = row[0]
    if active_key in admin_keys:
        await db.close()
        return {"licensed": True, "key": active_key, "expires_at": "2036-12-31 23:59:59"}

    cursor2 = await db.execute(
        "SELECT expires_at, status FROM license_keys WHERE key = ?",
        (active_key,)
    )
    lic = await cursor2.fetchone()
    await db.close()

    if not lic:
        return {"licensed": False}

    expires_at = lic[0]
    try:
        if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
            return {"licensed": False, "reason": "expired"}
    except Exception:
        pass

    return {
        "licensed": True,
        "key": active_key,
        "expires_at": expires_at
    }


@router.post("/revoke")
async def revoke_key(key: str = Form(...), master_token: str = Form(...)):
    """Revoke a license key."""
    MASTER_TOKEN = "phantom_master_2025"
    if master_token != MASTER_TOKEN:
        raise HTTPException(403, "Invalid master token")

    db = await get_db()
    await db.execute("UPDATE license_keys SET status = 'revoked' WHERE key = ?", (key,))
    await db.commit()
    await db.close()

    # Cloud sync
    sb = get_supabase_client()
    if sb:
        try:
            sb.table("license_keys").update({"status": "revoked"}).eq("key", key).execute()
        except Exception:
            pass

    return {"success": True}


@router.post("/delete")
async def delete_key(key: str = Form(...), master_token: str = Form(...)):
    """Permanently delete a license key."""
    MASTER_TOKEN = "phantom_master_2025"
    if master_token != MASTER_TOKEN:
        raise HTTPException(403, "Invalid master token")

    db = await get_db()
    await db.execute("DELETE FROM license_keys WHERE key = ?", (key,))
    await db.commit()
    await db.close()

    # Cloud sync
    sb = get_supabase_client()
    if sb:
        try:
            sb.table("license_keys").delete().eq("key", key).execute()
        except Exception:
            pass

    return {"success": True}
