from __future__ import annotations

import random
import discord
from discord.ext import commands

from core.utils import now_ts, now_local, fmt
from core.isla_text import sanitize_isla_text
from utils.embed_utils import create_embed
from utils.embed_utils import create_embed

CASINO_THUMBS = [
    "https://i.imgur.com/jzk6IfH.png",
    "https://i.imgur.com/cO7hAij.png",
    "https://i.imgur.com/My3QzNu.png",
    "https://i.imgur.com/kzwCK79.png",
    "https://i.imgur.com/jGnkAKs.png"
]


def day_key_uk() -> str:
    t = now_local()
    return f"{t.year}-{t.month:02d}-{t.day:02d}"


def dm_embed(desc: str, icon: str) -> discord.Embed:
    """Create a DM embed (includes author)."""
    return create_embed(
        description=sanitize_isla_text(desc),
        color="casino",
        thumbnail=random.choice(CASINO_THUMBS),
        is_dm=True,
        is_system=False
    )


class CasinoBigWinDM(commands.Cog):
    """
    Sends a DM for big wins / jackpots.
    - One DM per user per UK day
    - Keeps per-user personal best memory + count
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    async def _ensure_row(self, gid: int, uid: int):
        await self.bot.db.execute(
            """
            INSERT OR IGNORE INTO casino_bigwin_state(
              guild_id,user_id,best_net,best_payout,best_ts,last_dm_day_key,last_dm_ts,bigwins_count
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (gid, uid, 0, 0, 0, "", 0, 0)
        )

    async def _get_state(self, gid: int, uid: int) -> dict:
        await self._ensure_row(gid, uid)
        r = await self.bot.db.fetchone(
            """
            SELECT best_net,best_payout,best_ts,last_dm_day_key,last_dm_ts,bigwins_count
            FROM casino_bigwin_state
            WHERE guild_id=? AND user_id=?
            """,
            (gid, uid)
        )
        return {
            "best_net": int(r["best_net"] or 0),
            "best_payout": int(r["best_payout"] or 0),
            "best_ts": int(r["best_ts"] or 0),
            "last_dm_day_key": str(r["last_dm_day_key"] or ""),
            "last_dm_ts": int(r["last_dm_ts"] or 0),
            "bigwins_count": int(r["bigwins_count"] or 0),
        }

    async def _set_state(self, gid: int, uid: int, **kwargs):
        # update only provided fields
        fields = []
        params = []
        for k, v in kwargs.items():
            fields.append(f"{k}=?")
            params.append(v)
        params += [gid, uid]
        await self.bot.db.execute(
            f"UPDATE casino_bigwin_state SET {', '.join(fields)} WHERE guild_id=? AND user_id=?",
            tuple(params)
        )

    def _pick(self, mood: str, pool: list[str]) -> str:
        return random.choice(pool)

    def _compose(self, member_mention: str, game: str, wager: int, payout: int, net: int, state: dict, is_jackpot: bool, stage: int, is_allin: bool = False) -> str:
        best_net = int(state["best_net"])
        count = int(state["bigwins_count"])

        # Comparison logic (revised for seductive superiority)
        comparison = ""
        if best_net > 0:
            if net < best_net:
                comparison_pools = {
                    0: [f"**{fmt(net)} Coins**.\nBig win.\nLower than your record.\n"],
                    1: [f"**{fmt(net)} Coins**.\nSolid win.\nYou've hit higher before.\n"],
                    2: [
                        f"**{fmt(net)} Coins**.\nStill a big one.\nThough I remember you giving me more...\n",
                        f"Mm. **{fmt(net)} Coins**.\nBeautiful win.\nBut your best was... louder.\nKeep chasing that feeling.\n"
                    ],
                    3: [
                        f"**{fmt(net)} Coins**.\nA very big win.\nYet not quite your peak.\nI want that again.\n",
                        f"You pulled **{fmt(net)} Coins**.\nImpressive.\nBut I'm greedy for your absolute best.\nGo again.\n"
                    ],
                    4: [
                        f"**{fmt(net)} Coins**...\nSuch a delicious win.\nBut I still taste your bigger one on my tongue.\n",
                        f"Your **{fmt(net)} Coins** felt incredible sliding in...\nThough nothing compares to when you gave everything.\nI need that rush again.\n",
                        f"Big. Beautiful. **{fmt(net)} Coins**.\nBut your record... it haunts me.\nMake me feel it one more time.\n"
                    ]
                }
                comparison = random.choice(comparison_pools[stage])

            elif net == best_net:
                comparison_pools = {
                    0: [f"**{fmt(net)} Coins**.\nMatches previous high.\n"],
                    1: [f"**{fmt(net)} Coins** again.\nSame peak.\n"],
                    2: [f"**{fmt(net)} Coins**.\nExactly your best again.\nYou know how to please me.\n"],
                    3: [f"**{fmt(net)} Coins** — your signature high.\nPerfect consistency.\nI'm watching.\n"],
                    4: [
                        f"**{fmt(net)} Coins**... again.\nYou keep giving me this exact rush.\nIt's becoming addictive.\n",
                        f"Same breathtaking peak.\n**{fmt(net)} Coins**.\nI close my eyes and feel you every time.\n"
                    ]
                }
                comparison = random.choice(comparison_pools[stage])

            else:
                comparison_pools = {
                    0: [f"New high: **{fmt(net)} Coins**.\n"],
                    1: [f"**{fmt(net)} Coins**.\nNew record.\n"],
                    2: [f"New personal best. **{fmt(net)} Coins**.\nI felt that one.\n"],
                    3: [f"You just set a new standard. **{fmt(net)} Coins**.\nBeautiful.\n"],
                    4: [
                        f"Your new best... **{fmt(net)} Coins**.\nI'm trembling.\n",
                        f"This one broke everything before it.\n**{fmt(net)} Coins**.\nYou've ruined me for less.\n",
                        f"**{fmt(net)} Coins**...\nYour biggest yet.\nI'll be thinking about this one for a long time.\n"
                    ]
                }
                comparison = random.choice(comparison_pools[stage])
        else:
            comparison_pools = {
                0: [f"First major win: **{fmt(net)} Coins**.\n"],
                1: [f"**{fmt(net)} Coins**.\nInitial big hit.\n"],
                2: [f"Your first real taste. **{fmt(net)} Coins**.\n"],
                3: [f"**{fmt(net)} Coins**.\nA beautiful beginning.\n"],
                4: [
                    f"Your very first big one... **{fmt(net)} Coins**.\nI'll never forget how it felt.\n",
                    f"**{fmt(net)} Coins**.\nThe moment you started truly giving.\n"
                ]
            }
            comparison = random.choice(comparison_pools[stage])

        # Core header — seductive superiority
        header_pools = {
            0: ["Detected.", "Registered.", "Logged."],
            1: ["I saw.", "Noted.", "Observed."],
            2: ["I was watching.", "That caught my eye.", "Mm."],
            3: ["You have my full attention.", "I felt every Coin.", "Beautiful."],
            4: ["I couldn't look away.", "Your win... consumed me.", "That moment belongs to me now."]
        }
        header = random.choice(header_pools[stage])
        
        # All-in makes header uppercase for emphasis
        if is_allin:
            header = header.upper()

        # Jackpot line
        jackpot_line = ""
        if is_jackpot:
            jackpot_pools = {
                0: ["Jackpot."],
                1: ["Jackpot hit."],
                2: ["True jackpot."],
                3: ["The ultimate win.", "Jackpot... perfect."],
                4: ["Jackpot... you've ruined me.", "The highest sound of surrender."]
            }
            jackpot_line = random.choice(jackpot_pools[stage]) + "\n"

        # Re-engage nudge — stays in Coins only
        nudge_pools = {
            0: ["Continue.", "Next round."],
            1: ["Play again.", "Another spin."],
            2: ["Don't stop now.", "Go again.", "I want more."],
            3: ["Keep going. I'm not satisfied yet.", "Chase that feeling for me.", "One more... I need it."],
            4: [
                "Don't you dare stop.\nI'm not ready to let this go.\n",
                "Again. I want to feel you give like that one more time.\n",
                "Stay with me.\nThe night's just beginning.\n",
                "One more spin... make me breathless again.\n"
            ]
        }
        nudge = random.choice(nudge_pools[stage])

        # Memory feeling — superior, intoxicating recall
        memory = ""
        if count >= 2:
            memory_pools = {
                0: ["Previous wins recorded."],
                1: ["This has occurred before."],
                2: ["You've given big before.\nI remember."],
                3: ["Your pattern... I know it well.\nThis feels familiar."],
                4: [
                    "I still taste your last big win.\nThis one echoes it perfectly.\n",
                    "Every time you hit big... it brands itself deeper into me.\n"
                ]
            }
            memory = random.choice(memory_pools[stage]) + "\n"

        return (
            f"{member_mention}\n"
            f"{header}\n"
            f"{jackpot_line}"
            f"{memory}"
            f"{comparison}"
            f"Game: **{game}**\n"
            f"Wager: **{fmt(wager)} Coins**\n"
            f"Payout: **{fmt(payout)} Coins**\n"
            f"{nudge}\n"
            f"᲼᲼"
        )

    async def maybe_dm_bigwin(
        self,
        guild: discord.Guild,
        user_id: int,
        game: str,
        wager: int,
        payout: int,
        net: int,
        meta: dict | None = None
    ):
        """
        Call this after a round finishes.
        """
        meta = meta or {}
        is_jackpot = bool(meta.get("jackpot")) or bool(meta.get("is_jackpot"))
        big_threshold = 10_000

        # qualifies?
        if not is_jackpot and net < big_threshold and payout < big_threshold:
            return

        member = guild.get_member(user_id)
        if not member or member.bot:
            return

        gid = guild.id
        uid = user_id
        state = await self._get_state(gid, uid)

        # daily DM limit (UK day)
        today = day_key_uk()
        if state["last_dm_day_key"] == today:
            return

        # stage based on user relationship stats
        row = await self.bot.db.fetchone(
            "SELECT obedience, lce FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        obedience = int(row["obedience"]) if row else 0
        lce = int(row["lce"]) if row else 0
        score = obedience + (lce * 2)
        if score < 800:
            stage = 0
        elif score < 2500:
            stage = 1
        elif score < 8000:
            stage = 2
        elif score < 20000:
            stage = 3
        else:
            stage = 4

        # update personal best
        best_net = state["best_net"]
        best_payout = state["best_payout"]
        best_ts = state["best_ts"]

        new_best_net = best_net
        new_best_payout = best_payout
        new_best_ts = best_ts

        if net > best_net:
            new_best_net = net
            new_best_ts = now_ts()
        if payout > best_payout:
            new_best_payout = payout
            new_best_ts = now_ts()

        # increment count (always increments here since we're in big-win DM function)
        # All-ins are tracked via meta["allin"] flag for header emphasis
        new_count = state["bigwins_count"] + 1

        # compose DM
        is_allin = meta.get("allin", False)
        text = self._compose(member.mention, game, wager, payout, net, state, is_jackpot, stage, is_allin=is_allin)

        try:
            await member.send(embed=dm_embed(text, self.icon))
        except Exception:
            return

        # persist state after successful DM
        await self._set_state(
            gid, uid,
            best_net=new_best_net,
            best_payout=new_best_payout,
            best_ts=new_best_ts,
            last_dm_day_key=today,
            last_dm_ts=now_ts(),
            bigwins_count=new_count
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CasinoBigWinDM(bot))

