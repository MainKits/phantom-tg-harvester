"""
Telegram Engine — manages Telethon client instances for multiple accounts.
Handles session loading, proxy binding, and client lifecycle.
"""

import os
import asyncio
from typing import Dict, Optional
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserDeactivatedBanError, PhoneNumberBannedError
import socks

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


async def get_api_credentials() -> tuple:
    """Get API credentials from database settings or environment."""
    api_id = os.environ.get("TG_API_ID", "")
    api_hash = os.environ.get("TG_API_HASH", "")

    try:
        import aiosqlite
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "phantom_harvester.db")
        db = await aiosqlite.connect(db_path, timeout=30.0)
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'api_id'")
        row = await cursor.fetchone()
        if row and row[0]:
            api_id = row[0]
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'api_hash'")
        row = await cursor.fetchone()
        if row and row[0]:
            api_hash = row[0]
        await db.close()
    except Exception:
        pass

    return int(api_id) if api_id else 0, api_hash


class TelegramEngine:
    """Manages multiple Telethon client instances."""

    def __init__(self):
        self._clients: Dict[int, TelegramClient] = {}
        self._connected: Dict[int, bool] = {}

    def get_client(self, account_id: int) -> Optional[TelegramClient]:
        """Return connected client if exists, otherwise None."""
        return self._clients.get(account_id)

    def is_connected(self, account_id: int) -> bool:
        return self._connected.get(account_id, False)

    def _get_proxy(self, account: dict) -> Optional[tuple]:
        """Build proxy tuple from account config."""
        if not account.get("proxy_host"):
            return None
        proxy_type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
        ptype = proxy_type_map.get((account.get("proxy_type") or "socks5").lower(), socks.SOCKS5)
        return (ptype, account["proxy_host"], int(account.get("proxy_port") or 1080),
                True, account.get("proxy_username"), account.get("proxy_password"))

    async def connect_account(self, account: dict) -> bool:
        """Connect a Telethon client for the given account. Returns True if authorized."""
        account_id = account["id"]

        # Reuse existing connected client
        if account_id in self._clients and self._connected.get(account_id):
            if self._clients[account_id].is_connected():
                return True

        api_id, api_hash = await get_api_credentials()
        if not api_id or not api_hash:
            raise ValueError("API ID та API Hash не налаштовані. Перейдіть у Settings.")

        phone = account["phone"]
        session_file = account.get("session_file")
        # Strip .session extension to avoid double extension (e.g. file.session.session)
        session_name = (session_file or phone.replace("+", "")).replace(".session", "")
        session_path = os.path.join(SESSIONS_DIR, session_name)
        proxy = self._get_proxy(account)

        try:
            client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                self._connected[account_id] = False
                return False
            self._clients[account_id] = client
            self._connected[account_id] = True
            return True
        except (UserDeactivatedBanError, PhoneNumberBannedError):
            self._connected[account_id] = False
            raise ValueError(f"Account {phone} is banned")
        except Exception as e:
            self._connected[account_id] = False
            raise e

    async def disconnect_account(self, account_id: int):
        if account_id in self._clients:
            try:
                await self._clients[account_id].disconnect()
            except Exception:
                pass
            del self._clients[account_id]
        self._connected[account_id] = False

    async def disconnect_all(self):
        for account_id in list(self._clients.keys()):
            await self.disconnect_account(account_id)

    # ─── Auth flow ────────────────────────────────────────────────────────────

    async def send_code(self, phone: str, proxy: dict = None) -> dict:
        """Start manual authorization — send code to phone number."""
        api_id, api_hash = await get_api_credentials()
        if not api_id or not api_hash:
            raise ValueError("API ID та API Hash не налаштовані. Натисніть '🔑 API Settings' та додайте ключі з my.telegram.org")

        # Clean digits from phone
        digits = "".join(c for c in phone if c.isdigit())
        if not digits or len(digits) < 7:
            raise ValueError(f"'{phone}' не схоже на номер телефону. Введіть номер у міжнародному форматі (наприклад +380991234567)")
        clean_phone = "+" + digits

        session_name = clean_phone.replace("+", "")
        session_path = os.path.join(SESSIONS_DIR, session_name)

        auth_key = f"auth_{clean_phone}"
        if auth_key in self._clients:
            try:
                await self._clients[auth_key].disconnect()
            except Exception:
                pass
            del self._clients[auth_key]

        proxy_tuple = None
        if proxy and proxy.get("host"):
            proxy_type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
            proxy_tuple = (
                proxy_type_map.get((proxy.get("type") or "socks5").lower(), socks.SOCKS5),
                proxy["host"], int(proxy.get("port") or 1080),
                True, proxy.get("username"), proxy.get("password")
            )

        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy_tuple)
        await client.connect()
        try:
            result = await client.send_code_request(clean_phone)
            self._clients[auth_key] = client
            return {"phone_code_hash": result.phone_code_hash, "clean_phone": clean_phone}
        except Exception as e:
            await client.disconnect()
            err_str = str(e).lower()
            if "phone_number_invalid" in err_str:
                raise ValueError("Невірний номер телефону. Перевірте код країни та правильність цифр.")
            elif "phone_number_banned" in err_str:
                raise ValueError("Цей номер телефону заблокований у Telegram.")
            elif "flood" in err_str:
                raise ValueError(f"Забагато запитів від Telegram (FloodWait). Зачекайте трохи перед повторною спробою: {e}")
            elif "send_code_unavailable" in err_str:
                raise ValueError("Telegram не може надіслати SMS. Перевірте чи додаток Telegram відкритий на телефоні (код може прийти туди).")
            elif "api_id_invalid" in err_str:
                raise ValueError("Невірний API ID або API Hash! Перевірте налаштування в 'API Settings'.")
            raise ValueError(f"Помилка надсилання коду Telegram: {str(e)}")

    async def sign_in(self, phone: str, code: str, phone_code_hash: str, password: str = None) -> dict:
        """Complete manual authorization with the received code (and optional 2FA password)."""
        from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
        
        digits = "".join(c for c in phone if c.isdigit())
        clean_phone = "+" + digits if digits else phone
        
        auth_key = f"auth_{clean_phone}"
        client = self._clients.get(auth_key)
        if not client:
            raise ValueError("Немає активної сесії авторизації для цього номера. Натисніть 'Надіслати код' знову.")
        
        try:
            try:
                user = await client.sign_in(clean_phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                if not password:
                    return {"needs_2fa": True, "message": "Потрібен хмарний пароль (2FA)"}
                user = await client.sign_in(password=password)
            
            await client.disconnect()
            del self._clients[auth_key]
            return {"success": True, "user_id": user.id,
                    "first_name": user.first_name, "username": user.username,
                    "phone": clean_phone}
        except PhoneCodeInvalidError:
            raise ValueError("Невірний код підтвердження! Перевірте цифри і спробуйте знову.")
        except PhoneCodeExpiredError:
            raise ValueError("Термін дії коду закінчився. Надішліть код повторно.")
        except Exception as e:
            if "password_hash_invalid" in str(e).lower():
                raise ValueError("Невірний хмарний пароль (2FA)!")
            try:
                await client.disconnect()
            except Exception:
                pass
            if auth_key in self._clients:
                del self._clients[auth_key]
            raise ValueError(f"Помилка входу: {str(e)}")

    # ─── Account status check ─────────────────────────────────────────────────

    async def check_account_status(self, account: dict) -> str:
        """Check if an account is active, banned, or spam-blocked."""
        try:
            connected = await self.connect_account(account)
            if not connected:
                return "inactive"

            client = self.get_client(account["id"])
            if not client:
                return "inactive"

            me = await client.get_me()
            if not me:
                return "banned"

            from ..database import log_event
            try:
                await client.send_message("spambot", "/start")
                reply_text = ""
                for _ in range(6):
                    await asyncio.sleep(2)
                    messages = await client.get_messages("spambot", limit=1)
                    if messages and not messages[0].out:
                        reply_text = messages[0].message.lower()
                        break

                if reply_text:
                    await log_event("info", "accounts",
                                    f"SpamBot reply for {account['phone']}: {reply_text}")
                    good_words = [
                        "no limits", "free from any restrictions", "good news",
                        "свободен", "вільний", "ограничений нет", "обмежень немає",
                        "not limited", "working well"
                    ]
                    if any(w in reply_text for w in good_words):
                        return "active"
                    return "spam-block"
                else:
                    await log_event("warn", "accounts",
                                    f"SpamBot did not reply for {account['phone']}")
                    return "active"
            except Exception as e:
                await log_event("warn", "accounts", f"SpamBot check error: {str(e)}")
                if "PEER_ID_INVALID" in str(e) or "FloodWait" in str(e):
                    return "spam-block"
                return "active"

        except Exception as e:
            err = str(e).lower()
            if any(w in err for w in ["deactivated", "banned", "unregistered", "deleted"]):
                return "banned"
            if "flood" in err:
                return "spam-block"
            return "inactive"

    # ─── Telegram actions ─────────────────────────────────────────────────────

    async def join_chat(self, client: TelegramClient, chat_link: str):
        """Join a channel/group by link or username."""
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.tl.functions.messages import ImportChatInviteRequest

        chat_link = chat_link.strip()
        if "t.me/+" in chat_link or "t.me/joinchat/" in chat_link:
            invite_hash = chat_link.split("/")[-1].lstrip("+")
            await client(ImportChatInviteRequest(invite_hash))
        else:
            entity = await client.get_entity(chat_link)
            await client(JoinChannelRequest(entity))

    async def post_comment(self, client: TelegramClient, channel,
                            post_id: int, comment_text: str):
        """Post a comment to a channel post (via linked discussion group)."""
        entity = channel if not isinstance(channel, str) else await client.get_entity(channel)
        await client.send_message(entity, comment_text, comment_to=post_id)


# Global singleton
telegram_engine = TelegramEngine()
