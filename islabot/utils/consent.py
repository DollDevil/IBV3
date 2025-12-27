from __future__ import annotations
import time
import random

def now_ts() -> int:
    return int(time.time())

class Consent:
    """
    Central consent flags used by every feature/cog.
    """
    def __init__(self, opted_out: bool, safeword_on: bool, vacation_until_ts: int):
        self.opted_out = bool(opted_out)
        self.safeword_on = bool(safeword_on)
        self.vacation_until_ts = int(vacation_until_ts or 0)

    @property
    def on_vacation(self) -> bool:
        return self.vacation_until_ts > now_ts()

async def get_consent(db, gid: int, uid: int) -> Consent:
    row = await db.fetchone(
        "SELECT opted_out, safeword_on, vacation_until_ts FROM users WHERE guild_id=? AND user_id=?",
        (gid, uid)
    )
    if not row:
        return Consent(False, False, 0)
    return Consent(
        bool(int(row["opted_out"] or 0)),
        bool(int(row["safeword_on"] or 0)),
        int(row["vacation_until_ts"] or 0)
    )

# -----------------------------
# Tone pools (neutral)
# -----------------------------
NEUTRAL = {
    "ack": [
        "Noted.",
        "Okay.",
        "Understood.",
        "Done.",
    ],
    "error": [
        "That didn't work.",
        "I can't do that right now.",
        "Try again with valid inputs.",
    ],
    "welcome": [
        "Welcome.",
        "You're set up now.",
        "All good to go.",
    ],
    "order_accepted": [
        "Order accepted.",
        "Task accepted.",
        "Accepted. Timer started.",
    ],
    "order_success": [
        "Completed. Reward issued.",
        "Completion confirmed.",
        "Done. Rewards added.",
    ],
    "order_failed": [
        "Order expired.",
        "Time ran out.",
        "Order failed. Try again later.",
    ],
    "casino_win": [
        "Win confirmed. Coins added.",
        "You won. Rewards applied.",
        "Win registered.",
    ],
    "casino_loss": [
        "Loss registered.",
        "Round ended. Coins deducted.",
        "Loss confirmed.",
    ],
    "profile_header": [
        "Profile",
        "User Profile",
        "Account Summary",
    ],
}

def pick(pool: str) -> str:
    """Pick a random line from a neutral tone pool."""
    arr = NEUTRAL.get(pool) or NEUTRAL["ack"]
    return random.choice(arr)

def tone_key(consent: Consent) -> str:
    # You can extend later: "normal", "neutral", "staff", etc.
    return "neutral" if consent.safeword_on else "normal"

