from __future__ import annotations
import random
import discord
from discord.ext import commands
from discord import app_commands

from utils.isla_style import isla_embed, fmt
from utils.economy import ensure_wallet, get_wallet, add_coins

class DuelAcceptView(discord.ui.View):
    def __init__(self, bot: commands.Bot, challenger_id: int, target_id: int, amount: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.challenger_id = challenger_id
        self.target_id = target_id
        self.amount = amount
        self.resolved = False

    async def _resolve(self, interaction: discord.Interaction, accepted: bool):
        if self.resolved:
            return
        self.resolved = True
        for item in self.children:
            item.disabled = True

        if not accepted:
            await interaction.response.edit_message(
                content="",
                embed=isla_embed("Declined.\n᲼᲼", title="Duel"),
                view=self
            )
            return

        guild_id = interaction.guild_id
        if not guild_id:
            return await interaction.response.edit_message(embed=isla_embed("Server only.\n᲼᲼", title="Duel"), view=self)

        # Ensure wallets + balance checks (again, at accept time)
        await ensure_wallet(self.bot.db, guild_id, self.challenger_id)
        await ensure_wallet(self.bot.db, guild_id, self.target_id)

        w1 = await get_wallet(self.bot.db, guild_id, self.challenger_id)
        w2 = await get_wallet(self.bot.db, guild_id, self.target_id)

        if w1.coins < self.amount or w2.coins < self.amount:
            return await interaction.response.edit_message(
                embed=isla_embed("Someone can't cover the stake.\n᲼᲼", title="Duel"),
                view=self
            )

        # Deduct both stakes
        await add_coins(self.bot.db, guild_id, self.challenger_id, -self.amount, kind="duel_stake", reason="duel stake", other_user_id=self.target_id)
        await add_coins(self.bot.db, guild_id, self.target_id, -self.amount, kind="duel_stake", reason="duel stake", other_user_id=self.challenger_id)

        # Minigame: best of 3 "dice" (more fun than pure coinflip)
        scores = {self.challenger_id: 0, self.target_id: 0}
        rounds = []
        while scores[self.challenger_id] < 2 and scores[self.target_id] < 2:
            r1 = random.randint(1, 6)
            r2 = random.randint(1, 6)
            rounds.append((r1, r2))
            if r1 > r2:
                scores[self.challenger_id] += 1
            elif r2 > r1:
                scores[self.target_id] += 1

        winner = self.challenger_id if scores[self.challenger_id] > scores[self.target_id] else self.target_id
        pot = self.amount * 2

        await add_coins(self.bot.db, guild_id, winner, pot, kind="duel_win", reason="duel pot")

        # Render
        ch = interaction.guild.get_member(self.challenger_id)
        tg = interaction.guild.get_member(self.target_id)
        ch_name = ch.display_name if ch else "Challenger"
        tg_name = tg.display_name if tg else "Target"

        lines = []
        for i, (a, b) in enumerate(rounds, start=1):
            lines.append(f"Round {i}: {ch_name} **{a}** vs {tg_name} **{b}**")

        desc = (
            "Duel.\n\n"
            + "\n".join(lines)
            + f"\n\nWinner: <@{winner}>\n"
            + f"Pot: **{fmt(pot)} Coins**\n"
            "᲼᲼"
        )
        await interaction.response.edit_message(content="", embed=isla_embed(desc, title="Duel"), view=self)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(embed=isla_embed("Not for you.\n᲼᲼", title="Duel"), ephemeral=True)
        await self._resolve(interaction, accepted=True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(embed=isla_embed("Not for you.\n᲼᲼", title="Duel"), ephemeral=True)
        await self._resolve(interaction, accepted=False)

class DuelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="duel", description="Both stake Coins; minigame determines winner.")
    @app_commands.describe(user="Opponent", amount="Stake amount")
    async def duel(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return await interaction.followup.send("Server only.", ephemeral=True)

        if user.bot or user.id == interaction.user.id:
            return await interaction.followup.send(embed=isla_embed("No.\n᲼᲼", title="Duel"), ephemeral=True)

        amount = int(amount)
        if amount <= 0:
            return await interaction.followup.send(embed=isla_embed("Use a real number.\n᲼᲼", title="Duel"), ephemeral=True)

        gid = interaction.guild_id
        await ensure_wallet(self.bot.db, gid, interaction.user.id)
        await ensure_wallet(self.bot.db, gid, user.id)

        w1 = await get_wallet(self.bot.db, gid, interaction.user.id)
        if w1.coins < amount:
            return await interaction.followup.send(embed=isla_embed("You can't cover that stake.\n᲼᲼", title="Duel"), ephemeral=True)

        # Public challenge message in the channel (no @everyone)
        view = DuelAcceptView(self.bot, interaction.user.id, user.id, amount)
        embed = isla_embed(
            f"{user.mention}\n\n"
            f"{interaction.user.mention} wants a duel.\n"
            f"Stake: **{fmt(amount)} Coins** each.\n"
            "᲼᲼",
            title="Duel Request"
        )
        await interaction.followup.send("Posted.\n᲼᲼", ephemeral=True)
        await interaction.channel.send(content=f"{user.mention}", embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(DuelCog(bot))

