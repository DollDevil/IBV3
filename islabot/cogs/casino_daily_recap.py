from __future__ import annotations

import random
import discord
from discord.ext import commands, tasks
from datetime import time
from zoneinfo import ZoneInfo

from core.utils import now_ts, now_local, fmt
from core.isla_text import sanitize_isla_text
from utils.embed_utils import create_embed

UK_TZ = ZoneInfo("Europe/London")

CASINO_THUMBS = [
    "https://i.imgur.com/jzk6IfH.png",
    "https://i.imgur.com/cO7hAij.png",
    "https://i.imgur.com/My3QzNu.png",
    "https://i.imgur.com/kzwCK79.png",
    "https://i.imgur.com/jGnkAKs.png"
]


def casino_embed(desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(description=sanitize_isla_text(desc))
    e.set_author(name="Isla", icon_url=icon)
    e.set_thumbnail(url=random.choice(CASINO_THUMBS))
    return e


class CasinoDailyRecap(commands.Cog):
    """
    Posts ONE daily recap to #spotlight if casino activity is high.
    Uses CasinoCore's JSON round log summary.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        self.recap_loop.start()

    def cog_unload(self):
        self.recap_loop.cancel()

    async def _ensure_settings(self, gid: int):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id, collars_role_enabled, collars_role_prefix, log_channel_id) VALUES(?,?,?,?)",
            (gid, 0, "Collar", int(self.bot.cfg.get('channels', 'logs', default=0) or 0))
        )
        # ensure recap tracking columns exist (lightweight migration)
        # if you prefer clean migrations, add these columns in SQL instead.
        try:
            await self.bot.db.execute("ALTER TABLE guild_settings ADD COLUMN casino_recap_last_ts INTEGER NOT NULL DEFAULT 0;")
        except Exception:
            pass

    async def _get_last_recap_ts(self, gid: int) -> int:
        row = await self.bot.db.fetchone("SELECT casino_recap_last_ts FROM guild_settings WHERE guild_id=?", (gid,))
        if not row:
            return 0
        return int(row["casino_recap_last_ts"] or 0)

    async def _set_last_recap_ts(self, gid: int, ts: int):
        await self.bot.db.execute("UPDATE guild_settings SET casino_recap_last_ts=? WHERE guild_id=?", (int(ts), gid))

    def _high_activity(self, summary: dict) -> bool:
        """
        Tune thresholds here.
        High activity defaults:
          - total wagered >= 25,000 OR
          - rounds >= 120 OR
          - unique users >= 25
        """
        min_total_wagered = int(self.bot.cfg.get("casino_recap", "min_total_wagered", default=25000))
        min_rounds = int(self.bot.cfg.get("casino_recap", "min_rounds", default=120))
        min_unique_players = int(self.bot.cfg.get("casino_recap", "min_unique_players", default=25))
        
        return (
            int(summary["total_wagered"]) >= min_total_wagered
            or int(summary["rounds"]) >= min_rounds
            or int(summary["unique_users"]) >= min_unique_players
        )

    def _line(self) -> tuple[str, str]:
        openers = [
            "I looked at the casino today.",
            "I checked the tables.",
            "I read the casino logs."
        ]
        closers = [
            "If you want to be noticed tomorrow, you know what to do.",
            "Try harder tomorrow.",
            "I'll be watching again."
        ]
        return random.choice(openers), random.choice(closers)

    async def _post_recap(self, guild: discord.Guild, summary: dict, since_ts: int):
        spotlight_id = int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)
        ch = guild.get_channel(spotlight_id) if spotlight_id else None
        if not isinstance(ch, discord.TextChannel):
            return

        # Build spotlight users and spoiler pings
        featured = set()

        for uid, _w in (summary.get("top_spenders") or [])[:3]:
            featured.add(int(uid))

        bw = summary.get("biggest_wager")
        if bw and bw.get("uid"):
            featured.add(int(bw["uid"]))

        bnw = summary.get("biggest_net_win")
        if bnw and bnw.get("uid"):
            featured.add(int(bnw["uid"]))

        mp = (summary.get("most_played") or [])
        if mp:
            featured.add(int(mp[0][0]))

        pings = " ".join([f"||<@{uid}>||" for uid in list(featured)[:10]])

        opener, closer = self._line()

        # Sections
        total_wagered = int(summary["total_wagered"])
        rounds = int(summary["rounds"])
        uniq = int(summary["unique_users"])

        lines = []
        lines.append(f"{opener}\n")
        lines.append(f"Last 24h: **{fmt(total_wagered)} Coins wagered**")
        lines.append(f"Rounds: **{fmt(rounds)}**")
        lines.append(f"Players: **{fmt(uniq)}**\n")

        # Top spenders
        spenders = summary.get("top_spenders") or []
        if spenders:
            lines.append("**Top spenders**")
            for i, (uid, w) in enumerate(spenders[:3], start=1):
                lines.append(f"**#{i}** <@{int(uid)}> — **{fmt(int(w))} Coins**")
            lines.append("")

        # Biggest wager
        if bw:
            lines.append("**Biggest wager**")
            lines.append(f"<@{int(bw['uid'])}> — **{fmt(int(bw['wager']))} Coins** on **{bw['game']}**")
            lines.append("")

        # Biggest net win
        if bnw:
            lines.append("**Biggest win**")
            lines.append(f"<@{int(bnw['uid'])}> — **+{fmt(int(bnw['net']))} Coins** on **{bnw['game']}**")
            lines.append("")

        # Most games played
        if mp:
            uid, cnt = mp[0]
            lines.append("**Most games played**")
            lines.append(f"<@{int(uid)}> — **{fmt(int(cnt))} rounds**")
            lines.append("")

        lines.append(closer)
        lines.append("᲼᲼")

        # Daily recap is a system message (sent to channel, includes author)
        from utils.embed_utils import create_embed
        from core.isla_text import sanitize_isla_text
        embed = create_embed(
            description=sanitize_isla_text("\n".join(lines)),
            color="casino",
            thumbnail=random.choice(CASINO_THUMBS),
            is_dm=False,
            is_system=True  # System message - includes author
        )
        await ch.send(content=pings, embed=embed)

    @tasks.loop(time=time(hour=21, minute=15, tzinfo=UK_TZ))  # daily evening recap UK
    async def recap_loop(self):
        await self.bot.wait_until_ready()

        casino = self.bot.get_cog("CasinoCore")
        if not casino or not hasattr(casino, "get_window_summary"):
            return

        for guild in self.bot.guilds:
            try:
                await self._ensure_settings(guild.id)

                # one recap per ~20 hours max
                last_ts = await self._get_last_recap_ts(guild.id)
                if last_ts and (now_ts() - last_ts) < 20 * 3600:
                    continue

                since_ts = now_ts() - 24 * 3600
                summary = await casino.get_window_summary(guild.id, since_ts)

                if not self._high_activity(summary):
                    continue

                await self._post_recap(guild, summary, since_ts)
                await self._set_last_recap_ts(guild.id, now_ts())

            except Exception:
                continue


async def setup(bot: commands.Bot):
    await bot.add_cog(CasinoDailyRecap(bot))

