from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from utils.isla_style import isla_embed, fmt
from utils.uk_parse import parse_when_to_ts, human_eta, now_ts
from utils.economy import ensure_wallet, get_wallet, add_coins

class EventCreateModal(discord.ui.Modal, title="Create Event"):
    title_in = discord.ui.TextInput(label="Title", max_length=80)
    start_in = discord.ui.TextInput(label="Start (UK): 'in 2h' or 'YYYY-MM-DD HH:MM'", max_length=32)
    desc_in = discord.ui.TextInput(label="Description", style=discord.TextStyle.long, required=False, max_length=1000)
    entry_in = discord.ui.TextInput(label="Entry Cost (Coins)", default="0", max_length=10)
    role_in = discord.ui.TextInput(label="Role ID (optional)", required=False, max_length=24)

    def __init__(self, bot: commands.Bot, channel_id: int):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            return await interaction.response.send_message("Server only.", ephemeral=True)

        start_ts = parse_when_to_ts(str(self.start_in.value))
        if start_ts <= now_ts():
            return await interaction.response.send_message(embed=isla_embed("Bad start time.\n᲼᲼", title="Event Create"), ephemeral=True)

        try:
            entry_cost = max(0, int(str(self.entry_in.value).strip()))
        except Exception:
            entry_cost = 0

        role_id = 0
        if str(self.role_in.value).strip():
            try:
                role_id = int(str(self.role_in.value).strip())
            except Exception:
                role_id = 0

        await self.bot.db.execute(
            """
            INSERT INTO events_custom(guild_id,title,description,start_ts,end_ts,channel_id,role_id,entry_cost,reward_coins,max_slots,created_by,created_ts,active)
            VALUES(?,?,?,?,0,?,?,?,?,0,?,?,1)
            """,
            (gid, str(self.title_in.value), str(self.desc_in.value or ""), int(start_ts), int(self.channel_id),
             int(role_id), int(entry_cost), 0, int(interaction.user.id), now_ts())
        )

        row = await self.bot.db.fetchone(
            "SELECT MAX(event_id) AS eid FROM events_custom WHERE guild_id=?",
            (gid,)
        )
        eid = int(row["eid"] or 0)

        e = isla_embed(
            f"Event created.\n\n"
            f"**#{eid}** — {self.title_in.value}\n"
            f"Starts: {human_eta(start_ts)}\n"
            f"Entry: **{fmt(entry_cost)} Coins**\n"
            "᲼᲼",
            title="Event"
        )

        await interaction.response.send_message(embed=e, ephemeral=True)

class CustomEventsGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.calendar = app_commands.Group(name="calendar", description="Server calendar events")

        self._register()

    def _is_mod(self, m: discord.Member) -> bool:
        p = m.guild_permissions
        return p.manage_guild or p.manage_events or p.administrator

    # /event create
    @app_commands.command(name="create", description="Interactive event wizard.")
    async def create(self, interaction: discord.Interaction):
        if not interaction.guild_id or not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not self._is_mod(interaction.user):
            return await interaction.response.send_message(embed=isla_embed("Not for you.\n᲼᲼", title="Event"), ephemeral=True)

        await interaction.response.send_modal(EventCreateModal(self.bot, interaction.channel_id))

    # /event list
    @app_commands.command(name="list", description="Upcoming events.")
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        rows = await self.bot.db.fetchall(
            """
            SELECT event_id,title,start_ts,entry_cost
            FROM events_custom
            WHERE guild_id=? AND active=1 AND start_ts >= ?
            ORDER BY start_ts ASC
            LIMIT 10
            """,
            (gid, now_ts())
        )
        if not rows:
            return await interaction.followup.send(embed=isla_embed("No upcoming events.\n᲼᲼", title="Events"), ephemeral=True)

        lines = []
        for r in rows:
            lines.append(f"**#{r['event_id']}** {r['title']} — <t:{int(r['start_ts'])}:R> — {fmt(int(r['entry_cost']))} Coins")

        e = isla_embed("Upcoming.\n᲼᲼", title="Events")
        e.add_field(name="List", value="\n".join(lines), inline=False)
        e.set_footer(text="Join with /calendar join <event_id>")
        await interaction.followup.send(embed=e, ephemeral=True)

    # /event join <event_id>
    @app_commands.command(name="join", description="Join event and get role.")
    @app_commands.describe(event_id="Event ID")
    async def join(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self.bot.db.fetchone(
            "SELECT title,start_ts,channel_id,role_id,entry_cost,active FROM events_custom WHERE guild_id=? AND event_id=?",
            (gid, int(event_id))
        )
        if not ev or int(ev["active"]) != 1:
            return await interaction.followup.send(embed=isla_embed("No such event.\n᲼᲼", title="Event"), ephemeral=True)

        # already joined?
        existing = await self.bot.db.fetchone(
            "SELECT 1 FROM events_custom_participants WHERE guild_id=? AND event_id=? AND user_id=?",
            (gid, int(event_id), interaction.user.id)
        )
        if existing:
            return await interaction.followup.send(embed=isla_embed("You're already in.\n᲼᲼", title="Event"), ephemeral=True)

        entry = int(ev["entry_cost"] or 0)
        if entry > 0:
            await ensure_wallet(self.bot.db, gid, interaction.user.id)
            w = await get_wallet(self.bot.db, gid, interaction.user.id)
            if w.coins < entry:
                return await interaction.followup.send(embed=isla_embed("You can't cover the entry cost.\n᲼᲼", title="Event"), ephemeral=True)
            await add_coins(self.bot.db, gid, interaction.user.id, -entry, kind="event_entry", reason=f"event #{event_id}")

        await self.bot.db.execute(
            "INSERT INTO events_custom_participants(guild_id,event_id,user_id,joined_ts) VALUES(?,?,?,?)",
            (gid, int(event_id), interaction.user.id, now_ts())
        )

        role_id = int(ev["role_id"] or 0)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role, reason="event join")
                except Exception:
                    pass

        e = isla_embed(
            f"Joined.\n\n"
            f"Event **#{event_id}** — {ev['title']}\n"
            f"Starts: <t:{int(ev['start_ts'])}:R>\n"
            "᲼᲼",
            title="Event"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # /event leave <event_id>
    @app_commands.command(name="leave", description="Leave an event.")
    @app_commands.describe(event_id="Event ID")
    async def leave(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self.bot.db.fetchone(
            "SELECT role_id,active FROM events_custom WHERE guild_id=? AND event_id=?",
            (gid, int(event_id))
        )
        if not ev or int(ev["active"]) != 1:
            return await interaction.followup.send(embed=isla_embed("No such event.\n᲼᲼", title="Event"), ephemeral=True)

        await self.bot.db.execute(
            "DELETE FROM events_custom_participants WHERE guild_id=? AND event_id=? AND user_id=?",
            (gid, int(event_id), interaction.user.id)
        )

        role_id = int(ev["role_id"] or 0)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.remove_roles(role, reason="event leave")
                except Exception:
                    pass

        e = isla_embed("Removed.\n᲼᲼", title="Event")
        await interaction.followup.send(embed=e, ephemeral=True)

    def _register(self):
        self.calendar.add_command(self.create)
        self.calendar.add_command(self.join)
        self.calendar.add_command(self.leave)
        self.calendar.add_command(self.list)

async def setup(bot: commands.Bot):
    cog = CustomEventsGroup(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.calendar)

