"""
Anti-Ban System for Telegram operations.
Implements typing simulation, account rotation, and flood wait handling.
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Optional


class AntiBanSystem:
    """
    Core anti-ban logic:
    1. SetTyping simulation before each message
    2. Round-robin account rotation
    3. FloodWaitError handling per-account
    4. Random delays between actions
    """
    
    def __init__(self):
        self._account_queue: List[dict] = []
        self._current_index: int = 0
        self._flood_blocked: dict = {}  # account_id -> unblock_time
    
    def set_accounts(self, accounts: List[dict]):
        """Set the pool of accounts for rotation."""
        self._account_queue = [a for a in accounts if a.get("status") == "active"]
        self._current_index = 0
    
    def get_next_account(self) -> Optional[dict]:
        """
        Get next available account using round-robin rotation.
        Skips accounts that are currently flood-blocked.
        """
        if not self._account_queue:
            return None
        
        attempts = 0
        while attempts < len(self._account_queue):
            account = self._account_queue[self._current_index % len(self._account_queue)]
            self._current_index += 1
            
            # Check if account is flood-blocked
            account_id = account.get("id")
            if account_id in self._flood_blocked:
                if datetime.now() < self._flood_blocked[account_id]:
                    attempts += 1
                    continue
                else:
                    del self._flood_blocked[account_id]
            
            return account
            attempts += 1
        
        return None  # All accounts are flood-blocked
    
    def mark_flood_wait(self, account_id: int, wait_seconds: int):
        """Mark an account as flood-blocked for a duration."""
        self._flood_blocked[account_id] = datetime.now() + timedelta(seconds=wait_seconds)
    
    def is_flood_blocked(self, account_id: int) -> bool:
        """Check if an account is currently flood-blocked."""
        if account_id not in self._flood_blocked:
            return False
        if datetime.now() >= self._flood_blocked[account_id]:
            del self._flood_blocked[account_id]
            return False
        return True
    
    def get_flood_remaining(self, account_id: int) -> int:
        """Get remaining seconds of flood block for an account."""
        if account_id not in self._flood_blocked:
            return 0
        remaining = (self._flood_blocked[account_id] - datetime.now()).total_seconds()
        return max(0, int(remaining))
    
    @staticmethod
    async def simulate_typing(client, peer, duration: float = None):
        """
        Simulate typing action before sending a message.
        Duration is randomized between 3-5 seconds if not specified.
        """
        if duration is None:
            duration = random.uniform(3.0, 5.0)
        
        try:
            from telethon.tl.functions.messages import SetTypingRequest
            from telethon.tl.types import SendMessageTypingAction
            
            await client(SetTypingRequest(
                peer=peer,
                action=SendMessageTypingAction()
            ))
            await asyncio.sleep(duration)
        except Exception:
            # Typing simulation failure is non-critical
            await asyncio.sleep(duration)
    
    @staticmethod
    def get_random_delay(min_delay: int, max_delay: int) -> float:
        """Get a randomized delay between actions."""
        return random.uniform(min_delay, max_delay)
    
    @staticmethod
    async def wait_random(min_delay: int, max_delay: int):
        """Wait a random duration between min and max seconds."""
        delay = random.uniform(min_delay, max_delay)
        await asyncio.sleep(delay)


# Global singleton instance
antiban = AntiBanSystem()
