"""
Event Boss Command

Shows current boss HP, recent damage, and leaderboards.
Works for holiday weeks and seasonal eras.
"""

from __future__ import annotations
import time
import discord
from discord.ext import commands
from discord import app_commands
from utils.uk_time import uk_day_ymd
from utils.embed_utils import create_embed

def now_ts() -> int:
    return int(time.time())

def isla_embed(desc: str, title: str | None = None, icon_url: str = "https://i.imgur.com/5nsuuCV.png") -> discord.Embed:
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=icon_url)
    return e

def fmt_int(n: int | float) -> str:
    try:
        n = int(n)
    except Exception:
        n = 0
    return f"{n:,}"

class EventBossCmd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Helper: pick which event to show (priority: holiday_week > season_era, else first active)
    async def _pick_active_event(self, gid: int) -> str | None:
        rows = await self.bot.db.fetchall(
            "SELECT event_id, event_type FROM events WHERE guild_id=? AND is_active=1",
            (gid,)
        )
        if not rows:
            return None
        # prioritize holiday weeks
        for r in rows:
            if str(r["event_type"]) == "holiday_week":
                return str(r["event_id"])
        # else prefer season_era
        for r in rows:
            if str(r["event_type"]) == "season_era":
                return str(r["event_id"])
        return str(rows[0]["event_id"])

    @app_commands.command(name="event_boss", description="View the current event boss status.")
    async def event_boss(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        gid = interaction.guild_id
        event_id = await self._pick_active_event(gid)
        if not event_id:
            return await interaction.followup.send(
                embed=isla_embed("No active event boss right now.\n᲼᲼", title="Boss"),
                ephemeral=True
            )

        meta = await self.bot.db.fetchone(
            "SELECT name, event_type, token_name FROM events WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        if not boss:
            return await interaction.followup.send(
                embed=isla_embed("No boss is attached to the current event.\n᲼᲼", title="Boss"),
                ephemeral=True
            )

        boss_name = str(boss["boss_name"])
        hp_cur = int(boss["hp_current"])
        hp_max = max(1, int(boss["hp_max"]))
        hp_pct = max(0, min(100, int((hp_cur / hp_max) * 100)))

        # Top 3 today (UK day)
        today = uk_day_ymd(now_ts())
        top_today = await self.bot.db.fetchall(
            """
            SELECT user_id, dp_cached AS pts
            FROM event_user_day
            WHERE guild_id=? AND event_id=? AND day_ymd=?
            ORDER BY pts DESC
            LIMIT 3
            """,
            (gid, event_id, today)
        )

        # Top 10 overall
        top_overall = await self.bot.db.fetchall(
            """
            SELECT user_id, SUM(dp_cached) AS pts
            FROM event_user_day
            WHERE guild_id=? AND event_id=?
            GROUP BY user_id
            ORDER BY pts DESC
            LIMIT 10
            """,
            (gid, event_id)
        )

        # Recent damage window (optional) - last 6 hours
        recent_damage = None
        try:
            cutoff = now_ts() - (6 * 3600)
            r = await self.bot.db.fetchone(
                """
                SELECT COALESCE(SUM(damage_total), 0) AS dmg
                FROM event_boss_tick
                WHERE guild_id=? AND event_id=? AND ts >= ?
                """,
                (gid, event_id, cutoff)
            )
            recent_damage = int(float(r["dmg"] or 0))
        except Exception:
            recent_damage = None

        # Format leaderboard lines
        def line_for(uid: int, pts: float) -> str:
            m = interaction.guild.get_member(int(uid))
            name = m.display_name if m else f"User {uid}"
            return f"{name} — {fmt_int(pts)}"

        today_lines = []
        for i, r in enumerate(top_today, start=1):
            today_lines.append(f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}")
        if not today_lines:
            today_lines = ["No data yet."]

        overall_lines = []
        for i, r in enumerate(top_overall, start=1):
            overall_lines.append(f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}")
        if not overall_lines:
            overall_lines = ["No data yet."]

        event_name = str(meta["name"]) if meta else "Event"
        event_type = str(meta["event_type"]) if meta else "event"
        token_name = str(meta["token_name"]) if meta else "Tokens"

        desc = (
            f"**{boss_name}**\n"
            f"HP: **{fmt_int(hp_cur)} / {fmt_int(hp_max)}** (**{hp_pct}%**)\n"
        )
        if recent_damage is not None:
            desc += f"Recent damage (6h): **{fmt_int(recent_damage)}**\n"
        desc += "᲼᲼"

        e = isla_embed(desc, title=f"{event_name} Boss")

        e.add_field(
            name="Top Damage Today",
            value="\n".join(today_lines),
            inline=False
        )
        e.add_field(
            name="Top Damage Overall",
            value="\n".join(overall_lines[:10]),
            inline=False
        )

        e.add_field(
            name="Event",
            value=f"{event_type}\nToken: {token_name}",
            inline=True
        )
        e.set_footer(text="Use /event to see more event options.")

        await interaction.followup.send(embed=e, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EventBossCmd(bot))

