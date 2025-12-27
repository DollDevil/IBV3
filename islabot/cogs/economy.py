from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts, fmt
from utils.helpers import isla_embed as helper_isla_embed

def isla_embed(desc: str, icon: str) -> discord.Embed:
    return helper_isla_embed(desc, icon=icon)


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    async def _ensure_user(self, gid: int, uid: int):
        row = await self.bot.db.fetchone(
            "SELECT coins FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        if row is None:
            start = int(self.bot.cfg.get("economy", "start_balance", default=250))
            await self.bot.db.execute(
                "INSERT INTO users(guild_id,user_id,coins,lce,last_active_ts) VALUES(?,?,?,?,?)",
                (gid, uid, start, 0, now_ts())
            )

    async def _add_coins(self, gid: int, uid: int, delta: int, reason: str):
        await self._ensure_user(gid, uid)
        await self.bot.db.execute(
            "UPDATE users SET coins = coins + ? WHERE guild_id=? AND user_id=?",
            (delta, gid, uid)
        )
        await self.bot.db.execute(
            "INSERT INTO coin_ledger(guild_id,user_id,ts,delta,reason) VALUES(?,?,?,?,?)",
            (gid, uid, now_ts(), delta, reason)
        )

    async def _get_coins(self, gid: int, uid: int) -> int:
        await self._ensure_user(gid, uid)
        row = await self.bot.db.fetchone(
            "SELECT coins FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        return int(row["coins"]) if row else 0

    @app_commands.command(name="balance", description="Check your Coins.")
    async def balance(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        coins = await self._get_coins(gid, uid)
        desc = f"{interaction.user.mention}\nYou have **{fmt(coins)} Coins**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="pay", description="Send Coins to someone.")
    @app_commands.describe(user="Who to pay", amount="Coins to send")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("Amount must be > 0.", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("Not to bots.", ephemeral=True)

        gid = interaction.guild_id
        payer = interaction.user.id
        receiver = user.id

        payer_bal = await self._get_coins(gid, payer)
        if payer_bal < amount:
            return await interaction.response.send_message("Not enough Coins.", ephemeral=True)

        await self._add_coins(gid, payer, -amount, f"pay:{receiver}")
        await self._add_coins(gid, receiver, +amount, f"receive:{payer}")

        desc = f"{interaction.user.mention} paid {user.mention} **{fmt(amount)} Coins**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon))

    # Admin tools
    @app_commands.command(name="coins_add", description="(Admin) Add Coins to a user.")
    @app_commands.checks.has_permissions(administrator=True)
    async def coins_add(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = "admin"):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        gid = interaction.guild_id
        await self._add_coins(gid, user.id, amount, f"admin_add:{reason}")
        desc = f"{user.mention} received **{fmt(amount)} Coins**.\nReason: {reason}\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="coins_set", description="(Admin) Set a user's Coins.")
    @app_commands.checks.has_permissions(administrator=True)
    async def coins_set(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        gid = interaction.guild_id
        await self._ensure_user(gid, user.id)
        await self.bot.db.execute(
            "UPDATE users SET coins=? WHERE guild_id=? AND user_id=?",
            (amount, gid, user.id)
        )
        desc = f"{user.mention} now has **{fmt(amount)} Coins**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
