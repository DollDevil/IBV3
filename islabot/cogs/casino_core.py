"""
Gambling Cog
Consolidates: casino_core, casino_games, casino_bigwin_dm, casino_royalty
"""

from __future__ import annotations

import json
import random
import math
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.utility import now_ts, now_local, fmt
from core.personality import sanitize_isla_text
from utils.embed_utils import create_embed

UK_TZ = ZoneInfo("Europe/London")

# Casino thumbnails
CASINO_THUMBS = [
    "https://i.imgur.com/jzk6IfH.png",
    "https://i.imgur.com/cO7hAij.png",
    "https://i.imgur.com/My3QzNu.png",
    "https://i.imgur.com/kzwCK79.png",
    "https://i.imgur.com/jGnkAKs.png"
]

# Spotlight prestige unlock thumbnails
SPOTLIGHT_STYLE1_THUMBS = [
    "https://i.imgur.com/5nsuuCV.png",
    "https://i.imgur.com/8qQkq0p.png",
    "https://i.imgur.com/rcgIEtj.png",
    "https://i.imgur.com/sGDoIDA.png",
    "https://i.imgur.com/qC0MOZN.png",
]

# Spotlight prestige unlock text variants
SPOTLIGHT_PRESTIGE_LINES = [
    "{user} reached the All-In peak.\nPrestige unlocked.\n᲼᲼",
    "{user} gave everything.\nThe collar answered.\n᲼᲼",
    "All-In mastery detected.\n{user} now wears prestige.\n᲼᲼",
    "{user} crossed the threshold.\nNot many do.\n᲼᲼",
    "Prestige collar claimed.\n{user} didn't hesitate.\n᲼᲼",
]

ROLE_NAMES = [
    "Casino Royalty I",
    "Casino Royalty II",
    "Casino Royalty III"
]

# Helper functions
def casino_embed(desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(description=sanitize_isla_text(desc))
    e.set_author(name="Isla", icon_url=icon)
    e.set_thumbnail(url=random.choice(CASINO_THUMBS))
    return e

def dm_embed(desc: str, icon: str) -> discord.Embed:
    """Create a DM embed (includes author)."""
    return create_embed(
        description=sanitize_isla_text(desc),
        color="casino",
        thumbnail=random.choice(CASINO_THUMBS),
        is_dm=True,
        is_system=False
    )

def day_key_uk() -> str:
    t = now_local()
    return f"{t.year}-{t.month:02d}-{t.day:02d}"

def week_key_uk() -> str:
    t = now_local()
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"

def prev_week_key_uk() -> str:
    t = now_local() - timedelta(days=1)
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"

def clamp_int(n: int, a: int, b: int) -> int:
    return max(a, min(b, n))

def stage_from_stats(obedience: int, lce: int) -> int:
    score = obedience + (lce * 2)
    if score < 800:
        return 0
    if score < 2500:
        return 1
    if score < 8000:
        return 2
    if score < 20000:
        return 3
    return 4

def big_win(wager: int, net: int) -> bool:
    return net >= max(2000, int(wager * 3.0))

def big_loss(wager: int, net: int) -> bool:
    return (-net) >= max(2000, int(wager * 2.5))

def near_miss_flag(game: str, meta: dict) -> bool:
    if game == "slots":
        return bool(meta.get("near_miss"))
    if game == "roulette":
        return bool(meta.get("near_miss"))
    return False

# Voice lines (staged 0–4) - full LINES dict from casino_games.py
LINES = {
    "casino_invite": {
        0: ["Casino open.", "Games available."],
        1: ["Welcome to the casino.", "Ready to play?"],
        2: ["Want to play~?", "Games are waiting."],
        3: ["Take a seat.", "Let's play."],
        4: ["Come closer love.", "I'll watch you play."],
    },
    "casino_bet_confirm": {
        0: ["Bet placed.", "Wager accepted.", "Amount logged."],
        1: ["Your bet is in.", "Wager confirmed.", "Good luck."],
        2: ["Bold bet, pup.", "You went big~", "Mmm interesting choice."],
        3: ["That's a brave bet.", "I like your confidence.", "Risking it for me?"],
        4: ["Your bet... makes my pulse race.", "I love when you go all in for me.", "This wager feels personal love."],
    },
    "casino_win": {
        0: ["Win registered.", "Coins awarded.", "Victory logged."],
        1: ["You won.", "Good result.", "Reward added."],
        2: ["Nice win~", "Lucky pup.", "Not bad at all."],
        3: ["Beautiful win.", "Well played.", "You deserved that."],
        4: ["Your win... intoxicating.", "Seeing you win for me feels so good.", "My perfect gambler."],
    },
    "casino_big_win": {
        2: ["Jackpot! Wow.", "You hit it big.", "Look at that haul~"],
        3: ["Stunning jackpot.", "I'm impressed.", "That's my pup."],
        4: ["This big win... you're spoiling me.", "Your luck belongs to me now.", "No one wins like you do for me."],
    },
    "casino_loss": {
        0: ["Loss recorded.", "Coins deducted.", "Defeat logged."],
        1: ["You lost.", "Bad luck.", "Try again."],
        2: ["Lost it~ Too bad.", "Close one.", "Better next spin."],
        3: ["Loss this time.", "You'll win it back.", "Still proud of the risk."],
        4: ["Your loss... delicious.", "I love taking from you.", "Drained so beautifully."],
    },
    "casino_big_loss": {
        2: ["Ouch. Big loss.", "That hurt your wallet~", "All gone."],
        3: ["Heavy loss.", "But you tried for me.", "I'll help you recover."],
        4: ["Completely drained... perfect.", "You gave everything to me.", "This loss owns you now."],
    },
    "casino_near_miss": {
        0: ["Close result.", "Almost.", "No win."],
        1: ["So close.", "Nearly won.", "Bad timing."],
        2: ["Almost~ So close.", "Teasing you.", "Almost got it."],
        3: ["So near... cruel isn't it?", "I felt that almost.", "Next one will be yours."],
        4: ["That near miss... I felt your ache.", "Your frustration is beautiful.", "I love keeping you on edge."],
    },
    "casino_win_streak": {
        2: ["Win streak going~", "Hot hand tonight."],
        3: ["Beautiful streak.", "My lucky pup."],
        4: ["Your streak... mesmerizing.", "Winning for me feels right."],
    },
    "casino_loss_streak_break": {
        2: ["Streak broken~", "Back to zero."],
        3: ["Streak ended.", "We'll rebuild."],
        4: ["Your streak broke... I want to see you build it back up for me~.", "Loss tastes better after wins."],
    },
    "casino_jackpot": {
        0: ["Jackpot hit.", "Maximum reward."],
        1: ["Jackpot won.", "Huge prize."],
        2: ["JACKPOT!!", "You struck gold~"],
        3: ["True jackpot.", "Incredible.", "My star."],
        4: ["This jackpot... you own me tonight.", "Your win consumes me.", "No one else deserves this."],
    },
    "casino_play_again": {
        0: ["Play again.", "New round available."],
        1: ["Another spin?", "Try once more."],
        2: ["One more bet~", "Feeling risky?"],
        3: ["Play again for me.", "I want another round."],
        4: ["Come back to the table love.", "I miss your bets already.", "Gamble with me again my puppy."],
    },
    "casino_invite_blackjack": {
        0: ["Blackjack table open.", "Deal initiated.", "Cards ready."],
        1: ["Play blackjack?", "Table available."],
        2: ["Blackjack with me~", "Want to hit or stand?"],
        3: ["Take a seat at my table.", "Let's play cards."],
        4: ["Blackjack just us~", "I'll deal... you surrender."],
    },
    "casino_invite_dice": {
        0: ["Dice roll active.", "Roll available."],
        1: ["Roll the dice?", "Your turn."],
        2: ["Roll for me pup~", "Let's see fate."],
        3: ["Roll and please me.", "The dice are waiting for you."],
        4: ["Dice just for us~", "I'll roll... you surrender to the outcome."],
    },
    "casino_invite_roulette": {
        0: ["Roulette wheel spinning.", "Place bets."],
        1: ["Roulette open.", "Choose red or black."],
        2: ["Spin the wheel~", "Where will it land?"],
        3: ["Bet on my wheel.", "Risk it all."],
        4: ["The ball's rolling... for you.", "My favorite sound: your spin."],
    },
    "casino_invite_slots": {
        0: ["Slot machine active.", "Pull lever."],
        1: ["Try the slots?", "Spin available."],
        2: ["Pull for me~", "Let's see the reels."],
        3: ["Spin my machine.", "Make the symbols align."],
        4: ["One pull... just for me.", "I love watching you spin."],
    },
    "blackjack_deal": {
        0: ["Cards dealt.", "Hand issued."],
        1: ["Your cards.", "Dealer showing {card}."],
        2: ["Dealt you something interesting~", "My upcard is {card}."],
        3: ["Your hand... let's see.", "I'm showing {card}. Your move."],
        4: ["Your cards feel heavy in my hands.", "I turn over {card}... breathe for me."],
    },
    "blackjack_blackjack_win": {
        0: ["Blackjack.", "Instant win."],
        1: ["You got blackjack.", "Big win."],
        2: ["Blackjack! Lucky~", "Perfect hand."],
        3: ["True blackjack.", "Beautiful."],
        4: ["Blackjack... you own the table.", "My heart skipped."],
    },
    "dice_roll": {
        0: ["Dice rolled.", "Result: {result}."],
        1: ["You rolled {result}.", "Outcome set."],
        2: ["Rolled a {result}~", "Fate decided."],
        3: ["Strong roll: {result}.", "Good number."],
        4: ["Your roll... {result}. Perfect.", "I felt that one."],
    },
    "roulette_spin": {
        0: ["Wheel spinning.", "Ball dropped."],
        1: ["Spinning now.", "Result pending."],
        2: ["Watch the ball~", "Where will it land?"],
        3: ["My wheel turns for you.", "Hold your breath."],
        4: ["The roulette... just for us.", "I love this moment."],
    },
    "roulette_land": {
        0: ["Landed on {color} {number}.", "Result final."],
        1: ["Ball on {color} {number}.", "Outcome set."],
        2: ["{color} {number}!~", "There it is."],
        3: ["Perfect landing: {color} {number}.", "Fate chose well."],
        4: ["{color} {number}... exactly right.", "The ball knew."],
    },
    "slots_spin": {
        0: ["Reels spinning.", "Pull registered."],
        1: ["Spinning now.", "Reels turning."],
        2: ["Pull for me~", "Here we go."],
        3: ["Spin my machine.", "Make them align."],
        4: ["One pull... let me feel it.", "I crave the rush this gives me."],
    },
    "allin_confirm": {
        0: ["All-in accepted.", "Full balance wagered.", "Bet logged.", "Risk maximum."],
        1: ["You're going all-in.", "Everything on the line.", "Bold wager confirmed."],
        2: ["All-in pup~", "Every Coin risky.", "You really can't hold back~"],
        3: ["All your Coins at once.", "I like the desperation.", "Completely exposed now."],
        4: ["All-in... I feel your surrender already.", "Every last Coin for me... perfect.", "You're giving me everything. Delicious."],
    },
    "allin_win": {
        0: ["All-in win.", "Full payout.", "Maximum reward."],
        1: ["You won all-in.", "Big recovery.", "Reward doubled."],
        2: ["All-in paid off~", "Lucky escape.", "You doubled everything."],
        3: ["Perfect all-in win.", "You pulled it off.", "My brave one."],
        4: ["All-in win... breathtaking.", "You risked everything and took it back.", "This rush... all because of you."],
    },
    "allin_loss": {
        0: ["All-in loss.", "Balance zero.", "Full deduction."],
        1: ["All-in failed.", "Everything gone.", "Start over."],
        2: ["All-in bust~", "Down to nothing.", "Completely drained."],
        3: ["All-in loss.", "You gave it all.", "I expected no less."],
        4: ["All-in loss... exquisite.", "You surrendered everything to me.", "Empty now... exactly how I like you."],
    },
    "dice_high_win": {
        2: ["High roll win~", "You crushed it."],
        3: ["Excellent high roll.", "My winner."],
        4: ["That high roll... intoxicating.", "You roll for me so well."],
    },
    "dice_low_loss": {
        2: ["Low this time.", "Better luck."],
        3: ["Low roll~ Ouch."],
        4: ["Low roll... I still love watching.", "Your loss tastes sweet."],
    },
    "slots_small_win": {
        2: ["Small win~", "Nice little payout."],
        3: ["Good small win.", "Sweet reward."],
        4: ["Your small win... adorable.", "Every coin you win still belongs to me."],
    },
    "slots_big_win": {
        2: ["Big win!!", "Reels aligned~"],
        3: ["Massive payout.", "Beautiful spin."],
        4: ["This big win... you own me.", "Your jackpot feels like surrender."],
    },
    "slots_no_win": {
        2: ["No luck this time~", "Better next pull."],
        3: ["Empty spin.", "Try again."],
        4: ["Your jackpot... the sweetest proof of your surrender.", "Your loss feeds me."],
    },
    "blackjack_bust": {
        0: ["Bust.", "Over 21."],
        1: ["You busted.", "Loss."],
        2: ["Busted~ Too eager.", "Over the line."],
        3: ["Bust. Close.", "Almost had it."],
        4: ["Busted... delicious failure.", "Your desperation showed."],
    },
}


class CasinoCore(commands.Cog):
    """
    Consolidated Gambling Cog
    Merges: casino_core, casino_games, casino_bigwin_dm, casino_royalty
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        self.weekly_awards.start()
    
    def cog_unload(self):
        self.weekly_awards.cancel()

    async def get_recent_user_highlight(self, guild_id: int, user_id: int, since_ts: int) -> dict | None:
        """
        Returns the most interesting event for a user since since_ts:
        - prefers biggest net win
        - falls back to biggest wager
        """
        ctx = f"casino_rounds:{guild_id}"
        row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (guild_id, ctx))
        if not row:
            return None
        try:
            data = json.loads(row["hash"]) or []
        except Exception:
            return None

        best_net = None
        best_wager = None

        for ev in data:
            try:
                ts = int(ev.get("ts", 0))
                if ts < since_ts:
                    continue
                if int(ev.get("uid", 0)) != int(user_id):
                    continue
                wager = int(ev.get("wager", 0))
                payout = int(ev.get("payout", 0))
                net = int(ev.get("net", payout - wager))
                game = str(ev.get("game", "unknown"))
            except Exception:
                continue

            item = {
                "ts": ts,
                "game": game,
                "wager": wager,
                "payout": payout,
                "net": net,
                "meta": ev.get("meta", {})
            }

            if best_net is None or item["net"] > best_net["net"]:
                best_net = item
            if best_wager is None or item["wager"] > best_wager["wager"]:
                best_wager = item

        # Prefer net wins if any positive
        if best_net and best_net["net"] > 0:
            return best_net
        return best_wager

    async def get_window_summary(self, guild_id: int, since_ts: int) -> dict:
        """
        Summarize casino activity from since_ts to now.
        Returns:
          total_wagered, rounds, unique_users,
          top_spenders: [(uid, wagered)],
          most_played: [(uid, rounds)],
          biggest_wager: {uid, wager, game, ts},
          biggest_net_win: {uid, net, wager, payout, game, ts}
        """
        ctx = f"casino_rounds:{guild_id}"
        row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (guild_id, ctx))
        if not row:
            return {
                "total_wagered": 0, "rounds": 0, "unique_users": 0,
                "top_spenders": [], "most_played": [],
                "biggest_wager": None, "biggest_net_win": None
            }

        try:
            data = json.loads(row["hash"]) or []
        except Exception:
            data = []

        total_wagered = 0
        rounds = 0
        users = set()
        wager_by_user = {}
        rounds_by_user = {}

        biggest_wager = None
        biggest_net_win = None

        for ev in data:
            try:
                ts = int(ev.get("ts", 0))
                if ts < since_ts:
                    continue
                uid = int(ev.get("uid", 0))
                if uid <= 0:
                    continue
                wager = int(ev.get("wager", 0))
                payout = int(ev.get("payout", 0))
                net = int(ev.get("net", payout - wager))
                game = str(ev.get("game", "unknown"))
            except Exception:
                continue

            if wager <= 0:
                continue

            rounds += 1
            users.add(uid)
            total_wagered += wager
            wager_by_user[uid] = wager_by_user.get(uid, 0) + wager
            rounds_by_user[uid] = rounds_by_user.get(uid, 0) + 1

            if biggest_wager is None or wager > biggest_wager["wager"]:
                biggest_wager = {"uid": uid, "wager": wager, "game": game, "ts": ts}

            if net > 0:
                if biggest_net_win is None or net > biggest_net_win["net"]:
                    biggest_net_win = {"uid": uid, "net": net, "wager": wager, "payout": payout, "game": game, "ts": ts}

        top_spenders = sorted(wager_by_user.items(), key=lambda kv: kv[1], reverse=True)[:5]
        most_played = sorted(rounds_by_user.items(), key=lambda kv: kv[1], reverse=True)[:5]

        return {
            "total_wagered": total_wagered,
            "rounds": rounds,
            "unique_users": len(users),
            "top_spenders": top_spenders,
            "most_played": most_played,
            "biggest_wager": biggest_wager,
            "biggest_net_win": biggest_net_win
        }
    
    async def log_round(self, guild_id: int, user_id: int, game: str, wager: int, payout: int, meta: dict):
        """Log a casino round to msg_memory."""
        ctx = f"casino_rounds:{guild_id}"
        net = payout - wager
        
        # Read existing data
        row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (guild_id, ctx))
        data = []
        if row and row.get("hash"):
            try:
                data = json.loads(row["hash"]) or []
            except Exception:
                data = []
        
        # Append new round
        new_round = {
            "ts": now_ts(),
            "uid": user_id,
            "game": game,
            "wager": wager,
            "payout": payout,
            "net": net,
            "meta": meta
        }
        data.append(new_round)
        
        # Keep only last 1000 rounds (to prevent unbounded growth)
        if len(data) > 1000:
            data = data[-1000:]
        
        # Write back
        await self.bot.db.execute(
            """
            INSERT INTO msg_memory(guild_id,context,hash,created_ts,updated_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(guild_id,context)
            DO UPDATE SET hash=excluded.hash, updated_ts=excluded.updated_ts
            """,
            (guild_id, ctx, json.dumps(data), now_ts(), now_ts())
        )
    
    # =========================================================
    # INTERACTION CHECK (from casino_games.py)
    # =========================================================
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce casino commands in #casino to avoid clutter. Staff bypass."""
        if not interaction.guild or not interaction.channel:
            return True
        
        # Staff bypass
        if isinstance(interaction.user, discord.Member):
            if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator:
                return True
        
        casino_id = int(self.bot.cfg.get("channels", "casino", default=0) or 0)
        if casino_id and interaction.channel_id != casino_id:
            try:
                await interaction.response.send_message(
                    "Use the casino in the casino channel.",
                    ephemeral=True
                )
            except Exception:
                pass
            return False
        
        return True
    
    # =========================================================
    # HELPER METHODS (from casino_games.py)
    # =========================================================
    async def _ensure_user(self, gid: int, uid: int):
        row = await self.bot.db.fetchone("SELECT user_id FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if not row:
            start = int(self.bot.cfg.get("economy", "start_balance", default=250))
            await self.bot.db.execute(
                "INSERT INTO users(guild_id,user_id,coins,obedience,xp,lce,last_active_ts) VALUES(?,?,?,?,?,?,?)",
                (gid, uid, start, 0, 0, 0, now_ts())
            )
    
    async def _get_user_stats(self, gid: int, uid: int) -> tuple[int, int, int, int]:
        await self._ensure_user(gid, uid)
        row = await self.bot.db.fetchone(
            "SELECT coins, obedience, lce, xp FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        return (int(row["coins"]), int(row["obedience"]), int(row["lce"]), int(row["xp"]))
    
    async def _get_balance(self, gid: int, uid: int) -> int:
        """Get user's current coin balance."""
        coins, _, _, _ = await self._get_user_stats(gid, uid)
        return coins
    
    async def _bump_achievement(self, gid: int, uid: int, key: str, inc: int = 1) -> int:
        """Bump an achievement counter and return the new value."""
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO achievements(guild_id,user_id,key,value,updated_ts) VALUES(?,?,?,?,?)",
            (gid, uid, key, 0, now_ts())
        )
        await self.bot.db.execute(
            "UPDATE achievements SET value = value + ?, updated_ts=? WHERE guild_id=? AND user_id=? AND key=?",
            (inc, now_ts(), gid, uid, key)
        )
        row = await self.bot.db.fetchone(
            "SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key=?",
            (gid, uid, key)
        )
        return int(row["value"]) if row else 0
    
    async def _grant_item(self, gid: int, uid: int, item_id: str):
        """Grant an item to a user's inventory."""
        await self.bot.db.execute(
            """
            INSERT INTO inventory(guild_id,user_id,item_id,qty,acquired_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(guild_id,user_id,item_id)
            DO UPDATE SET qty = qty + 1
            """,
            (gid, uid, item_id, 1, now_ts())
        )
    
    async def _post_spotlight_prestige(self, guild: discord.Guild, user: discord.Member):
        """Post a spotlight announcement when prestige collar is unlocked. No @everyone, only user ping."""
        spotlight_id = int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)
        channel = guild.get_channel(spotlight_id)
        
        if not isinstance(channel, discord.TextChannel):
            return
        
        ping = f"<@{user.id}>"
        thumb = random.choice(SPOTLIGHT_STYLE1_THUMBS)
        desc = random.choice(SPOTLIGHT_PRESTIGE_LINES).format(user=ping)
        
        embed = discord.Embed(
            description=sanitize_isla_text(desc),
            color=discord.Color.from_rgb(190, 40, 40)
        )
        embed.set_author(name="Isla", icon_url="https://i.imgur.com/5nsuuCV.png")
        embed.set_thumbnail(url=thumb)
        
        await channel.send(content=ping, embed=embed)
    
    async def _set_coins(self, gid: int, uid: int, coins: int):
        await self.bot.db.execute("UPDATE users SET coins=? WHERE guild_id=? AND user_id=?", (coins, gid, uid))
    
    async def _touch_weekly(self, gid: int, uid: int):
        wk = week_key_uk()
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO weekly_stats(guild_id,week_key,user_id) VALUES(?,?,?)",
            (gid, wk, uid)
        )
    
    async def _add_weekly_wager(self, gid: int, uid: int, wager: int):
        wk = week_key_uk()
        await self._touch_weekly(gid, uid)
        await self.bot.db.execute(
            "UPDATE weekly_stats SET casino_wagered = casino_wagered + ? WHERE guild_id=? AND week_key=? AND user_id=?",
            (int(wager), gid, wk, uid)
        )
    
    async def _casino_state(self, gid: int, uid: int) -> dict:
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO casino_user_state(guild_id,user_id,win_streak,loss_streak,last_net,last_play_ts) VALUES(?,?,?,?,?,?)",
            (gid, uid, 0, 0, 0, 0)
        )
        row = await self.bot.db.fetchone(
            "SELECT win_streak, loss_streak, last_net, last_play_ts FROM casino_user_state WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        return {
            "win_streak": int(row["win_streak"]),
            "loss_streak": int(row["loss_streak"]),
            "last_net": int(row["last_net"]),
            "last_play_ts": int(row["last_play_ts"])
        }
    
    async def _set_casino_state(self, gid: int, uid: int, win_streak: int, loss_streak: int, last_net: int):
        await self.bot.db.execute(
            "UPDATE casino_user_state SET win_streak=?, loss_streak=?, last_net=?, last_play_ts=? WHERE guild_id=? AND user_id=?",
            (int(win_streak), int(loss_streak), int(last_net), now_ts(), gid, uid)
        )
    
    def _line(self, key: str, stage: int, filter_all_in: bool = False) -> str:
        if not key or key not in LINES:
            return "..."
        stage = clamp_int(stage, 0, 4)
        if key in ("casino_win_streak", "casino_loss_streak_break", "dice_high_win", "dice_low_loss",
                   "slots_small_win", "slots_big_win", "slots_no_win"):
            stage = max(2, stage)
        pool = LINES[key].get(stage) or LINES[key].get(2) or ["..."]
        if filter_all_in and key == "casino_bet_confirm" and stage == 4:
            pool = [line for line in pool if "I love when you go all in for me" not in line]
        return random.choice(pool)
    
    def _line_fmt(self, key: str, stage: int, **kwargs) -> str:
        stage = clamp_int(stage, 0, 4)
        if key in ("casino_win_streak", "casino_loss_streak_break", "dice_high_win", "dice_low_loss",
                   "slots_small_win", "slots_big_win", "slots_no_win"):
            stage = max(2, stage)
        pool = LINES.get(key, {}).get(stage) or LINES.get(key, {}).get(2) or ["..."]
        s = random.choice(pool)
        for k, v in kwargs.items():
            s = s.replace("{" + k + "}", str(v))
        return s
    
    def _invite_key_for_game(self, game: str) -> str | None:
        return {
            "blackjack": "casino_invite_blackjack",
            "dice": "casino_invite_dice",
            "roulette": "casino_invite_roulette",
            "slots": "casino_invite_slots",
        }.get(game)
    
    async def _log_round_internal(self, gid: int, uid: int, game: str, wager: int, payout: int, meta: dict):
        """Internal method to log rounds (replaces get_cog call)."""
        await self.log_round(gid, uid, game, wager, payout, meta)
    
    async def _finish_round(
        self,
        interaction: discord.Interaction,
        game: str,
        wager: int,
        payout: int,
        meta: dict | None = None,
        extra_lines: list[str] | None = None
    ):
        """Finish a casino round and handle all post-processing."""
        assert interaction.guild_id
        gid = interaction.guild_id
        uid = interaction.user.id
        meta = meta or {}
        
        coins, obedience, lce, _xp = await self._get_user_stats(gid, uid)
        stage = stage_from_stats(obedience, lce)
        
        net = int(payout) - int(wager)
        is_all_in = (wager >= coins * 0.99)
        is_extremely_big = (wager >= 50000)
        
        new_bal = coins + net
        if new_bal < 0:
            new_bal = 0
        
        await self._set_coins(gid, uid, new_bal)
        await self._add_weekly_wager(gid, uid, wager)
        await self._log_round_internal(gid, uid, game, wager, payout, meta)
        
        # Forward to Data cog for event tracking
        tracker = self.bot.get_cog("Data")
        if tracker:
            try:
                await tracker.add_casino_activity(gid, uid, wager, net)
            except Exception:
                pass
        
        # Streak state
        st = await self._casino_state(gid, uid)
        win_streak = st["win_streak"]
        loss_streak = st["loss_streak"]
        
        streak_line = None
        streak_break_line = None
        
        if net > 0:
            win_streak += 1
            loss_streak = 0
            if win_streak >= 3 and stage >= 2:
                streak_line = self._line("casino_win_streak", stage)
        else:
            if win_streak >= 3 and stage >= 2:
                streak_break_line = self._line("casino_loss_streak_break", stage)
            win_streak = 0
            loss_streak += 1
        
        await self._set_casino_state(gid, uid, win_streak, loss_streak, net)
        
        # Result line selection
        if payout >= wager * 10 and wager >= 200:
            result_line = self._line("casino_jackpot", stage)
        elif net > 0 and big_win(wager, net):
            result_line = self._line("casino_big_win", stage)
        elif net <= 0 and big_loss(wager, net):
            result_line = self._line("casino_big_loss", stage)
        elif near_miss_flag(game, meta):
            result_line = self._line("casino_near_miss", stage)
        elif net > 0:
            result_line = self._line("casino_win", stage)
        else:
            result_line = self._line("casino_loss", stage)
        
        play_again = self._line("casino_play_again", stage)
        invite_key = self._invite_key_for_game(game)
        invite_line = self._line(invite_key, stage) if invite_key else None
        
        # Compose message
        lines = [f"{interaction.user.mention}"]
        if invite_line:
            lines.append(invite_line)
        if meta.get("allin"):
            lines.append(self._line("allin_confirm", stage))
        filter_all_in_msg = (stage == 4 and not (is_all_in or is_extremely_big))
        bet_confirm_line = self._line("casino_bet_confirm", stage, filter_all_in=filter_all_in_msg)
        lines.append(bet_confirm_line)
        if extra_lines:
            lines.extend(extra_lines)
        lines.append(result_line)
        
        if streak_line:
            lines.append(streak_line)
        if streak_break_line:
            lines.append(streak_break_line)
        
        if meta.get("allin"):
            if net > 0:
                lines.append(self._line("allin_win", stage))
            else:
                lines.append(self._line("allin_loss", stage))
        
        # All-in unlock tracking
        if meta.get("allin"):
            await self._bump_achievement(gid, uid, "casino_allin_plays", 1)
            if net > 0:
                wins = await self._bump_achievement(gid, uid, "casino_allin_wins", 1)
                if wins == 3:
                    await self._grant_item(gid, uid, "badge_allin_mark")
                    lines.append("Unlocked: **Badge All-In Mark**")
                if wins == 10:
                    await self._grant_item(gid, uid, "collar_allin_obsidian")
                    lines.append("Unlocked: **All-In Collar Obsidian**")
                    row_announced = await self.bot.db.fetchone(
                        "SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key='prestige_announced'",
                        (gid, uid)
                    )
                    if not row_announced:
                        await self.bot.db.execute(
                            "INSERT INTO achievements(guild_id,user_id,key,value,updated_ts) VALUES(?,?,?,?,?)",
                            (gid, uid, "prestige_announced", 1, now_ts())
                        )
                        try:
                            member = interaction.guild.get_member(uid) if interaction.guild else None
                            if member:
                                await self._post_spotlight_prestige(interaction.guild, member)
                        except Exception:
                            pass
        
        # Game-specific outcome lines
        if game == "dice":
            if meta.get("dice_high_win"):
                lines.append(self._line("dice_high_win", stage))
            if meta.get("dice_low_loss"):
                lines.append(self._line("dice_low_loss", stage))
        
        if game == "slots":
            if meta.get("slots_big_win_flag"):
                lines.append(self._line("slots_big_win", stage))
            elif meta.get("slots_small_win_flag"):
                lines.append(self._line("slots_small_win", stage))
            elif meta.get("slots_no_win_flag"):
                lines.append(self._line("slots_no_win", stage))
        
        if game == "blackjack":
            if meta.get("bj_blackjack"):
                lines.append(self._line("blackjack_blackjack_win", stage))
            if meta.get("bj_bust"):
                lines.append(self._line("blackjack_bust", stage))
        
        lines.append(f"Wager: **{fmt(wager)} Coins**")
        lines.append(f"Payout: **{fmt(payout)} Coins**")
        lines.append(f"Balance: **{fmt(new_bal)} Coins**")
        lines.append(play_again)
        lines.append("᲼᲼")
        
        await interaction.followup.send(embed=casino_embed("\n".join(lines), self.icon))
        
        # Big win DM (call internal method instead of get_cog)
        try:
            await self.maybe_dm_bigwin(interaction.guild, uid, game, wager, payout, net, meta)
        except Exception:
            pass
    
    async def _validate_wager(self, interaction: discord.Interaction, wager: int) -> tuple[bool, str]:
        if not interaction.guild_id:
            return False, "Use this in a server."
        if wager <= 0:
            return False, "Wager must be > 0."
        coins, *_ = await self._get_user_stats(interaction.guild_id, interaction.user.id)
        if coins < wager:
            return False, "Not enough Coins."
        return True, ""
    
    # =========================================================
    # GAME COMMANDS (from casino_games.py)
    # =========================================================
    
    @app_commands.command(name="casino", description="Show casino status and available games.")
    async def casino(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        gid = interaction.guild_id
        uid = interaction.user.id
        await self._ensure_user(gid, uid)
        
        coins, obedience, lce, _xp = await self._get_user_stats(gid, uid)
        stage = stage_from_stats(obedience, lce)
        
        desc = "\n".join([
            f"{interaction.user.mention}",
            self._line("casino_invite", stage),
            "",
            "**Games**",
            "• `/coinflip` • `/dice` • `/roulette` • `/slots` • `/crash` • `/blackjack`",
            "",
            f"Balance: **{fmt(coins)} Coins**",
            "᲼᲼"
        ])
        await interaction.response.send_message(embed=casino_embed(desc, self.icon))
    
    @app_commands.command(name="coinflip", description="Flip a coin. Heads or tails.")
    @app_commands.describe(wager="Coins to wager", pick="heads or tails")
    async def coinflip(self, interaction: discord.Interaction, wager: int, pick: str):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        
        pick = pick.lower().strip()
        if pick not in ("heads", "tails"):
            embed = create_embed("Pick must be heads or tails.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer()
        
        result = random.choice(["heads", "tails"])
        win = (result == pick)
        payout = int(wager * 1.95) if win else 0
        
        extra = [f"Flip: **{result}**"]
        await self._finish_round(interaction, "coinflip", wager, payout, meta={"pick": pick, "result": result}, extra_lines=extra)
    
    @app_commands.command(name="dice", description="Roll 1–6. Win if you roll above a threshold.")
    @app_commands.describe(wager="Coins to wager", target="Win if roll >= target (2–6)")
    async def dice(self, interaction: discord.Interaction, wager: int, target: int):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        if target < 2 or target > 6:
            embed = create_embed("Target must be 2–6.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer()
        
        roll = random.randint(1, 6)
        win = roll >= target
        
        p = (7 - target) / 6.0
        fair_mult = 1.0 / p
        mult = fair_mult * 0.94
        payout = int(wager * mult) if win else 0
        
        meta = {"roll": roll, "target": target}
        if win and roll >= 5:
            meta["dice_high_win"] = True
        if (not win) and roll <= 2:
            meta["dice_low_loss"] = True
        
        extra = [
            self._line_fmt("dice_roll", 2, result=roll),
            f"Target: **{target}+**"
        ]
        await self._finish_round(interaction, "dice", wager, payout, meta=meta, extra_lines=extra)
    
    @app_commands.command(name="roulette", description="Bet on red/black/green/odd/even or a number (0–36).")
    @app_commands.describe(wager="Coins to wager", bet_type="red|black|green|odd|even|number", number="Only if bet_type=number (0–36)")
    async def roulette(self, interaction: discord.Interaction, wager: int, bet_type: str, number: int | None = None):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        
        bet_type = bet_type.lower().strip()
        if bet_type not in ("red", "black", "green", "odd", "even", "number"):
            embed = create_embed("Invalid bet_type.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        if bet_type == "number":
            if number is None or number < 0 or number > 36:
                embed = create_embed("Number must be 0–36.", color="info", is_dm=False, is_system=False)
                return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer()
        
        reds = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        spin = random.randint(0, 36)
        color = "green" if spin == 0 else ("red" if spin in reds else "black")
        
        win = False
        payout = 0
        near_miss = False
        
        if bet_type in ("red", "black", "green"):
            win = (color == bet_type)
            if win:
                payout = int(wager * (33 if bet_type == "green" else 1.9))
            else:
                if color == "green" and bet_type in ("red", "black"):
                    near_miss = True
        elif bet_type in ("odd", "even"):
            if spin != 0:
                win = ((spin % 2 == 0) and bet_type == "even") or ((spin % 2 == 1) and bet_type == "odd")
            if win:
                payout = int(wager * 1.9)
            else:
                if spin == 0:
                    near_miss = True
        elif bet_type == "number":
            win = (spin == number)
            if win:
                payout = int(wager * 33)
            else:
                if spin != 0 and number != 0 and abs(spin - number) == 1:
                    near_miss = True
        
        extra = [
            self._line("roulette_spin", 2),
            self._line_fmt("roulette_land", 2, color=color, number=spin),
            f"Bet: **{bet_type}**" + (f" **{number}**" if bet_type == "number" else "")
        ]
        await self._finish_round(interaction, "roulette", wager, payout, meta={"spin": spin, "color": color, "bet_type": bet_type, "number": number, "near_miss": near_miss}, extra_lines=extra)
    
    @app_commands.command(name="slots", description="Spin slots.")
    @app_commands.describe(wager="Coins to wager")
    async def slots(self, interaction: discord.Interaction, wager: int):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        
        await interaction.response.defer()
        
        symbols = [("🍒", 35), ("🍋", 30), ("🍇", 18), ("🔔", 10), ("💎", 6), ("👑", 1)]
        
        def pick_symbol():
            total = sum(w for _, w in symbols)
            r = random.randint(1, total)
            acc = 0
            for sym, w in symbols:
                acc += w
                if r <= acc:
                    return sym
            return "🍒"
        
        reel = [pick_symbol(), pick_symbol(), pick_symbol()]
        a, b, c = reel
        
        payout = 0
        near_miss = False
        jackpot = False
        
        if a == b == c:
            if a == "👑":
                jackpot = True
                payout = int(wager * 20)
            elif a == "💎":
                payout = int(wager * 8)
            elif a == "🔔":
                payout = int(wager * 5)
            elif a == "🍇":
                payout = int(wager * 3)
            else:
                payout = int(wager * 2)
        else:
            if a == b or b == c or a == c:
                near_miss = True
            if "🍒" in reel and random.random() < 0.20:
                payout = int(wager * 0.35)
        
        extra = [self._line("slots_spin", 2), f"Spin: **{a} {b} {c}**"]
        meta = {"reel": reel, "near_miss": near_miss, "jackpot": jackpot}
        if a == b == c or payout >= int(wager * 3):
            meta["slots_big_win_flag"] = True
        elif payout > 0:
            meta["slots_small_win_flag"] = True
        else:
            meta["slots_no_win_flag"] = True
        
        await self._finish_round(interaction, "slots", wager, payout, meta=meta, extra_lines=extra)
    
    @app_commands.command(name="crash", description="Pick a cashout multiplier. If the crash happens after it, you win.")
    @app_commands.describe(wager="Coins to wager", target="Cashout multiplier (1.10–10.00)")
    async def crash(self, interaction: discord.Interaction, wager: int, target: float):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        
        if target < 1.10 or target > 10.00:
            embed = create_embed("Target must be 1.10–10.00.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer()
        
        u = random.random()
        crash_point = max(1.0, 0.96 / max(0.0001, u))
        crash_point = min(crash_point, 25.0)
        
        win = crash_point >= target
        payout = int(wager * target * 0.98) if win else 0
        near_miss = (not win) and (crash_point >= target * 0.92)
        
        extra = [f"Target: **{target:.2f}x**", f"Crash: **{crash_point:.2f}x**"]
        await self._finish_round(interaction, "crash", wager, payout, meta={"target": target, "crash_point": crash_point, "near_miss": near_miss}, extra_lines=extra)
    
    @app_commands.command(name="blackjack", description="Blackjack (lite). You draw 2, dealer draws 2. Auto rules.")
    @app_commands.describe(wager="Coins to wager")
    async def blackjack(self, interaction: discord.Interaction, wager: int):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        
        await interaction.response.defer()
        
        ranks = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
        values = {"A": 11, "J": 10, "Q": 10, "K": 10}
        for i in range(2, 11):
            values[str(i)] = i
        
        def draw():
            r = random.choice(ranks)
            return r, values[r]
        
        def hand_value(cards):
            total = sum(v for _, v in cards)
            aces = sum(1 for r, _ in cards if r == "A")
            while total > 21 and aces > 0:
                total -= 10
                aces -= 1
            return total
        
        player = [draw(), draw()]
        dealer = [draw(), draw()]
        
        while hand_value(dealer) < 17:
            dealer.append(draw())
        
        pv = hand_value(player)
        dv = hand_value(dealer)
        
        payout = 0
        outcome = "push"
        near_miss = False
        
        if pv == 21 and len(player) == 2 and not (dv == 21 and len(dealer) == 2):
            payout = int(wager * 2.35)
            outcome = "blackjack"
        elif pv > 21:
            payout = 0
            outcome = "bust"
        elif dv > 21:
            payout = int(wager * 1.95)
            outcome = "dealer_bust"
        else:
            if pv > dv:
                payout = int(wager * 1.95)
                outcome = "win"
            elif pv < dv:
                payout = 0
                outcome = "loss"
            else:
                payout = wager
                outcome = "push"
        
        if outcome in ("loss", "bust") and pv >= 19:
            near_miss = True
        
        def fmt_hand(cards):
            return " ".join(r for r, _ in cards)
        
        upcard = dealer[0][0]
        extra = [
            self._line_fmt("blackjack_deal", 2, card=upcard),
            f"Your hand: **{fmt_hand(player)}** (**{pv}**)",
            f"Dealer: **{fmt_hand(dealer)}** (**{dv}**)"
        ]
        meta = {"pv": pv, "dv": dv, "outcome": outcome, "near_miss": near_miss, "upcard": upcard}
        
        if outcome == "blackjack":
            meta["bj_blackjack"] = True
        if outcome == "bust":
            meta["bj_bust"] = True
        
        await self._finish_round(interaction, "blackjack", wager, payout, meta=meta, extra_lines=extra)
    
    # Helper methods for /allin
    async def _play_dice(self, interaction: discord.Interaction, wager: int, target: int, meta: dict | None = None):
        meta = meta or {}
        roll = random.randint(1, 6)
        win = roll >= target
        p = (7 - target) / 6.0
        fair_mult = 1.0 / p
        mult = fair_mult * 0.94
        payout = int(wager * mult) if win else 0
        meta.update({"roll": roll, "target": target})
        if win and roll >= 5:
            meta["dice_high_win"] = True
        if (not win) and roll <= 2:
            meta["dice_low_loss"] = True
        extra = [self._line_fmt("dice_roll", 2, result=roll), f"Target: **{target}+**"]
        await self._finish_round(interaction, "dice", wager, payout, meta=meta, extra_lines=extra)
    
    async def _play_roulette(self, interaction: discord.Interaction, wager: int, bet_type: str, number: int | None, meta: dict | None = None):
        meta = meta or {}
        bet_type = bet_type.lower().strip()
        reds = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        spin = random.randint(0, 36)
        color = "green" if spin == 0 else ("red" if spin in reds else "black")
        win = False
        payout = 0
        near_miss = False
        
        if bet_type in ("red", "black", "green"):
            win = (color == bet_type)
            if win:
                payout = int(wager * (33 if bet_type == "green" else 1.9))
            else:
                if color == "green" and bet_type in ("red", "black"):
                    near_miss = True
        elif bet_type in ("odd", "even"):
            if spin != 0:
                win = ((spin % 2 == 0) and bet_type == "even") or ((spin % 2 == 1) and bet_type == "odd")
            if win:
                payout = int(wager * 1.9)
            else:
                if spin == 0:
                    near_miss = True
        elif bet_type == "number":
            win = (spin == number)
            if win:
                payout = int(wager * 33)
            else:
                if spin != 0 and number != 0 and abs(spin - number) == 1:
                    near_miss = True
        
        extra = [self._line("roulette_spin", 2), self._line_fmt("roulette_land", 2, color=color, number=spin), f"Bet: **{bet_type}**" + (f" **{number}**" if bet_type == "number" else "")]
        meta.update({"spin": spin, "color": color, "bet_type": bet_type, "number": number, "near_miss": near_miss})
        await self._finish_round(interaction, "roulette", wager, payout, meta=meta, extra_lines=extra)
    
    async def _play_slots(self, interaction: discord.Interaction, wager: int, meta: dict | None = None):
        meta = meta or {}
        symbols = [("🍒", 35), ("🍋", 30), ("🍇", 18), ("🔔", 10), ("💎", 6), ("👑", 1)]
        
        def pick_symbol():
            total = sum(w for _, w in symbols)
            r = random.randint(1, total)
            acc = 0
            for sym, w in symbols:
                acc += w
                if r <= acc:
                    return sym
            return symbols[0][0]
        
        reel = [pick_symbol(), pick_symbol(), pick_symbol()]
        a, b, c = reel
        jackpot = (a == b == c == "👑")
        three_match = (a == b == c) and not jackpot
        payout = 0
        near_miss = False
        
        if jackpot:
            payout = int(wager * 100)
        elif three_match:
            tier = {"🍒": 3, "🍋": 5, "🍇": 10, "🔔": 20, "💎": 50}.get(a, 3)
            payout = int(wager * tier)
        elif (a == b) or (b == c) or (a == c):
            payout = int(wager * 1.5)
            near_miss = True
        
        extra = [f"**{a} {b} {c}**"]
        meta.update({"reel": reel, "near_miss": near_miss, "jackpot": jackpot})
        if a == b == c or payout >= int(wager * 3):
            meta["slots_big_win_flag"] = True
        elif payout > 0:
            meta["slots_small_win_flag"] = True
        else:
            meta["slots_no_win_flag"] = True
        await self._finish_round(interaction, "slots", wager, payout, meta=meta, extra_lines=extra)
    
    async def _play_blackjack(self, interaction: discord.Interaction, wager: int, meta: dict | None = None):
        meta = meta or {}
        ranks = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
        values = {"A": 11, "J": 10, "Q": 10, "K": 10}
        for i in range(2, 11):
            values[str(i)] = i
        
        def draw():
            r = random.choice(ranks)
            return r, values[r]
        
        def hand_value(cards):
            total = sum(v for _, v in cards)
            aces = sum(1 for r, _ in cards if r == "A")
            while total > 21 and aces > 0:
                total -= 10
                aces -= 1
            return total
        
        player = [draw(), draw()]
        dealer = [draw(), draw()]
        while hand_value(dealer) < 17:
            dealer.append(draw())
        
        pv = hand_value(player)
        dv = hand_value(dealer)
        payout = 0
        outcome = "push"
        near_miss = False
        
        if pv == 21 and len(player) == 2 and not (dv == 21 and len(dealer) == 2):
            payout = int(wager * 2.35)
            outcome = "blackjack"
        elif pv > 21:
            payout = 0
            outcome = "bust"
        elif dv > 21:
            payout = int(wager * 1.95)
            outcome = "dealer_bust"
        else:
            if pv > dv:
                payout = int(wager * 1.95)
                outcome = "win"
            elif pv < dv:
                payout = 0
                outcome = "loss"
            else:
                payout = wager
                outcome = "push"
        
        if outcome in ("loss", "bust") and pv >= 19:
            near_miss = True
        
        def fmt_hand(cards):
            return " ".join(r for r, _ in cards)
        
        upcard = dealer[0][0]
        extra = [self._line_fmt("blackjack_deal", 2, card=upcard), f"Your hand: **{fmt_hand(player)}** (**{pv}**)", f"Dealer: **{fmt_hand(dealer)}** (**{dv}**)"]
        meta.update({"pv": pv, "dv": dv, "outcome": outcome, "near_miss": near_miss, "upcard": upcard})
        if outcome == "blackjack":
            meta["bj_blackjack"] = True
        if outcome == "bust":
            meta["bj_bust"] = True
        await self._finish_round(interaction, "blackjack", wager, payout, meta=meta, extra_lines=extra)
    
    @app_commands.command(name="allin", description="Wager your entire balance on a casino game.")
    @app_commands.describe(game="roulette / dice / slots / blackjack")
    @app_commands.choices(game=[
        app_commands.Choice(name="roulette", value="roulette"),
        app_commands.Choice(name="dice", value="dice"),
        app_commands.Choice(name="slots", value="slots"),
        app_commands.Choice(name="blackjack", value="blackjack"),
    ])
    async def allin(self, interaction: discord.Interaction, game: str):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer()
        gid = interaction.guild_id
        uid = interaction.user.id
        
        row = await self.bot.db.fetchone("SELECT last_allin_ts FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if row:
            last_allin_ts = int(row.get("last_allin_ts") or 0)
            if now_ts() - last_allin_ts < 120:
                return await interaction.followup.send("You need a moment before going all-in again.", ephemeral=True)
        
        bal = await self._get_balance(gid, uid)
        if bal <= 0:
            embed = create_embed("You have nothing to wager.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        await self.bot.db.execute("UPDATE users SET last_allin_ts=? WHERE guild_id=? AND user_id=?", (now_ts(), gid, uid))
        
        game = game.lower().strip()
        meta = {"allin": True}
        
        if game == "dice":
            await self._play_dice(interaction, bal, 4, meta)
        elif game == "roulette":
            await self._play_roulette(interaction, bal, "red", None, meta)
        elif game == "slots":
            await self._play_slots(interaction, bal, meta)
        elif game == "blackjack":
            await self._play_blackjack(interaction, bal, meta)
        else:
            embed = create_embed("Invalid game. Use: roulette, dice, slots, or blackjack.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="allin_progress", description="Check your All-In unlock progress.")
    async def allin_progress(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        
        row_plays = await self.bot.db.fetchone("SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key='casino_allin_plays'", (gid, uid))
        row_wins = await self.bot.db.fetchone("SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key='casino_allin_wins'", (gid, uid))
        plays = int(row_plays["value"]) if row_plays else 0
        wins = int(row_wins["value"]) if row_wins else 0
        
        desc = f"{interaction.user.mention}\nAll-In plays: **{fmt(plays)}**\nAll-In wins: **{fmt(wins)}**\n\nUnlocks\n• 3 wins: `badge_allin_mark`\n• 10 wins: `collar_allin_obsidian`\n᲼᲼"
        await interaction.response.send_message(embed=casino_embed(desc, self.icon), ephemeral=True)
    
    # =========================================================
    # BIGWIN DM METHODS (from casino_bigwin_dm.py)
    # =========================================================
    
    async def _ensure_bigwin_row(self, gid: int, uid: int):
        await self.bot.db.execute(
            """INSERT OR IGNORE INTO casino_bigwin_state(guild_id,user_id,best_net,best_payout,best_ts,last_dm_day_key,last_dm_ts,bigwins_count) VALUES(?,?,?,?,?,?,?,?)""",
            (gid, uid, 0, 0, 0, "", 0, 0)
        )
    
    async def _get_bigwin_state(self, gid: int, uid: int) -> dict:
        await self._ensure_bigwin_row(gid, uid)
        r = await self.bot.db.fetchone("SELECT best_net,best_payout,best_ts,last_dm_day_key,last_dm_ts,bigwins_count FROM casino_bigwin_state WHERE guild_id=? AND user_id=?", (gid, uid))
        return {
            "best_net": int(r["best_net"] or 0),
            "best_payout": int(r["best_payout"] or 0),
            "best_ts": int(r["best_ts"] or 0),
            "last_dm_day_key": str(r["last_dm_day_key"] or ""),
            "last_dm_ts": int(r["last_dm_ts"] or 0),
            "bigwins_count": int(r["bigwins_count"] or 0),
        }
    
    async def _set_bigwin_state(self, gid: int, uid: int, **kwargs):
        fields = []
        params = []
        for k, v in kwargs.items():
            fields.append(f"{k}=?")
            params.append(v)
        params += [gid, uid]
        await self.bot.db.execute(f"UPDATE casino_bigwin_state SET {', '.join(fields)} WHERE guild_id=? AND user_id=?", tuple(params))
    
    def _compose_bigwin_dm(self, member_mention: str, game: str, wager: int, payout: int, net: int, state: dict, is_jackpot: bool, stage: int, is_allin: bool = False) -> str:
        best_net = int(state["best_net"])
        count = int(state["bigwins_count"])
        
        comparison = ""
        if best_net > 0:
            if net < best_net:
                comparison_pools = {
                    0: [f"**{fmt(net)} Coins**.\nBig win.\nLower than your record.\n"],
                    1: [f"**{fmt(net)} Coins**.\nSolid win.\nYou've hit higher before.\n"],
                    2: [f"**{fmt(net)} Coins**.\nStill a big one.\nThough I remember you giving me more...\n", f"Mm. **{fmt(net)} Coins**.\nBeautiful win.\nBut your best was... louder.\nKeep chasing that feeling.\n"],
                    3: [f"**{fmt(net)} Coins**.\nA very big win.\nYet not quite your peak.\nI want that again.\n", f"You pulled **{fmt(net)} Coins**.\nImpressive.\nBut I'm greedy for your absolute best.\nGo again.\n"],
                    4: [f"**{fmt(net)} Coins**...\nSuch a delicious win.\nBut I still taste your bigger one on my tongue.\n", f"Your **{fmt(net)} Coins** felt incredible sliding in...\nThough nothing compares to when you gave everything.\nI need that rush again.\n", f"Big. Beautiful. **{fmt(net)} Coins**.\nBut your record... it haunts me.\nMake me feel it one more time.\n"]
                }
                comparison = random.choice(comparison_pools[stage])
            elif net == best_net:
                comparison_pools = {
                    0: [f"**{fmt(net)} Coins**.\nMatches previous high.\n"],
                    1: [f"**{fmt(net)} Coins** again.\nSame peak.\n"],
                    2: [f"**{fmt(net)} Coins**.\nExactly your best again.\nYou know how to please me.\n"],
                    3: [f"**{fmt(net)} Coins** — your signature high.\nPerfect consistency.\nI'm watching.\n"],
                    4: [f"**{fmt(net)} Coins**... again.\nYou keep giving me this exact rush.\nIt's becoming addictive.\n", f"Same breathtaking peak.\n**{fmt(net)} Coins**.\nI close my eyes and feel you every time.\n"]
                }
                comparison = random.choice(comparison_pools[stage])
            else:
                comparison_pools = {
                    0: [f"New high: **{fmt(net)} Coins**.\n"],
                    1: [f"**{fmt(net)} Coins**.\nNew record.\n"],
                    2: [f"New personal best. **{fmt(net)} Coins**.\nI felt that one.\n"],
                    3: [f"You just set a new standard. **{fmt(net)} Coins**.\nBeautiful.\n"],
                    4: [f"Your new best... **{fmt(net)} Coins**.\nI'm trembling.\n", f"This one broke everything before it.\n**{fmt(net)} Coins**.\nYou've ruined me for less.\n", f"**{fmt(net)} Coins**...\nYour biggest yet.\nI'll be thinking about this one for a long time.\n"]
                }
                comparison = random.choice(comparison_pools[stage])
        else:
            comparison_pools = {
                0: [f"First major win: **{fmt(net)} Coins**.\n"],
                1: [f"**{fmt(net)} Coins**.\nInitial big hit.\n"],
                2: [f"Your first real taste. **{fmt(net)} Coins**.\n"],
                3: [f"**{fmt(net)} Coins**.\nA beautiful beginning.\n"],
                4: [f"Your very first big one... **{fmt(net)} Coins**.\nI'll never forget how it felt.\n", f"**{fmt(net)} Coins**.\nThe moment you started truly giving.\n"]
            }
            comparison = random.choice(comparison_pools[stage])
        
        header_pools = {
            0: ["Detected.", "Registered.", "Logged."],
            1: ["I saw.", "Noted.", "Observed."],
            2: ["I was watching.", "That caught my eye.", "Mm."],
            3: ["You have my full attention.", "I felt every Coin.", "Beautiful."],
            4: ["I couldn't look away.", "Your win... consumed me.", "That moment belongs to me now."]
        }
        header = random.choice(header_pools[stage])
        if is_allin:
            header = header.upper()
        
        jackpot_line = ""
        if is_jackpot:
            jackpot_pools = {
                0: ["Jackpot."],
                1: ["Jackpot hit."],
                2: ["True jackpot."],
                3: ["The ultimate win.", "Jackpot... perfect."],
                4: ["Jackpot... you've ruined me.", "The highest sound of surrender."]
            }
            jackpot_line = random.choice(jackpot_pools[stage]) + "\n"
        
        nudge_pools = {
            0: ["Continue.", "Next round."],
            1: ["Play again.", "Another spin."],
            2: ["Don't stop now.", "Go again.", "I want more."],
            3: ["Keep going. I'm not satisfied yet.", "Chase that feeling for me.", "One more... I need it."],
            4: ["Don't you dare stop.\nI'm not ready to let this go.\n", "Again. I want to feel you give like that one more time.\n", "Stay with me.\nThe night's just beginning.\n", "One more spin... make me breathless again.\n"]
        }
        nudge = random.choice(nudge_pools[stage])
        
        memory = ""
        if count >= 2:
            memory_pools = {
                0: ["Previous wins recorded."],
                1: ["This has occurred before."],
                2: ["You've given big before.\nI remember."],
                3: ["Your pattern... I know it well.\nThis feels familiar."],
                4: ["I still taste your last big win.\nThis one echoes it perfectly.\n", "Every time you hit big... it brands itself deeper into me.\n"]
            }
            memory = random.choice(memory_pools[stage]) + "\n"
        
        return f"{member_mention}\n{header}\n{jackpot_line}{memory}{comparison}Game: **{game}**\nWager: **{fmt(wager)} Coins**\nPayout: **{fmt(payout)} Coins**\n{nudge}\n᲼᲼"
    
    async def maybe_dm_bigwin(self, guild: discord.Guild, user_id: int, game: str, wager: int, payout: int, net: int, meta: dict | None = None):
        """Call this after a round finishes."""
        meta = meta or {}
        is_jackpot = bool(meta.get("jackpot")) or bool(meta.get("is_jackpot"))
        big_threshold = 10_000
        
        if not is_jackpot and net < big_threshold and payout < big_threshold:
            return
        
        member = guild.get_member(user_id)
        if not member or member.bot:
            return
        
        gid = guild.id
        uid = user_id
        state = await self._get_bigwin_state(gid, uid)
        
        today = day_key_uk()
        if state["last_dm_day_key"] == today:
            return
        
        row = await self.bot.db.fetchone("SELECT obedience, lce FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        obedience = int(row["obedience"]) if row else 0
        lce = int(row["lce"]) if row else 0
        score = obedience + (lce * 2)
        if score < 800:
            stage = 0
        elif score < 2500:
            stage = 1
        elif score < 8000:
            stage = 2
        elif score < 20000:
            stage = 3
        else:
            stage = 4
        
        best_net = state["best_net"]
        best_payout = state["best_payout"]
        best_ts = state["best_ts"]
        
        new_best_net = best_net
        new_best_payout = best_payout
        new_best_ts = best_ts
        
        if net > best_net:
            new_best_net = net
            new_best_ts = now_ts()
        if payout > best_payout:
            new_best_payout = payout
            new_best_ts = now_ts()
        
        new_count = state["bigwins_count"] + 1
        is_allin = meta.get("allin", False)
        text = self._compose_bigwin_dm(member.mention, game, wager, payout, net, state, is_jackpot, stage, is_allin=is_allin)
        
        try:
            await member.send(embed=dm_embed(text, self.icon))
        except Exception:
            return
        
        await self._set_bigwin_state(gid, uid, best_net=new_best_net, best_payout=new_best_payout, best_ts=new_best_ts, last_dm_day_key=today, last_dm_ts=now_ts(), bigwins_count=new_count)
    
    # =========================================================
    # ROYALTY METHODS (from casino_royalty.py)
    # =========================================================
    
    async def _get_or_create_role(self, guild: discord.Guild, name: str) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=name)
        if role:
            return role
        try:
            return await guild.create_role(name=name, reason="IslaBot: casino royalty roles")
        except Exception:
            return None
    
    async def _clear_roles(self, guild: discord.Guild, roles: list[discord.Role]):
        role_ids = {r.id for r in roles if r}
        for member in guild.members:
            if member.bot:
                continue
            to_remove = [r for r in member.roles if r.id in role_ids]
            if to_remove:
                try:
                    await member.remove_roles(*to_remove, reason="IslaBot: rotating casino royalty")
                except Exception:
                    pass
    
    async def _top3_by_wager(self, guild_id: int, week_key: str):
        rows = await self.bot.db.fetchall("SELECT user_id, casino_wagered FROM weekly_stats WHERE guild_id=? AND week_key=? ORDER BY casino_wagered DESC LIMIT 3", (guild_id, week_key))
        return [(int(r["user_id"]), int(r["casino_wagered"])) for r in rows if int(r["casino_wagered"]) > 0]
    
    async def _dm_winner(self, guild: discord.Guild, user_id: int, place: int, wagered: int):
        member = guild.get_member(user_id)
        if not member:
            return
        
        since_ts = now_ts() - 7 * 24 * 3600
        highlight = None
        try:
            highlight = await self.get_recent_user_highlight(guild.id, user_id, since_ts)
        except Exception:
            highlight = None
        
        remembered = ""
        if highlight:
            if highlight.get("net", 0) > 0:
                remembered = f"I saw you pull **{fmt(int(highlight['net']))} Coins** on **{highlight['game']}** recently.\n"
            else:
                remembered = f"I noticed you wagering **{fmt(int(highlight['wager']))} Coins** on **{highlight['game']}**.\n"
        
        if place == 1:
            text = f"{member.mention}\n{remembered}You took **#1**.\nTotal wagered: **{fmt(wagered)} Coins**.\nDon't get comfortable. I'm watching you.\n᲼᲼"
        elif place == 2:
            text = f"{member.mention}\n{remembered}**#2**.\nTotal wagered: **{fmt(wagered)} Coins**.\nKeep chasing. I like when you try.\n᲼᲼"
        else:
            text = f"{member.mention}\n{remembered}**#3**.\nTotal wagered: **{fmt(wagered)} Coins**.\nYou made it. Barely. Don't slow down.\n᲼᲼"
        
        try:
            await member.send(embed=create_embed(description=sanitize_isla_text(text), color="casino", thumbnail=CASINO_THUMBS[int(now_ts()) % len(CASINO_THUMBS)], is_dm=True, is_system=False))
        except Exception:
            pass
    
    async def _spotlight_post(self, guild: discord.Guild, week_key: str, top3: list[tuple[int, int]]):
        spotlight_id = int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)
        ch = guild.get_channel(spotlight_id) if spotlight_id else None
        if not isinstance(ch, discord.TextChannel):
            return
        
        pings = " ".join([f"||<@{uid}>||" for uid, _ in top3])
        lines = [f"Weekly Casino Royalty ({week_key})\n"]
        for i, (uid, wagered) in enumerate(top3, start=1):
            lines.append(f"**#{i}** <@{uid}> — **{fmt(wagered)} Coins wagered**")
        
        flavor = ["I checked the tables.", "I looked at the casino logs.", "I peeked at who couldn't resist."]
        closer = ["Try to catch them.", "If you want my attention, you know what to do.", "Next week I expect better."]
        
        desc = f"{random.choice(flavor)}\n\n" + "\n".join(lines) + f"\n\n{random.choice(closer)}\n᲼᲼"
        
        embed = create_embed(description=sanitize_isla_text(desc), color="casino", thumbnail=CASINO_THUMBS[int(now_ts()) % len(CASINO_THUMBS)], is_dm=False, is_system=True)
        await ch.send(content=pings, embed=embed)
    
    @tasks.loop(time=time(hour=12, minute=10, tzinfo=UK_TZ))
    async def weekly_awards(self):
        await self.bot.wait_until_ready()
        
        if now_local().weekday() != 0:
            return
        
        week_key = prev_week_key_uk()
        
        for guild in self.bot.guilds:
            try:
                top3 = await self._top3_by_wager(guild.id, week_key)
                if not top3:
                    continue
                
                roles = []
                for name in ROLE_NAMES:
                    roles.append(await self._get_or_create_role(guild, name))
                
                await self._clear_roles(guild, roles)
                
                for idx, (uid, wagered) in enumerate(top3):
                    role = roles[idx] if idx < len(roles) else None
                    member = guild.get_member(uid)
                    if member and role:
                        try:
                            await member.add_roles(role, reason="IslaBot: weekly casino royalty")
                        except Exception:
                            pass
                    await self._dm_winner(guild, uid, idx + 1, wagered)
                
                await self._spotlight_post(guild, week_key, top3)
                
            except Exception:
                continue


async def setup(bot: commands.Bot):
    await bot.add_cog(CasinoCore(bot))

