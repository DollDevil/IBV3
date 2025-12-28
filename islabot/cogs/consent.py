from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
from core.utils import now_ts
from core.tone import pick, DEFAULT_POOLS
from utils.embed_utils import create_embed

MODULES = {
    "orders": "opt_orders",
    "public_callouts": "opt_public_callouts",
    "dm": "opt_dm",
    "humiliation": "opt_humiliation",
}

class Consent(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _stage(self, gid: int, uid: int) -> int:
        row = await self.bot.db.fetchone("SELECT stage FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        cap = await self.bot.db.fetchone("SELECT stage_cap FROM server_state WHERE guild_id=?", (gid,))
        stage = int(row["stage"] if row else 0)
        stage_cap = int(cap["stage_cap"] if cap else self.bot.cfg.get("isla", "stage_cap", default=4))
        return min(stage, stage_cap)

    @app_commands.command(name="verify", description="Grant required server roles (18+ verified + consent).")
    async def verify(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        g = interaction.guild
        m = interaction.user
        gid, uid = g.id, m.id
        await self.bot.db.ensure_user(gid, uid)

        r18 = self.bot.cfg.get("roles", "verified_18")
        rcons = self.bot.cfg.get("roles", "consent")

        # Best-effort role grants (server chooses how strict this is)
        added = []
        if r18:
            role = g.get_role(int(r18))
            if role and role not in m.roles:
                try:
                    await m.add_roles(role, reason="Isla verify")
                    added.append(role.name)
                except discord.Forbidden:
                    pass
        if rcons:
            role = g.get_role(int(rcons))
            if role and role not in m.roles:
                try:
                    await m.add_roles(role, reason="Isla verify")
                    added.append(role.name)
                except discord.Forbidden:
                    pass

        await self.bot.db.execute(
            "UPDATE consent SET verified_18=1, consent_ok=1 WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        embed = create_embed(f"Verified. Roles added: {', '.join(added) if added else '—'}", color="success", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="consent", description="View or change consent modules.")
    async def consent(self, interaction: discord.Interaction, action: str, module: str | None = None):
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid, uid = interaction.guild.id, interaction.user.id
        await self.bot.db.ensure_user(gid, uid)

        action = action.lower().strip()
        if action == "view":
            row = await self.bot.db.fetchone("SELECT * FROM consent WHERE guild_id=? AND user_id=?", (gid, uid))
            if not row:
                embed = create_embed("No consent record.", color="info", is_dm=False, is_system=False)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            lines = []
            for k, col in MODULES.items():
                lines.append(f"- {k}: {'✅' if int(row[col]) == 1 else '❌'}")
            lines.append(f"- verified_18: {'✅' if int(row['verified_18']) == 1 else '❌'}")
            lines.append(f"- consent_ok: {'✅' if int(row['consent_ok']) == 1 else '❌'}")
            embed = create_embed("\n".join(lines), color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if action not in ("optin", "optout") or not module or module not in MODULES:
            embed = create_embed("Use: /consent action:view OR /consent action:optin|optout module:orders|public_callouts|dm|humiliation", color="warning", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        col = MODULES[module]
        val = 1 if action == "optin" else 0
        await self.bot.db.execute(f"UPDATE consent SET {col}=? WHERE guild_id=? AND user_id=?", (val, gid, uid))
        embed = create_embed(f"{module} set to {'ON' if val else 'OFF'}.", color="success", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # NOTE: /safeword command moved to cogs/safeword.py (new system)
    # Old safeword_until_ts system removed in favor of safeword_on toggle

    @app_commands.command(name="resetme", description="Reset your Isla stats (coins/consent/orders).")
    async def resetme(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, interaction.user.id
        await self.bot.db.ensure_user(gid, uid)

        await self.bot.db.execute("DELETE FROM orders_active WHERE guild_id=? AND user_id=?", (gid, uid))
        await self.bot.db.execute("UPDATE users SET coins=0,lce=0,debt=0,stage=0,daily_claim_day=NULL,safeword_until_ts=NULL WHERE guild_id=? AND user_id=?", (gid, uid))
        await self.bot.db.execute("UPDATE consent SET opt_orders=0,opt_public_callouts=0,opt_dm=0,opt_humiliation=0 WHERE guild_id=? AND user_id=?", (gid, uid))

        embed = create_embed("Reset complete.", color="success", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Consent(bot))

