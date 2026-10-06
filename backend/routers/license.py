"""
License key management system for Phantom TG Harvester.
"""
import secrets
import string
from fastapi import APIRouter, HTTPException, Form
from datetime import datetime, timedelta
from ..database import get_db

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

    return {"key": key, "expires_at": expires_at, "days": days}


@router.get("/all")
async def list_keys(master_token: str):
    """List all license keys (admin only)."""
    MASTER_TOKEN = "phantom_master_2025"
    if master_token != MASTER_TOKEN:
        raise HTTPException(403, "Invalid master token")

    db = await get_db()
    cursor = await db.execute(
        "SELECT key, status, activated_at, expires_at, note FROM license_keys ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    await db.close()

    return [
        {
            "key": r[0],
            "status": r[1],
            "activated_at": r[2],
            "expires_at": r[3],
            "note": r[4]
        }
        for r in rows
    ]


@router.post("/activate")
async def activate_key(key: str = Form(...)):
    """Activate a license key. Called on first login."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT key, status, expires_at FROM license_keys WHERE key = ?",
        (key,)
    )
    row = await cursor.fetchone()

    if not row:
        await db.close()
        raise HTTPException(400, "Невірний ключ ліцензії")

    status, expires_at = row[1], row[2]

    if status == "used":
        await db.close()
        raise HTTPException(400, "Цей ключ вже був використаний")

    if status == "revoked":
        await db.close()
        raise HTTPException(400, "Цей ключ заблоковано")

    # Check expiry
    if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
        await db.close()
        raise HTTPException(400, "Термін дії ключа закінчився")

    # Mark as used
    await db.execute(
        "UPDATE license_keys SET status = 'used', activated_at = ? WHERE key = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), key)
    )
    # Store in settings as active license
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_license', ?)",
        (key,)
    )
    await db.commit()
    await db.close()

    return {"success": True, "expires_at": expires_at, "message": "Ліцензія активована!"}


@router.get("/status")
async def get_status():
    """Check current license status."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'active_license'"
    )
    row = await cursor.fetchone()

    if not row:
        await db.close()
        return {"licensed": False}

    active_key = row[0]
    cursor2 = await db.execute(
        "SELECT expires_at, status FROM license_keys WHERE key = ?",
        (active_key,)
    )
    lic = await cursor2.fetchone()
    await db.close()

    if not lic:
        return {"licensed": False}

    expires_at = lic[0]
    if datetime.now() > datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S"):
        return {"licensed": False, "reason": "expired"}

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
    return {"success": True}
