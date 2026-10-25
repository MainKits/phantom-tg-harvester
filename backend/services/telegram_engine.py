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
    """Get API credentials from environment, SQLite settings, or Supabase cloud."""
    api_id = os.environ.get("TG_API_ID", "")
    api_hash = os.environ.get("TG_API_HASH", "")

    # 1. Check local SQLite
    try:
        from ..database import get_db
        db = await get_db()
        cursor = await db.execute("SELECT key, value FROM settings WHERE key IN ('api_id', 'api_hash')")
        rows = await cursor.fetchall()
        for r in rows:
            if r[0] == "api_id" and r[1]:
                api_id = r[1]
            elif r[0] == "api_hash" and r[1]:
                api_hash = r[1]
        await db.close()
    except Exception:
        pass

    # 2. Check Supabase cloud if missing
    if not api_id or not api_hash:
        try:
            from ..database import get_supabase_client
            sb = get_supabase_client()
            if sb:
                res = sb.table("settings").select("*").execute()
                if res.data:
                    for item in res.data:
                        k, v = item.get("key"), str(item.get("value", ""))
                        if k == "api_id" and v:
                            api_id = v
                        elif k == "api_hash" and v:
                            api_hash = v
        except Exception:
            pass

    # 3. Safe fallback to default Telegram Desktop credentials so client never crashes
    DEFAULT_API_ID = 2040
    DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

    final_id = int(api_id) if api_id and str(api_id).isdigit() else DEFAULT_API_ID
    final_hash = api_hash if api_hash else DEFAULT_API_HASH

    return final_id, final_hash


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
        actual_session = f"{session_path}.session"

        # On-demand restore session file from Supabase cloud if missing on Render disk
        if not os.path.exists(actual_session) or os.path.getsize(actual_session) == 0:
            try:
                from ..database import get_supabase_client
                sb = get_supabase_client()
                if sb:
                    res = sb.table("accounts").select("session_data").or_(f"phone.eq.{phone},session_file.eq.{session_file}").execute()
                    if res.data and res.data[0].get("session_data"):
                        import base64
                        with open(actual_session, "wb") as sf:
                            sf.write(base64.b64decode(res.data[0]["session_data"]))
                        print(f"[Supabase] Restored missing session for {phone} from cloud")
            except Exception as restore_err:
                print(f"[Supabase] On-demand session restore note: {restore_err}")

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
                            post_id: int, comment_text: str, file: str = None):
        """Post a comment to a channel post (via linked discussion group)."""
        entity = channel if not isinstance(channel, str) else await client.get_entity(channel)
        if file and os.path.exists(file):
            await client.send_message(entity, comment_text, comment_to=post_id, file=file)
        else:
            await client.send_message(entity, comment_text, comment_to=post_id)

    async def handle_captcha_and_subscriptions(self, client: TelegramClient, entity, me=None, log_fn=None, on_sponsor_channel=None) -> bool:
        """
        Detect and automatically solve:
        1. Inline click-to-verify buttons ("I am not a bot", "Verify", "Accept rules", etc.)
        2. Math captchas (e.g. "5 + 3 = ?", clicks button with "8" or sends answer)
        3. Mandatory sponsor channel subscriptions (extracts public and private channels from text AND buttons, joins them, and clicks verification)
        4. DM verification bots (follows /start link in buttons to verify)
        """
        import re
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.tl.functions.messages import ImportChatInviteRequest

        action_taken = False
        if me is None:
            try:
                me = await client.get_me()
            except Exception:
                me = None

        try:
            # Check the last 12 messages in chat for bot captchas or subscription prompts
            async for msg in client.iter_messages(entity, limit=12):
                if not msg:
                    continue

                txt_raw = msg.text or ""
                txt = txt_raw.lower()

                user_mentioned = False
                if me:
                    if me.username and me.username.lower() in txt:
                        user_mentioned = True
                    if me.first_name and me.first_name.lower() in txt:
                        user_mentioned = True
                    if str(me.id) in txt:
                        user_mentioned = True

                is_verification = any(k in txt for k in [
                    "капч", "робот", "проверк", "вериф", "human", "verify", "captcha",
                    "кнопк", "підтверд", "подтверд", "правила", "подпиш", "підпиш", "sponsor", "спонсор",
                    "привет", "привіт", "добро пожаловать", "ласкаво просимо", "welcome"
                ])

                # ─── 1. MANDATORY SPONSOR CHANNEL SUBSCRIPTIONS ─────────────
                channels_to_join = set()
                invites_to_join = set()

                # Check text for sponsor links
                for m_url in re.findall(r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([a-zA-Z0-9_\-]+)", txt_raw):
                    invites_to_join.add(m_url.split("?")[0].strip())
                for m_ch in re.findall(r"(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{4,32})", txt_raw):
                    if m_ch.lower() not in ("joinchat", "share", "addstickers"):
                        channels_to_join.add(m_ch.lstrip("@"))
                for u in re.findall(r"@([a-zA-Z0-9_]{4,32})", txt_raw):
                    channels_to_join.add(u.lstrip("@"))

                # Check buttons for sponsor channel links
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if hasattr(btn, 'url') and btn.url:
                                u_str = str(btn.url)
                                if "/+" in u_str or "joinchat/" in u_str:
                                    inv = u_str.split("/+")[-1] if "/+" in u_str else u_str.split("joinchat/")[-1]
                                    inv = inv.split("?")[0].split("/")[0].strip()
                                    if inv:
                                        invites_to_join.add(inv)
                                elif "t.me/" in u_str or "telegram.me/" in u_str:
                                    ch = u_str.split("t.me/")[-1] if "t.me/" in u_str else u_str.split("telegram.me/")[-1]
                                    ch = ch.split("?")[0].split("/")[0].strip().lstrip("@")
                                    if ch and ch.lower() not in ("joinchat", "share", "addstickers") and not ch.endswith("bot"):
                                        channels_to_join.add(ch)

                # Join public sponsor channels
                for ch in channels_to_join:
                    if hasattr(entity, "username") and entity.username and entity.username.lower() == ch.lower():
                        continue
                    try:
                        ch_ent = await client.get_entity(ch)
                        await client(JoinChannelRequest(ch_ent))
                        action_taken = True
                        if log_fn:
                            await log_fn(f"📢 Підписано на спонсорський канал: @{ch}")
                        if on_sponsor_channel:
                            try:
                                await on_sponsor_channel(f"@{ch}")
                            except Exception:
                                pass
                        await asyncio.sleep(1.5)
                    except Exception:
                        pass

                # Join private sponsor channels
                for inv in invites_to_join:
                    try:
                        await client(ImportChatInviteRequest(inv))
                        action_taken = True
                        if log_fn:
                            await log_fn(f"📢 Приєднано приватний спонсорський канал за посиланням")
                        if on_sponsor_channel:
                            try:
                                await on_sponsor_channel(f"https://t.me/+{inv}")
                            except Exception:
                                pass
                        await asyncio.sleep(1.5)
                    except Exception:
                        pass

                # ─── 2. MATH CAPTCHAS (e.g. 7 + 4 = 11) ───────────────────────
                math_match = re.search(r"(\d{1,3})\s*([\+\-\*])\s*(\d{1,3})", txt_raw)
                math_ans = None
                if math_match:
                    try:
                        n1, op, n2 = int(math_match.group(1)), math_match.group(2), int(math_match.group(3))
                        if op == '+':
                            math_ans = n1 + n2
                        elif op == '-':
                            math_ans = n1 - n2
                        elif op == '*':
                            math_ans = n1 * n2
                    except Exception:
                        math_ans = None

                # ─── 3. CLICK INLINE BUTTONS (VERIFY / CONFIRM / MATH) ───────
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            b_text = (btn.text or "").strip().lower()

                            # Math captcha button match
                            if math_ans is not None:
                                if b_text == str(math_ans) or b_text == f"[{math_ans}]" or b_text == f"✅ {math_ans}":
                                    try:
                                        await btn.click()
                                        action_taken = True
                                        if log_fn:
                                            await log_fn(f"🤖 Розв'язано математичну капчу: {math_ans}")
                                        await asyncio.sleep(1.5)
                                        break
                                    except Exception:
                                        pass

                            # Standard verify keywords
                            is_verify_btn = any(k in b_text for k in [
                                "я не робот", "я не бот", "не робот", "я человек", "людина", "не бот",
                                "пройти", "вериф", "верифи", "verify", "human", "підтверд", "подтверд",
                                "согласен", "согласна", "згоден", "згодна", "agree", "accept", "принять",
                                "правила", "старт", "start", "ok", "ок", "✅", "🟢", "👍", "🆗", "🔓",
                                "подписался", "підписався", "проверить", "перевірити", "готово", "done",
                                "check", "продолжить", "продовжити", "continue", "вступил", "вступив",
                                "разблокировать", "розблокувати", "click here", "натисніть", "нажмите"
                            ])

                            if is_verify_btn or (user_mentioned and is_verification):
                                try:
                                    await btn.click()
                                    action_taken = True
                                    if log_fn:
                                        await log_fn(f"🤖 Натиснуто кнопку проходження перевірки: «{btn.text}»")
                                    await asyncio.sleep(1.5)
                                    break
                                except Exception:
                                    pass

                            # DM bot verification link in button
                            if hasattr(btn, 'url') and btn.url and ("?start=" in btn.url or "?startgroup=" in btn.url):
                                bot_m = re.search(r"(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+bot)\?(start(?:group)?)=([a-zA-Z0-9_\-]+)", btn.url, re.I)
                                if bot_m:
                                    b_username = bot_m.group(1)
                                    b_arg = bot_m.group(3)
                                    try:
                                        bot_ent = await client.get_entity(b_username)
                                        await client.send_message(bot_ent, f"/start {b_arg}")
                                        action_taken = True
                                        await asyncio.sleep(2)
                                        # Click verify button in bot chat if present
                                        async for bot_msg in client.iter_messages(bot_ent, limit=2):
                                            if bot_msg and bot_msg.buttons:
                                                for b_row in bot_msg.buttons:
                                                    for b_b in b_row:
                                                        try:
                                                            await b_b.click()
                                                            await asyncio.sleep(1)
                                                            break
                                                        except Exception:
                                                            pass
                                    except Exception:
                                        pass

                # If text asks to send the math answer directly in chat
                if math_ans is not None and not msg.buttons:
                    if any(k in txt for k in ["отправьте ответ", "напишите ответ", "надішліть відповідь", "напишіть відповідь", "ответ", "відповідь"]):
                        try:
                            await client.send_message(entity, str(math_ans))
                            action_taken = True
                            if log_fn:
                                await log_fn(f"🤖 Відправлено відповідь на капчу в чат: {math_ans}")
                            await asyncio.sleep(1.5)
                        except Exception:
                            pass

        except Exception:
            pass
        return action_taken


# Global singleton
telegram_engine = TelegramEngine()

