from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from core.utils import fmt, now_ts
from core.isla_text import sanitize_isla_text
from utils.helpers import isla_embed as helper_isla_embed

def vacation_badge(vac_until: int, vac_last_used: int) -> str:
    """Returns vacation status badge text."""
    now = now_ts()
    if vac_until > now:
        return "🏖️ Vacation"
    cd_end = (vac_last_used or 0) + 24*3600
    if cd_end > now:
        return "⏳ Vacation Cooldown"
    return ""


def isla_embed(desc: str, icon: str) -> discord.Embed:
    return helper_isla_embed(desc, icon=icon)

# Reuse RANKS from progression module
RANKS = [
    ("Stray", 0),
    ("Worthless Pup", 500),
    ("Leashed Pup", 1000),
    ("Collared Dog", 5000),
    ("Trained Pet", 10000),
    ("Devoted Dog", 15000),
    ("Cherished Pet", 20000),
    ("Favorite Puppy", 50000),
]


def rank_for_obedience(obedience: int) -> str:
    cur = RANKS[0][0]
    for name, req in RANKS:
        if obedience >= req:
            cur = name
    return cur


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    @app_commands.command(name="profile", description="Show a user's profile.")
    async def profile(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        gid = interaction.guild_id
        user = user or interaction.user
        row = await self.bot.db.fetchone(
            "SELECT coins, obedience, xp, lce, vacation_until_ts, vacation_last_used_ts, safeword_on FROM users WHERE guild_id=? AND user_id=?",
            (gid, user.id)
        )
        if not row:
            return await interaction.response.send_message("No data yet.", ephemeral=True)

        coins = int(row["coins"])
        obedience = int(row["obedience"])
        xp = int(row["xp"])
        lce = int(row["lce"])
        vac_until = int(row["vacation_until_ts"] or 0)
        vac_last_used = int(row["vacation_last_used_ts"] or 0)
        safeword_on = int(row["safeword_on"] or 0)

        rank = rank_for_obedience(obedience)

        # Equipped collar (optional)
        eq = await self.bot.db.fetchone(
            "SELECT item_id FROM equips WHERE guild_id=? AND user_id=? AND slot='collar'",
            (gid, user.id)
        )
        collar = f"`{eq['item_id']}`" if eq else "None"

        # Equipped badge (optional)
        bq = await self.bot.db.fetchone(
            "SELECT item_id FROM equips WHERE guild_id=? AND user_id=? AND slot='badge'",
            (gid, user.id)
        )
        badge = f"`{bq['item_id']}`" if bq else "None"

        desc = (
            f"{user.mention}\n"
            f"Rank: **{rank}**\n"
            f"Coins: **{fmt(coins)}**\n"
            f"Obedience: **{fmt(obedience)}**\n"
            f"XP: **{fmt(xp)}**\n"
            f"LCE: **{fmt(lce)}**\n"
            f"Collar: {collar}\n"
            f"Badge: {badge}\n"
            f"᲼᲼"
        )
        e = isla_embed(desc, self.icon)
        
        # Status badges (vacation + safeword)
        status_badges = []
        vac_badge = vacation_badge(vac_until, vac_last_used)
        if vac_badge:
            status_badges.append(vac_badge)
        if safeword_on:
            status_badges.append("🧷 Safeword On (Neutral)")
        if status_badges:
            e.add_field(name="Status", value=" • ".join(status_badges), inline=True)
        
        # Vacation time remaining
        now = now_ts()
        if vac_until > now:
            left = vac_until - now
            days = left // 86400
            hours = (left % 86400) // 3600
            e.add_field(name="Vacation", value=f"Active • {days}d {hours}h left", inline=False)
        elif (vac_last_used + 86400) > now:
            left = (vac_last_used + 86400) - now
            hours = left // 3600
            minutes = (left % 3600) // 60
            e.add_field(name="Vacation", value=f"Cooldown • {hours}h {minutes}m left", inline=False)
        
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="leaderboard", description="Show top users by a stat.")
    @app_commands.describe(stat="coins|obedience|xp|lce")
    async def leaderboard(self, interaction: discord.Interaction, stat: str = "obedience"):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        gid = interaction.guild_id
        stat = stat.lower().strip()
        if stat not in ("coins", "obedience", "xp", "lce"):
            stat = "obedience"

        rows = await self.bot.db.fetchall(
            f"SELECT user_id,{stat} as v FROM users WHERE guild_id=? ORDER BY v DESC LIMIT 10",
            (gid,)
        )
        if not rows:
            return await interaction.response.send_message("No data.", ephemeral=True)

        lines = []
        for i, r in enumerate(rows, start=1):
            lines.append(f"**{i}.** <@{int(r['user_id'])}> — **{fmt(int(r['v']))}**")

        desc = f"{interaction.user.mention}\nTop 10 by **{stat}**\n\n" + "\n".join(lines) + "\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, "https://i.imgur.com/5nsuuCV.png"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
