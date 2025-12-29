from __future__ import annotations
import random
import json
from typing import Optional
import discord
from discord.ext import commands, tasks
from discord import app_commands

from core.utility import now_ts, fmt, day_key
from core.personality import sanitize_isla_text, MemoryService, ConversationTracker, ReplyEngine
from utils.helpers import isla_embed, ensure_user_row, isla_embed as helper_isla_embed
from utils.embed_utils import create_embed
from utils.isla_style import isla_embed as isla_embed_style, fmt as fmt_style
from utils.economy import ensure_wallet, get_wallet, add_coins
from utils.isla_reply import embed_isla

# ============================================================================
# CONSTANTS AND HELPERS (from profile.py)
# ============================================================================

def vacation_badge(vac_until: int, vac_last_used: int) -> str:
    """Returns vacation status badge text."""
    now = now_ts()
    if vac_until > now:
        return "🏖️ Vacation"
    cd_end = (vac_last_used or 0) + 24*3600
    if cd_end > now:
        return "⏳ Vacation Cooldown"
    return ""

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

def isla_embed(desc: str, icon: str = "https://i.imgur.com/5nsuuCV.png") -> discord.Embed:
    return helper_isla_embed(desc, icon=icon)

# ============================================================================
# DUEL VIEW (from duel_cog.py)
# ============================================================================

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
                embed=isla_embed_style("Declined.\n᲼᲼", title="Duel"),
                view=self
            )
            return

        guild_id = interaction.guild_id
        if not guild_id:
            return await interaction.response.edit_message(embed=isla_embed_style("Server only.\n᲼᲼", title="Duel"), view=self)

        # Ensure wallets + balance checks (again, at accept time)
        await ensure_wallet(self.bot.db, guild_id, self.challenger_id)
        await ensure_wallet(self.bot.db, guild_id, self.target_id)

        w1 = await get_wallet(self.bot.db, guild_id, self.challenger_id)
        w2 = await get_wallet(self.bot.db, guild_id, self.target_id)

        if w1.coins < self.amount or w2.coins < self.amount:
            return await interaction.response.edit_message(
                embed=isla_embed_style("Someone can't cover the stake.\n᲼᲼", title="Duel"),
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
            + f"Pot: **{fmt_style(pot)} Coins**\n"
            "᲼᲼"
        )
        await interaction.response.edit_message(content="", embed=isla_embed_style(desc, title="Duel"), view=self)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(embed=isla_embed_style("Not for you.\n᲼᲼", title="Duel"), ephemeral=True)
        await self._resolve(interaction, accepted=True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message(embed=isla_embed_style("Not for you.\n᲼᲼", title="Duel"), ephemeral=True)
        await self._resolve(interaction, accepted=False)

# ============================================================================
# MAIN USER COG CLASS
# ============================================================================

class User(commands.Cog):
    """Consolidated User cog: Profile, privacy, safeword, vacation watch, auto-reply, and duels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        
        # Vacation watch setup
        self.spam_channel_id = int(bot.cfg.get("channels", "spam", default=0) or 0)
        
        # Auto-reply setup
        self.memory = MemoryService(bot.db)
        self.conversation = ConversationTracker(self.memory, bot.db)
        self.reply_engine = ReplyEngine(
            self.memory,
            self.conversation,
            bot.personality,
            bot.db
        )
        self.cooldowns: dict[tuple[int, int], int] = {}
        self.cooldown_seconds = 60  # 1 minute cooldown per user
        
        # Start background tasks
        self.vacation_watch_loop.start()
        self.cleanup_task.start()
    
    def cog_unload(self):
        self.vacation_watch_loop.cancel()
        self.cleanup_task.cancel()
    
    # ========================================================================
    # VACATION WATCH TASK (from vacation_watch.py)
    # ========================================================================
    
    @tasks.loop(minutes=10)
    async def vacation_watch_loop(self):
        """Welcome users back from vacation."""
        await self.bot.wait_until_ready()
        now = now_ts()

        for guild in self.bot.guilds:
            gid = guild.id
            spam = guild.get_channel(self.spam_channel_id) if self.spam_channel_id else None
            if not isinstance(spam, discord.TextChannel):
                spam = None

            # ended vacations that haven't been welcomed yet
            rows = await self.bot.db.fetchall(
                """
                SELECT user_id, vacation_until_ts, vacation_welcomed_ts
                FROM users
                WHERE guild_id=?
                  AND vacation_until_ts > 0
                  AND vacation_until_ts <= ?
                  AND (vacation_welcomed_ts=0 OR vacation_welcomed_ts < vacation_until_ts)
                  AND opted_out=0
                """,
                (gid, now)
            )
            if not rows:
                continue

            for r in rows:
                uid = int(r["user_id"])
                member = guild.get_member(uid)
                if not member:
                    # user left; still mark to avoid looping forever
                    await self.bot.db.execute(
                        "UPDATE users SET vacation_welcomed_ts=? WHERE guild_id=? AND user_id=?",
                        (now, gid, uid)
                    )
                    continue

                desc = (
                    "Welcome back.\n\n"
                    "Vacation's over.\n"
                    "You're back on normal rules again.\n\n"
                    "If you're rusty, run `/start`.\n"
                    "᲼᲼"
                )
                e = isla_embed(desc, title="Back")

                sent = False
                try:
                    await member.send(embed=e)
                    sent = True
                except discord.Forbidden:
                    sent = False

                if not sent and spam:
                    await spam.send(content=f"||{member.mention}||", embed=e)

                await self.bot.db.execute(
                    "UPDATE users SET vacation_welcomed_ts=? WHERE guild_id=? AND user_id=?",
                    (now, gid, uid)
                )

    @vacation_watch_loop.before_loop
    async def before_vacation_watch_loop(self):
        await self.bot.wait_until_ready()
    
    # ========================================================================
    # AUTO-REPLY TASK (from auto_reply.py)
    # ========================================================================
    
    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Daily cleanup of old conversations and context."""
        await self.memory.prune_old_conversations()
        await self.memory.clear_old_context(max_age_seconds=3600)
    
    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()
    
    def _check_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Check if user is on cooldown. Returns True if can reply."""
        key = (guild_id, user_id)
        last_ts = self.cooldowns.get(key, 0)
        now = now_ts()
        
        if now - last_ts < self.cooldown_seconds:
            return False
        
        self.cooldowns[key] = now
        return True
    
    async def _save_conversation(
        self,
        message: discord.Message,
        bot_response: Optional[str] = None,
        interaction_type: str = "message"
    ):
        """Save conversation to memory."""
        if not message.guild:
            return
        
        context = {
            "channel_name": message.channel.name if hasattr(message.channel, "name") else None,
            "author_name": message.author.display_name if isinstance(message.author, discord.Member) else str(message.author)
        }
        
        await self.memory.save_conversation(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            user_id=message.author.id,
            message_content=message.content[:500],  # Limit length
            bot_response=bot_response,
            message_id=message.id,
            context=context,
            interaction_type=interaction_type
        )
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle message events for automated replies."""
        if message.author.bot:
            return
        
        if not message.guild:
            return
        
        # Check if bot is mentioned
        bot_mentioned = self.bot.user and self.bot.user.mentioned_in(message)
        
        # Check for keyword-based replies (only if not mentioned, to avoid double replies)
        should_check_keywords = not bot_mentioned
        
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Ensure user exists
        await self.bot.db.ensure_user(guild_id, user_id)
        
        # Handle mentions
        if bot_mentioned:
            if not self._check_cooldown(guild_id, user_id):
                return  # On cooldown
            
            should_reply = await self.reply_engine.should_reply_to_mention(
                guild_id, user_id, message.channel.id
            )
            
            if should_reply:
                # Get context
                context = await self.conversation.get_user_context(
                    guild_id, user_id, message.channel.id
                )
                
                # Generate reply
                reply = await self.reply_engine.generate_reply(
                    text=message.content,
                    guild_id=guild_id,
                    user_id=user_id,
                    channel_id=message.channel.id,
                    use_memory=True
                )
                
                if reply:
                    try:
                        # Send reply
                        sent_message = await message.channel.send(embed=embed_isla(reply))
                        
                        # Save conversation
                        await self._save_conversation(
                            message,
                            bot_response=reply,
                            interaction_type="mention"
                        )
                    except discord.Forbidden:
                        pass  # No permission to send
                    except Exception:
                        pass  # Ignore other errors
        
        # Handle keyword-based replies (lower priority, less frequent)
        elif should_check_keywords and len(message.content) > 10:
            # Only check keywords occasionally (10% chance) to avoid spam
            if random.random() < 0.1:
                if not self._check_cooldown(guild_id, user_id):
                    return
                
                reply = await self.reply_engine.generate_reply(
                    text=message.content,
                    guild_id=guild_id,
                    user_id=user_id,
                    channel_id=message.channel.id,
                    use_memory=False  # Less memory usage for keyword replies
                )
                
                if reply:
                    try:
                        # Send reply with lower probability (50% chance even if matched)
                        if random.random() < 0.5:
                            sent_message = await message.channel.send(embed=embed_isla(reply))
                            await self._save_conversation(
                                message,
                                bot_response=reply,
                                interaction_type="keyword"
                            )
                    except Exception:
                        pass
    
    async def get_conversation_summary(
        self,
        guild_id: int,
        user_id: int,
        limit: int = 5
    ) -> str:
        """Get a summary of recent conversations with a user."""
        conversations = await self.memory.get_recent_conversations(
            guild_id=guild_id,
            user_id=user_id,
            limit=limit
        )
        
        if not conversations:
            return "No recent conversations."
        
        lines = []
        for conv in reversed(conversations):  # Oldest first
            user_msg = conv["message_content"][:50]
            bot_resp = conv["bot_response"][:50] if conv["bot_response"] else None
            lines.append(f"User: {user_msg}")
            if bot_resp:
                lines.append(f"Bot: {bot_resp}")
            lines.append("")
        
        return "\n".join(lines)[:1000]  # Limit length
    
    # ========================================================================
    # PROFILE COMMANDS (from profile.py)
    # ========================================================================
    
    @app_commands.command(name="profile", description="Show a user's profile.")
    async def profile(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        user = user or interaction.user
        row = await self.bot.db.fetchone(
            "SELECT coins, obedience, xp, lce, vacation_until_ts, vacation_last_used_ts, safeword_on FROM users WHERE guild_id=? AND user_id=?",
            (gid, user.id)
        )
        if not row:
            embed = create_embed("No data yet.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

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
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        stat = stat.lower().strip()
        if stat not in ("coins", "obedience", "xp", "lce"):
            stat = "obedience"

        rows = await self.bot.db.fetchall(
            f"SELECT user_id,{stat} as v FROM users WHERE guild_id=? ORDER BY v DESC LIMIT 10",
            (gid,)
        )
        if not rows:
            embed = create_embed("No data.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = []
        for i, r in enumerate(rows, start=1):
            lines.append(f"**{i}.** <@{int(r['user_id'])}> — **{fmt(int(r['v']))}**")

        desc = f"{interaction.user.mention}\nTop 10 by **{stat}**\n\n" + "\n".join(lines) + "\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, "https://i.imgur.com/5nsuuCV.png"), ephemeral=True)
    
    # ========================================================================
    # PRIVACY COMMANDS (from privacy.py)
    # ========================================================================
    
    @app_commands.command(name="optout", description="Hard leave Isla system: deletes your data and stops tracking.")
    async def optout(self, interaction: discord.Interaction):
        """Hard opt-out - deletes all user data."""
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, interaction.user.id

        # Audit first (minimal)
        await self.bot.db.audit(gid, uid, uid, "optout_requested", "{}", now_ts())

        # Delete all user data, then mark optout
        await self.bot.db.hard_delete_user(gid, uid)
        await self.bot.db.set_optout(gid, uid, True, now_ts())
        await self.bot.db.audit(gid, uid, uid, "optout_completed", "{}", now_ts())

        await interaction.followup.send(
            "You are opted out. All Isla data for you in this server has been deleted, and I will not track you.\n"
            "If you ever want back in, use /optin.",
            ephemeral=True,
        )

    @app_commands.command(name="optin", description="Re-join Isla system after opting out.")
    async def optin(self, interaction: discord.Interaction):
        """Re-join after hard opt-out."""
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, interaction.user.id

        await self.bot.db.set_optout(gid, uid, False, None)
        await self.bot.db.ensure_user(gid, uid)
        await self.bot.db.audit(gid, uid, uid, "optin", "{}", now_ts())

        embed = create_embed("Opt-in complete. You're back in the system.", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # ========================================================================
    # SAFEWORD COMMANDS (from safeword.py)
    # ========================================================================
    
    @app_commands.command(name="safeword", description="Toggle neutral tone for IslaBot.")
    @app_commands.describe(reason="Optional reason (stored privately; you can leave blank).")
    async def safeword(self, interaction: discord.Interaction, reason: str = ""):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)

        row = await self.bot.db.fetchone(
            "SELECT opted_out, safeword_on FROM users WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        if row and int(row["opted_out"] or 0) == 1:
            e = isla_embed(
                "You're opted out.\nUse `/opt-in` first if you want IslaBot again.\n᲼᲼",
                title="Safeword"
            )
            return await interaction.followup.send(embed=e, ephemeral=True)

        cur = int(row["safeword_on"] or 0) if row else 0
        new = 0 if cur else 1

        await self.bot.db.execute(
            "UPDATE users SET safeword_on=?, safeword_set_ts=?, safeword_reason=? WHERE guild_id=? AND user_id=?",
            (new, now_ts(), (reason or ""), gid, interaction.user.id)
        )

        if new == 1:
            desc = (
                "Noted.\n\n"
                "Neutral mode is on.\n"
                "You can keep using IslaBot normally.\n\n"
                "What changes:\n"
                "• No degrading language\n"
                "• No petnames\n"
                "• No flirt escalation\n"
                "• No targeted public callouts\n\n"
                "Toggle off anytime with `/safeword`.\n"
                "᲼᲼"
            )
            e = isla_embed(desc, title="Safeword On")
        else:
            desc = (
                "Okay.\n\n"
                "Neutral mode is off.\n"
                "Back to normal.\n"
                "᲼᲼"
            )
            e = isla_embed(desc, title="Safeword Off")

        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="safeword_status", description="View what Safeword does and your current mode.")
    async def safeword_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)
        row = await self.bot.db.fetchone(
            "SELECT safeword_on, safeword_set_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        on = int(row["safeword_on"] or 0) if row else 0
        since = int(row["safeword_set_ts"] or 0)

        if on:
            desc = (
                "Status: **Safeword On**\n\n"
                "Isla will stay neutral with you.\n"
                "You still have access to:\n"
                "• coins, profile, quests, orders, casino\n\n"
                "Neutral means:\n"
                "• no humiliation\n"
                "• no petnames\n"
                "• no flirt escalation\n"
                "• no targeted public callouts\n"
                "᲼᲼"
            )
        else:
            desc = (
                "Status: **Safeword Off**\n\n"
                "Isla uses normal tone with you.\n"
                "You can turn Safeword on anytime with `/safeword`.\n"
                "᲼᲼"
            )

        e = isla_embed(desc, title="Safeword")
        await interaction.followup.send(embed=e, ephemeral=True)
    
    # ========================================================================
    # DUEL COMMANDS (from duel_cog.py)
    # ========================================================================
    
    @app_commands.command(name="duel", description="Both stake Coins; minigame determines winner.")
    @app_commands.describe(user="Opponent", amount="Stake amount")
    async def duel(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if user.bot or user.id == interaction.user.id:
            return await interaction.followup.send(embed=isla_embed_style("No.\n᲼᲼", title="Duel"), ephemeral=True)

        amount = int(amount)
        if amount <= 0:
            return await interaction.followup.send(embed=isla_embed_style("Use a real number.\n᲼᲼", title="Duel"), ephemeral=True)

        gid = interaction.guild_id
        await ensure_wallet(self.bot.db, gid, interaction.user.id)
        await ensure_wallet(self.bot.db, gid, user.id)

        w1 = await get_wallet(self.bot.db, gid, interaction.user.id)
        if w1.coins < amount:
            return await interaction.followup.send(embed=isla_embed_style("You can't cover that stake.\n᲼᲼", title="Duel"), ephemeral=True)

        # Public challenge message in the channel (no @everyone)
        view = DuelAcceptView(self.bot, interaction.user.id, user.id, amount)
        challenge_embed = isla_embed_style(
            f"{user.mention}\n\n"
            f"{interaction.user.mention} wants a duel.\n"
            f"Stake: **{fmt_style(amount)} Coins** each.\n"
            "᲼᲼",
            title="Duel Request"
        )
        embed = create_embed("Posted.\n᲼᲼", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
        await interaction.channel.send(content=f"{user.mention}", embed=challenge_embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(User(bot))

