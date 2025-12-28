from __future__ import annotations

import random
import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.utils import now_ts, now_local, fmt
from core.isla_text import sanitize_isla_text
from utils.embed_utils import create_embed
from utils.embed_utils import create_embed

UK_TZ = ZoneInfo("Europe/London")

CASINO_THUMBS = [
    "https://i.imgur.com/jzk6IfH.png",
    "https://i.imgur.com/cO7hAij.png",
    "https://i.imgur.com/My3QzNu.png",
    "https://i.imgur.com/kzwCK79.png",
    "https://i.imgur.com/jGnkAKs.png"
]

ROLE_NAMES = [
    "Casino Royalty I",
    "Casino Royalty II",
    "Casino Royalty III"
]


def casino_embed(desc: str, icon: str) -> discord.Embed:
    """Create a casino embed (for DMs, includes author)."""
    return create_embed(
        description=sanitize_isla_text(desc),
        color="casino",
        thumbnail=CASINO_THUMBS[int(now_ts()) % len(CASINO_THUMBS)],
        is_dm=True,  # Used for DMs
        is_system=False
    )


def prev_week_key_uk() -> str:
    # use yesterday to ensure "previous week" when run early Monday
    t = now_local() - timedelta(days=1)
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"


def random_choice(arr):
    return random.choice(arr)


class CasinoRoyalty(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        self.weekly_awards.start()

    def cog_unload(self):
        self.weekly_awards.cancel()

    async def _get_or_create_role(self, guild: discord.Guild, name: str) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=name)
        if role:
            return role
        try:
            return await guild.create_role(name=name, reason="IslaBot: casino royalty roles")
        except Exception:
            return None

    async def _clear_roles(self, guild: discord.Guild, roles: list[discord.Role]):
        role_ids = {r.id for r in roles if r}
        for member in guild.members:
            if member.bot:
                continue
            to_remove = [r for r in member.roles if r.id in role_ids]
            if to_remove:
                try:
                    await member.remove_roles(*to_remove, reason="IslaBot: rotating casino royalty")
                except Exception:
                    pass

    async def _top3_by_wager(self, guild_id: int, week_key: str):
        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, casino_wagered
            FROM weekly_stats
            WHERE guild_id=? AND week_key=?
            ORDER BY casino_wagered DESC
            LIMIT 3
            """,
            (guild_id, week_key)
        )
        return [(int(r["user_id"]), int(r["casino_wagered"])) for r in rows if int(r["casino_wagered"]) > 0]

    async def _dm_winner(self, guild: discord.Guild, user_id: int, place: int, wagered: int):
        member = guild.get_member(user_id)
        if not member:
            return

        casino = self.bot.get_cog("CasinoCore")

        # window: last 7 days
        since_ts = now_ts() - 7 * 24 * 3600
        highlight = None
        if casino and hasattr(casino, "get_recent_user_highlight"):
            try:
                highlight = await casino.get_recent_user_highlight(guild.id, user_id, since_ts)
            except Exception:
                highlight = None

        # build fluid remembered reference (real numbers if available)
        remembered = ""
        if highlight:
            if highlight.get("net", 0) > 0:
                remembered = f"I saw you pull **{fmt(int(highlight['net']))} Coins** on **{highlight['game']}** recently.\n"
            else:
                remembered = f"I noticed you wagering **{fmt(int(highlight['wager']))} Coins** on **{highlight['game']}**.\n"

        # different tone per placement (still "Isla", but distinct)
        if place == 1:
            text = (
                f"{member.mention}\n"
                f"{remembered}"
                f"You took **#1**.\n"
                f"Total wagered: **{fmt(wagered)} Coins**.\n"
                f"Don't get comfortable. I'm watching you.\n᲼᲼"
            )
        elif place == 2:
            text = (
                f"{member.mention}\n"
                f"{remembered}"
                f"**#2**.\n"
                f"Total wagered: **{fmt(wagered)} Coins**.\n"
                f"Keep chasing. I like when you try.\n᲼᲼"
            )
        else:
            text = (
                f"{member.mention}\n"
                f"{remembered}"
                f"**#3**.\n"
                f"Total wagered: **{fmt(wagered)} Coins**.\n"
                f"You made it. Barely. Don't slow down.\n᲼᲼"
            )

        try:
            await member.send(embed=casino_embed(text, self.icon))
        except Exception:
            pass

    async def _spotlight_post(self, guild: discord.Guild, week_key: str, top3: list[tuple[int, int]]):
        spotlight_id = int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)
        ch = guild.get_channel(spotlight_id) if spotlight_id else None
        if not isinstance(ch, discord.TextChannel):
            return

        # spoiler pings outside embed (your rule)
        pings = " ".join([f"||<@{uid}>||" for uid, _ in top3])

        lines = [f"Weekly Casino Royalty ({week_key})\n"]
        for i, (uid, wagered) in enumerate(top3, start=1):
            lines.append(f"**#{i}** <@{uid}> — **{fmt(wagered)} Coins wagered**")

        # Isla voice: short, fluid, not spammy
        flavor = [
            "I checked the tables.",
            "I looked at the casino logs.",
            "I peeked at who couldn't resist."
        ]
        closer = [
            "Try to catch them.",
            "If you want my attention, you know what to do.",
            "Next week I expect better."
        ]

        desc = (
            f"{random_choice(flavor)}\n\n"
            + "\n".join(lines)
            + f"\n\n{random_choice(closer)}\n᲼᲼"
        )

        # Spotlight post is a system message (sent to channel, includes author)
        embed = create_embed(
            description=sanitize_isla_text(desc),
            color="casino",
            thumbnail=CASINO_THUMBS[int(now_ts()) % len(CASINO_THUMBS)],
            is_dm=False,
            is_system=True  # System message - includes author
        )
        await ch.send(content=pings, embed=embed)

    @tasks.loop(time=time(hour=12, minute=10, tzinfo=UK_TZ))  # Monday midday-ish UK
    async def weekly_awards(self):
        await self.bot.wait_until_ready()

        # only run on Monday
        if now_local().weekday() != 0:
            return

        week_key = prev_week_key_uk()

        for guild in self.bot.guilds:
            try:
                top3 = await self._top3_by_wager(guild.id, week_key)
                if not top3:
                    continue

                roles = []
                for name in ROLE_NAMES:
                    roles.append(await self._get_or_create_role(guild, name))

                # clear old holders
                await self._clear_roles(guild, roles)

                # assign new holders + DM
                for idx, (uid, wagered) in enumerate(top3):
                    role = roles[idx] if idx < len(roles) else None
                    member = guild.get_member(uid)
                    if member and role:
                        try:
                            await member.add_roles(role, reason="IslaBot: weekly casino royalty")
                        except Exception:
                            pass
                    await self._dm_winner(guild, uid, idx + 1, wagered)

                # spotlight post
                await self._spotlight_post(guild, week_key, top3)

            except Exception:
                continue


async def setup(bot: commands.Bot):
    await bot.add_cog(CasinoRoyalty(bot))

