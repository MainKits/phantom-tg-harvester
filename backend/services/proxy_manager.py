"""
Proxy Manager — validates and tests proxy connections.
"""

import asyncio
import aiohttp
import socks
from typing import Optional


async def test_proxy(
    proxy_type: str,
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> dict:
    """
    Test a proxy connection by making a request to a test endpoint.
    Returns dict with 'working' bool and 'ip' if successful.
    """
    proxy_url = ""
    
    if proxy_type.lower() == "http":
        if username and password:
            proxy_url = f"http://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"http://{host}:{port}"
    elif proxy_type.lower() in ("socks5", "socks4"):
        if username and password:
            proxy_url = f"{proxy_type.lower()}://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"{proxy_type.lower()}://{host}:{port}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.ipify.org?format=json",
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"working": True, "ip": data.get("ip", "unknown")}
                return {"working": False, "error": f"HTTP {resp.status}"}
    except asyncio.TimeoutError:
        return {"working": False, "error": "Connection timeout"}
    except Exception as e:
        return {"working": False, "error": str(e)}


def parse_proxy_string(proxy_str: str) -> dict:
    """
    Parse proxy string in common formats:
    - host:port
    - host:port:user:pass
    - type://user:pass@host:port
    """
    proxy_str = proxy_str.strip()
    
    # URL format
    if "://" in proxy_str:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_str)
        return {
            "type": parsed.scheme or "socks5",
            "host": parsed.hostname,
            "port": parsed.port or 1080,
            "username": parsed.username,
            "password": parsed.password,
        }
    
    parts = proxy_str.split(":")
    
    if len(parts) == 2:
        return {
            "type": "socks5",
            "host": parts[0],
            "port": int(parts[1]),
            "username": None,
            "password": None,
        }
    elif len(parts) == 4:
        return {
            "type": "socks5",
            "host": parts[0],
            "port": int(parts[1]),
            "username": parts[2],
            "password": parts[3],
        }
    
    raise ValueError(f"Invalid proxy format: {proxy_str}")
