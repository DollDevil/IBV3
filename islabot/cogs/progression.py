from __future__ import annotations

import math
import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts, now_local, fmt
from utils.helpers import isla_embed as helper_isla_embed
from utils.embed_utils import create_embed


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


def isla_embed(desc: str, icon: str) -> discord.Embed:
    return helper_isla_embed(desc, icon=icon)


def week_key_uk() -> str:
    t = now_local()
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"


class Progression(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    async def _ensure_user(self, gid: int, uid: int):
        row = await self.bot.db.fetchone("SELECT user_id FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if not row:
            start = int(self.bot.cfg.get("economy", "start_balance", default=250))
            await self.bot.db.execute(
                "INSERT INTO users(guild_id,user_id,coins,obedience,xp,lce,last_active_ts) VALUES(?,?,?,?,?,?,?)",
                (gid, uid, start, 0, 0, 0, now_ts())
            )

    def rank_for_obedience(self, obedience: int) -> str:
        current = RANKS[0][0]
        for name, req in RANKS:
            if obedience >= req:
                current = name
        return current

    def next_rank(self, obedience: int):
        for name, req in RANKS:
            if obedience < req:
                return name, req
        return None, None

    # ---- WAS formula (tunable) ----
    def compute_was(self, msg_count: int, react_count: int, voice_seconds: int, casino_wagered: int) -> int:
        voice_minutes = voice_seconds // 60
        # Weighted: chat + reacts + voice + casino engagement
        score = (
            msg_count * 3 +
            react_count * 1 +
            min(voice_minutes, 600) * 2 +                 # cap 10h per week contribution
            int(math.sqrt(max(casino_wagered, 0))) * 2    # diminishing returns
        )
        return int(score)

    def weekly_bonus_from_was(self, was: int) -> int:
        # Smooth scaling, not punishing: 200..3000-ish
        base = 200
        bonus = base + int(min(2800, math.sqrt(max(was, 0)) * 35))
        return bonus

    async def update_weekly_was(self, gid: int, uid: int):
        wk = week_key_uk()
        row = await self.bot.db.fetchone(
            "SELECT msg_count, react_count, voice_seconds, casino_wagered FROM weekly_stats WHERE guild_id=? AND week_key=? AND user_id=?",
            (gid, wk, uid)
        )
        if not row:
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO weekly_stats(guild_id,week_key,user_id) VALUES(?,?,?)",
                (gid, wk, uid)
            )
            row = {"msg_count": 0, "react_count": 0, "voice_seconds": 0, "casino_wagered": 0}

        was = self.compute_was(int(row["msg_count"]), int(row["react_count"]), int(row["voice_seconds"]), int(row["casino_wagered"]))
        await self.bot.db.execute(
            "UPDATE weekly_stats SET was=? WHERE guild_id=? AND week_key=? AND user_id=?",
            (was, gid, wk, uid)
        )
        return was

    # ---- Slash commands ----
    @app_commands.command(name="rank", description="Show your rank ladder progress.")
    async def rank(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        await self._ensure_user(gid, uid)

        row = await self.bot.db.fetchone("SELECT obedience, xp FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        obedience = int(row["obedience"]) if row else 0
        cur_rank = self.rank_for_obedience(obedience)
        nxt_name, nxt_req = self.next_rank(obedience)
        if nxt_name:
            need = max(0, nxt_req - obedience)
            desc = f"{interaction.user.mention}\nRank: **{cur_rank}**\nObedience: **{fmt(obedience)}**\nNext: **{nxt_name}** in **{fmt(need)}**.\n᲼᲼"
        else:
            desc = f"{interaction.user.mention}\nRank: **{cur_rank}**\nObedience: **{fmt(obedience)}**\nYou're capped.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="weekly", description="Claim your weekly activity bonus (Coins).")
    async def weekly(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        await self._ensure_user(gid, uid)
        wk = week_key_uk()

        await self.bot.db.execute(
            "INSERT OR IGNORE INTO weekly_stats(guild_id,week_key,user_id) VALUES(?,?,?)",
            (gid, wk, uid)
        )

        row = await self.bot.db.fetchone(
            "SELECT was, weekly_bonus_claimed FROM weekly_stats WHERE guild_id=? AND week_key=? AND user_id=?",
            (gid, wk, uid)
        )
        if not row:
            claimed = 0
            was = 0
        else:
            claimed = int(row["weekly_bonus_claimed"])
            was = int(row["was"] or 0)
            
        if claimed:
            embed = create_embed("You already claimed this week.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        was = await self.update_weekly_was(gid, uid)
        bonus = self.weekly_bonus_from_was(was)

        await self.bot.db.execute("UPDATE users SET coins = coins + ? WHERE guild_id=? AND user_id=?", (bonus, gid, uid))
        await self.bot.db.execute("UPDATE weekly_stats SET weekly_bonus_claimed=1 WHERE guild_id=? AND week_key=? AND user_id=?", (gid, wk, uid))

        desc = f"{interaction.user.mention}\nWeekly bonus: **{fmt(bonus)} Coins**\nWAS: **{fmt(was)}**\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    # Top 3 praise list for Isla's morning/spotlight use
    async def top3_weekly(self, gid: int):
        wk = week_key_uk()
        rows = await self.bot.db.fetchall(
            "SELECT user_id, was FROM weekly_stats WHERE guild_id=? AND week_key=? ORDER BY was DESC LIMIT 3",
            (gid, wk)
        )
        result = []
        for r in rows:
            result.append((int(r["user_id"]), int(r["was"])))
        return result


async def setup(bot: commands.Bot):
    await bot.add_cog(Progression(bot))

