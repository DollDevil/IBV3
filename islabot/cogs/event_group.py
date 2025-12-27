"""
Event Group Commands

/event group with subcommands:
  /event info
  /event boss
  /event progress
  /event leaderboard
  /event ritual
  /event shop

Picks the current active event automatically.
"""

from __future__ import annotations

import time
import math
import discord
from discord.ext import commands
from discord import app_commands
from utils.uk_time import uk_day_ymd

VC_REDUCED_MULT = 0.35

# DP log scaling params (no caps)
k_TS = 25.0
k_CN = 10_000.0
k_CW = 20_000.0
k_M = 20.0
k_V = 30.0


def now_ts() -> int:
    return int(time.time())


def g(x: float, k: float) -> float:
    return math.log(1.0 + (x / k))


def compute_dp(msg_count: int, vc_minutes: int, vc_reduced_minutes: int,
               ritual_done: int, tokens_spent: int, casino_wager: int, casino_net: int) -> float:
    V_eff = float(vc_minutes) + (float(vc_reduced_minutes) * VC_REDUCED_MULT)
    CN_pos = max(int(casino_net), 0)
    return (
        260.0 * g(tokens_spent, k_TS) +
        160.0 * (1 if ritual_done else 0) +
        110.0 * g(CN_pos, k_CN) +
        95.0 * g(casino_wager, k_CW) +
        80.0 * g(msg_count, k_M) +
        80.0 * g(V_eff, k_V)
    )


def fmt_int(n: int | float) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"


def isla_embed(desc: str, title: str | None = None, icon_url: str = "https://i.imgur.com/5nsuuCV.png") -> discord.Embed:
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=icon_url)
    return e


class EventGroup(commands.Cog):
    """
    /event group with subcommands:
      /event info
      /event boss
      /event progress
      /event leaderboard
      /event ritual
      /event shop

    Picks the current active event automatically.
    If no events are active, responds: "No event going on right now."
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.event = app_commands.Group(name="event", description="Event commands")
        self._register_commands()

    # ---------- Active event resolution ----------
    async def _get_active_events(self, gid: int) -> list[dict]:
        # Expecting "events" table exists
        return await self.bot.db.fetchall(
            """
            SELECT event_id, event_type, name, token_name, start_ts, end_ts, climax_ts
            FROM events
            WHERE guild_id=? AND is_active=1
            """,
            (gid,)
        )

    async def _pick_current_event(self, gid: int) -> dict | None:
        rows = await self._get_active_events(gid)
        if not rows:
            return None

        # Priority: holiday_week > season_era > anything else
        for r in rows:
            if str(r["event_type"]) == "holiday_week":
                return dict(r)
        for r in rows:
            if str(r["event_type"]) == "season_era":
                return dict(r)
        return dict(rows[0])

    async def _no_event(self, interaction: discord.Interaction):
        e = isla_embed("No event going on right now.\n᲼᲼", title="Event")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ---------- /event info ----------
    async def _cmd_info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=isla_embed("No event going on right now.\n᲼᲼", title="Event"), ephemeral=True)

        name = str(ev["name"])
        etype = str(ev["event_type"])
        token = str(ev["token_name"])

        desc = (
            "Hey.\n\n"
            f"Current event:\n**{name}**\n\n"
            f"Type: **{etype}**\n"
            f"Token: **{token}**\n"
            "᲼᲼"
        )
        e = isla_embed(desc, title="Event Info")
        e.add_field(
            name="Commands",
            value=(
                "• `/event boss`\n"
                "• `/event progress`\n"
                "• `/event leaderboard`\n"
                "• `/event ritual`\n"
                "• `/event shop`\n"
            ),
            inline=False
        )
        e.set_footer(text="If this looks empty, it means people haven't moved yet.")
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /event boss ----------
    async def _cmd_boss(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=isla_embed("No event going on right now.\n᲼᲼", title="Event"), ephemeral=True)

        event_id = str(ev["event_id"])
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        if not boss:
            return await interaction.followup.send(embed=isla_embed("No boss is attached to the current event.\n᲼᲼", title="Boss"), ephemeral=True)

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

        # Recent damage (last 6h) if event_boss_tick exists
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

        def line_for(uid: int, pts: float) -> str:
            m = interaction.guild.get_member(int(uid))
            name = m.display_name if m else f"User {uid}"
            return f"{name} — {fmt_int(pts)}"

        today_lines = [f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}" for i, r in enumerate(top_today, start=1)]
        overall_lines = [f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}" for i, r in enumerate(top_overall, start=1)]
        if not today_lines:
            today_lines = ["No data yet."]
        if not overall_lines:
            overall_lines = ["No data yet."]

        desc = (
            f"**{boss_name}**\n"
            f"HP: **{fmt_int(hp_cur)} / {fmt_int(hp_max)}** (**{hp_pct}%**)\n"
        )
        if recent_damage is not None:
            desc += f"Recent damage (6h): **{fmt_int(recent_damage)}**\n"
        desc += "᲼᲼"

        e = isla_embed(desc, title=f"{ev['name']} Boss")
        e.add_field(name="Top Damage Today", value="\n".join(today_lines), inline=False)
        e.add_field(name="Top Damage Overall", value="\n".join(overall_lines[:10]), inline=False)
        e.set_footer(text="Use /event leaderboard for the full ranking.")
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /event progress (boss + your own day stats snapshot) ----------
    async def _cmd_progress(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=isla_embed("No event going on right now.\n᲼᲼", title="Event"), ephemeral=True)

        event_id = str(ev["event_id"])
        today = uk_day_ymd(now_ts())

        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )

        me = await self.bot.db.fetchone(
            """
            SELECT msg_count, vc_minutes, vc_reduced_minutes,
                   ritual_done, tokens_spent, casino_wager, casino_net, dp_cached
            FROM event_user_day
            WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?
            """,
            (gid, event_id, uid, today)
        )

        desc = "Progress check.\n᲼᲼"
        e = isla_embed(desc, title="Event Progress")

        if boss:
            hp_cur = int(boss["hp_current"])
            hp_max = max(1, int(boss["hp_max"]))
            hp_pct = max(0, min(100, int((hp_cur / hp_max) * 100)))
            e.add_field(
                name="Boss",
                value=f"{boss['boss_name']}\nHP: {fmt_int(hp_cur)}/{fmt_int(hp_max)} ({hp_pct}%)",
                inline=False
            )

        if me:
            # If dp_cached is stale (it updates on scheduler), compute a rough live dp from today row
            approx = compute_dp(
                int(me["msg_count"] or 0),
                int(me["vc_minutes"] or 0),
                int(me["vc_reduced_minutes"] or 0),
                int(me["ritual_done"] or 0),
                int(me["tokens_spent"] or 0),
                int(me["casino_wager"] or 0),
                int(me["casino_net"] or 0),
            )
            e.add_field(
                name="You Today",
                value=(
                    f"Damage: **{fmt_int(approx)}**\n"
                    f"Messages: {fmt_int(me['msg_count'] or 0)}\n"
                    f"Voice: {fmt_int(me['vc_minutes'] or 0)}m (+{fmt_int(me['vc_reduced_minutes'] or 0)}m reduced)\n"
                    f"Ritual: {'Done' if int(me['ritual_done'] or 0) else 'Not yet'}\n"
                    f"Tokens spent: {fmt_int(me['tokens_spent'] or 0)}\n"
                ),
                inline=False
            )
        else:
            e.add_field(
                name="You Today",
                value="No activity recorded yet.\nSay something or hop in voice.\n᲼᲼",
                inline=False
            )

        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /event leaderboard ----------
    async def _cmd_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=isla_embed("No event going on right now.\n᲼᲼", title="Event"), ephemeral=True)

        event_id = str(ev["event_id"])
        today = uk_day_ymd(now_ts())

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

        top_today = await self.bot.db.fetchall(
            """
            SELECT user_id, dp_cached AS pts
            FROM event_user_day
            WHERE guild_id=? AND event_id=? AND day_ymd=?
            ORDER BY pts DESC
            LIMIT 10
            """,
            (gid, event_id, today)
        )

        def line_for(rank: int, uid: int, pts: float) -> str:
            m = interaction.guild.get_member(uid)
            name = m.display_name if m else f"User {uid}"
            return f"{rank}) {name} — {fmt_int(pts)}"

        overall_lines = [line_for(i, int(r["user_id"]), float(r["pts"] or 0)) for i, r in enumerate(top_overall, start=1)]
        today_lines = [line_for(i, int(r["user_id"]), float(r["pts"] or 0)) for i, r in enumerate(top_today, start=1)]

        if not overall_lines:
            overall_lines = ["No data yet."]
        if not today_lines:
            today_lines = ["No data yet."]

        e = isla_embed("Here's the ranking.\n᲼᲼", title=f"{ev['name']} Leaderboard")
        e.add_field(name="Top Overall", value="\n".join(overall_lines), inline=False)
        e.add_field(name="Top Today", value="\n".join(today_lines), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /event ritual (info placeholder; hook to your ritual system) ----------
    async def _cmd_ritual(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=isla_embed("No event going on right now.\n᲼᲼", title="Event"), ephemeral=True)

        # If you have an event_rituals table, read it here. Otherwise keep it informational.
        e = isla_embed(
            "Ritual is available.\n\n"
            "If you have a ritual task posted, complete it once today.\n"
            "Then come back and check `/event progress`.\n"
            "᲼᲼",
            title="Ritual"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /event shop (info placeholder; hook to your event shop) ----------
    async def _cmd_shop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=isla_embed("No event going on right now.\n᲼᲼", title="Event"), ephemeral=True)

        e = isla_embed(
            "Event shop is open while the event is active.\n\n"
            "Spend event tokens on limited items.\n"
            "᲼᲼",
            title="Event Shop"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- Register group + subcommands ----------
    def _register_commands(self):
        self.event.command(name="info", description="View current event info.")(self._cmd_info)
        self.event.command(name="boss", description="View the current event boss.")(self._cmd_boss)
        self.event.command(name="progress", description="View boss progress and your contribution today.")(self._cmd_progress)
        self.event.command(name="leaderboard", description="View event leaderboards.")(self._cmd_leaderboard)
        self.event.command(name="ritual", description="View today's ritual info.")(self._cmd_ritual)
        self.event.command(name="shop", description="View the event shop info.")(self._cmd_shop)


async def setup(bot: commands.Bot):
    cog = EventGroup(bot)
    await bot.add_cog(cog)
    # Remove command if it exists, then add it
    bot.tree.remove_command("event")
    bot.tree.add_command(cog.event)

