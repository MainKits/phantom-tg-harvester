"""
System & Updates API — version management, update checking, and auto-install.
"""
import os
import sys
import tempfile
import subprocess
import asyncio
import aiohttp
from fastapi import APIRouter, Form, HTTPException
from ..database import get_db, log_event

router = APIRouter(prefix="/api/system", tags=["system"])

CURRENT_VERSION = "1.0.0"
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/MainKits/phantom-releases/main/version.json"


def compare_versions(v1: str, v2: str) -> int:
    """Returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal."""
    def parse(v):
        return [int(x) for x in v.lstrip("v").split(".") if x.isdigit()]
    try:
        p1, p2 = parse(v1), parse(v2)
        for a, b in zip(p1, p2):
            if a > b:
                return 1
            if a < b:
                return -1
        return 1 if len(p1) > len(p2) else (-1 if len(p1) < len(p2) else 0)
    except Exception:
        return 0


@router.get("/version")
async def get_version():
    return {"version": CURRENT_VERSION}


@router.get("/check-update")
async def check_update():
    """Check for app updates via configured URL."""
    db = await get_db()
    cursor = await db.execute("SELECT value FROM settings WHERE key = 'update_url'")
    row = await cursor.fetchone()
    await db.close()

    update_url = row[0] if row and row[0] else DEFAULT_UPDATE_URL

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(update_url) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    latest_version = data.get("version", CURRENT_VERSION)
                    has_update = compare_versions(latest_version, CURRENT_VERSION) > 0
                    return {
                        "has_update": has_update,
                        "current_version": CURRENT_VERSION,
                        "latest_version": latest_version,
                        "download_url": data.get("download_url", ""),
                        "changelog": data.get("changelog", "Оновлення стабільності та нові функції."),
                        "update_url": update_url
                    }
    except Exception as e:
        return {
            "has_update": False,
            "current_version": CURRENT_VERSION,
            "error": str(e),
            "update_url": update_url
        }

    return {"has_update": False, "current_version": CURRENT_VERSION, "update_url": update_url}


@router.post("/set-update-url")
async def set_update_url(url: str = Form(...)):
    """Set custom update URL."""
    db = await get_db()
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('update_url', ?)", (url.strip(),))
    await db.commit()
    await db.close()
    return {"success": True, "update_url": url.strip()}


@router.post("/install-update")
async def install_update(download_url: str = Form(...)):
    """Download update installer and launch it."""
    if not download_url.startswith("http"):
        raise HTTPException(400, "Невірне посилання для завантаження")

    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, "Phantom_Update_Setup.exe")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    raise HTTPException(400, f"Не вдалося завантажити інсталятор: HTTP {resp.status}")
                with open(installer_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)

        # Launch the installer
        subprocess.Popen([installer_path], shell=True)
        await log_event("info", "system", f"Launched update installer: {installer_path}")

        asyncio.create_task(_exit_later())
        return {"success": True, "message": "Інсталятор запущено, додаток оновлюється..."}

    except Exception as e:
        raise HTTPException(400, f"Помилка завантаження оновлення: {str(e)}")


async def _exit_later():
    await asyncio.sleep(2)
    os._exit(0)


# ─── System Toast Alerts ───────────────────────────────────────────────────────
_system_alerts = []

def add_system_alert(alert_type: str, phone: str, message: str, details: str = ""):
    """Store a toast alert in memory for the frontend notification system."""
    import time
    alert = {
        "id": f"{int(time.time() * 1000)}",
        "type": alert_type,  # 'spam-block' | 'banned' | 'warn'
        "phone": phone,
        "message": message,
        "details": details,
        "timestamp": int(time.time()),
        "read": False
    }
    _system_alerts.append(alert)
    if len(_system_alerts) > 30:
        _system_alerts.pop(0)
    return alert


@router.get("/alerts")
async def get_system_alerts():
    """Get recent unacknowledged alerts from the last 10 minutes."""
    import time
    now = time.time()
    recent = [a for a in _system_alerts if (now - a["timestamp"]) < 600 and not a.get("read", False)]
    return {"alerts": recent}


@router.post("/alerts/ack")
async def ack_system_alert(alert_id: str = Form(...)):
    """Acknowledge / dismiss a toast alert."""
    for a in _system_alerts:
        if a["id"] == alert_id:
            a["read"] = True
    return {"success": True}

