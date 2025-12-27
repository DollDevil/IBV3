from __future__ import annotations

import random
import math
import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts, now_local, fmt
from core.isla_text import sanitize_isla_text


# ---- Casino thumbnails (you provided) ----
CASINO_THUMBS = [
    "https://i.imgur.com/jzk6IfH.png",  # Red
    "https://i.imgur.com/cO7hAij.png",  # Purple
    "https://i.imgur.com/My3QzNu.png",  # Blue
    "https://i.imgur.com/kzwCK79.png",  # Orange
    "https://i.imgur.com/jGnkAKs.png",  # Green
]

# ---- Spotlight prestige unlock thumbnails ----
SPOTLIGHT_STYLE1_THUMBS = [
    "https://i.imgur.com/5nsuuCV.png",   # Confident smirk
    "https://i.imgur.com/8qQkq0p.png",   # Head tilt smirk
    "https://i.imgur.com/rcgIEtj.png",   # Leaning, intrigued
    "https://i.imgur.com/sGDoIDA.png",   # Looking down
    "https://i.imgur.com/qC0MOZN.png",   # Soft smirk
]

# ---- Spotlight prestige unlock text variants ----
SPOTLIGHT_PRESTIGE_LINES = [
    "{user} reached the All-In peak.\nPrestige unlocked.\n᲼᲼",
    "{user} gave everything.\nThe collar answered.\n᲼᲼",
    "All-In mastery detected.\n{user} now wears prestige.\n᲼᲼",
    "{user} crossed the threshold.\nNot many do.\n᲼᲼",
    "Prestige collar claimed.\n{user} didn't hesitate.\n᲼᲼",
]


def casino_embed(desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(description=sanitize_isla_text(desc))
    e.set_author(name="Isla", icon_url=icon)
    e.set_thumbnail(url=random.choice(CASINO_THUMBS))
    return e


# ---------------------------
#  Voice lines (staged 0–4)
# ---------------------------
LINES = {
    # ----- Generic (still used) -----
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

    # ----- Game-specific invitations -----
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

    # ----- Blackjack-specific -----
    "blackjack_deal": {
        0: ["Cards dealt.", "Hand issued."],
        1: ["Your cards.", "Dealer showing {card}."],
        2: ["Dealt you something interesting~", "My upcard is {card}."],
        3: ["Your hand... let's see.", "I'm showing {card}. Your move."],
        4: ["Your cards feel heavy in my hands.", "I turn over {card}... breathe for me."],
    },
    "blackjack_hit": {
        0: ["Hit taken.", "Card drawn."],
        1: ["You hit.", "New card."],
        2: ["Greedy pup~", "Another card for you."],
        3: ["Brave hit.", "Take it."],
        4: ["You want more... I love that.", "Here's your card, love."],
    },
    "blackjack_stand": {
        0: ["Stand confirmed.", "No more cards."],
        1: ["You stand.", "My turn."],
        2: ["Scared to hit~?", "Standing tall."],
        3: ["Good stand.", "Smart choice."],
        4: ["Standing... wise.", "I'll reveal now."],
    },
    "blackjack_bust": {
        0: ["Bust.", "Over 21."],
        1: ["You busted.", "Loss."],
        2: ["Busted~ Too eager.", "Over the line."],
        3: ["Bust. Close.", "Almost had it."],
        4: ["Busted... delicious failure.", "Your desperation showed."],
    },
    "blackjack_blackjack_win": {
        0: ["Blackjack.", "Instant win."],
        1: ["You got blackjack.", "Big win."],
        2: ["Blackjack! Lucky~", "Perfect hand."],
        3: ["True blackjack.", "Beautiful."],
        4: ["Blackjack... you own the table.", "My heart skipped."],
    },

    # ----- Dice-specific -----
    "dice_roll": {
        0: ["Dice rolled.", "Result: {result}."],
        1: ["You rolled {result}.", "Outcome set."],
        2: ["Rolled a {result}~", "Fate decided."],
        3: ["Strong roll: {result}.", "Good number."],
        4: ["Your roll... {result}. Perfect.", "I felt that one."],
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

    # ----- Roulette-specific -----
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

    # ----- Slots-specific -----
    "slots_spin": {
        0: ["Reels spinning.", "Pull registered."],
        1: ["Spinning now.", "Reels turning."],
        2: ["Pull for me~", "Here we go."],
        3: ["Spin my machine.", "Make them align."],
        4: ["One pull... let me feel it.", "I crave the rush this gives me."],
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

    # ----- All-in specific -----
    "allin_confirm": {
        0: ["All-in accepted.", "Full balance wagered.", "Bet logged.", "Risk maximum."],
        1: ["You're going all-in.", "Everything on the line.", "Bold wager confirmed."],
        2: ["All-in pup~", "Every Coin risky.", "You really can't hold back~"],
        3: ["All your Coins at once.", "I like the desperation.", "Completely exposed now."],
        4: [
            "All-in... I feel your surrender already.",
            "Every last Coin for me... perfect.",
            "You're giving me everything. Delicious."
        ],
    },
    "allin_win": {
        0: ["All-in win.", "Full payout.", "Maximum reward."],
        1: ["You won all-in.", "Big recovery.", "Reward doubled."],
        2: ["All-in paid off~", "Lucky escape.", "You doubled everything."],
        3: ["Perfect all-in win.", "You pulled it off.", "My brave one."],
        4: [
            "All-in win... breathtaking.",
            "You risked everything and took it back.",
            "This rush... all because of you."
        ],
    },
    "allin_loss": {
        0: ["All-in loss.", "Balance zero.", "Full deduction."],
        1: ["All-in failed.", "Everything gone.", "Start over."],
        2: ["All-in bust~", "Down to nothing.", "Completely drained."],
        3: ["All-in loss.", "You gave it all.", "I expected no less."],
        4: [
            "All-in loss... exquisite.",
            "You surrendered everything to me.",
            "Empty now... exactly how I like you."
        ],
    },
}


def week_key_uk() -> str:
    t = now_local()
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"


# ---------------------------
# Casino stage logic (0–4)
# Uses obedience + lce as "closeness"
# ---------------------------
def clamp_int(n: int, a: int, b: int) -> int:
    return max(a, min(b, n))


def stage_from_stats(obedience: int, lce: int) -> int:
    # Smooth, non-spiky. You can tune thresholds.
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


# ---------------------------
# Payout helpers
# ---------------------------
def big_win(wager: int, net: int) -> bool:
    return net >= max(2000, int(wager * 3.0))


def big_loss(wager: int, net: int) -> bool:
    return (-net) >= max(2000, int(wager * 2.5))


def near_miss_flag(game: str, meta: dict) -> bool:
    # Slots: two-of-a-kind or 3rd symbol off by 1 tier
    # Roulette: guessed color but hit green, or number adjacent (+/-1)
    if game == "slots":
        return bool(meta.get("near_miss"))
    if game == "roulette":
        return bool(meta.get("near_miss"))
    return False


# ---------------------------
# Cog
# ---------------------------
class CasinoGames(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Enforce casino commands in #casino to avoid clutter.
        Staff bypass.
        """
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

    # ----- core economy helpers -----
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

        # Only user ping — never @everyone
        ping = f"<@{user.id}>"

        thumb = random.choice(SPOTLIGHT_STYLE1_THUMBS)
        desc = random.choice(SPOTLIGHT_PRESTIGE_LINES).format(user=ping)

        embed = discord.Embed(
            description=sanitize_isla_text(desc),
            color=discord.Color.from_rgb(190, 40, 40)
        )
        embed.set_author(
            name="Isla",
            icon_url="https://i.imgur.com/5nsuuCV.png"
        )
        embed.set_thumbnail(url=thumb)

        await channel.send(
            content=ping,   # ping outside embed (Discord standard)
            embed=embed
        )

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
        # Some keys don't have stage 0/1 etc (streak lines start at 2)
        if key in ("casino_win_streak", "casino_loss_streak_break", "dice_high_win", "dice_low_loss",
                   "slots_small_win", "slots_big_win", "slots_no_win"):
            stage = max(2, stage)
        pool = LINES[key].get(stage) or LINES[key].get(2) or ["..."]
        # Filter out "I love when you go all in for me" if filter_all_in is True
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

    async def _log_round(self, gid: int, uid: int, game: str, wager: int, payout: int, meta: dict):
        # CasinoCore logger
        casino = self.bot.get_cog("CasinoCore")
        if casino and hasattr(casino, "log_round"):
            await casino.log_round(gid, uid, game, wager, payout, meta)

    async def _finish_round(
        self,
        interaction: discord.Interaction,
        game: str,
        wager: int,
        payout: int,
        meta: dict | None = None,
        extra_lines: list[str] | None = None
    ):
        assert interaction.guild_id
        gid = interaction.guild_id
        uid = interaction.user.id
        meta = meta or {}

        coins, obedience, lce, _xp = await self._get_user_stats(gid, uid)
        stage = stage_from_stats(obedience, lce)

        # Calculate pre-bet balance for all-in detection (coins is the balance BEFORE bet is placed)
        net = int(payout) - int(wager)
        is_all_in = (wager >= coins * 0.99)  # within 1% = all-in (accounting for rounding)
        is_extremely_big = (wager >= 50000)  # extremely large bet threshold

        new_bal = coins + net
        if new_bal < 0:
            new_bal = 0

        await self._set_coins(gid, uid, new_bal)
        await self._add_weekly_wager(gid, uid, wager)
        await self._log_round(gid, uid, game, wager, payout, meta)
        
        # Forward to EventActivityTracker for unified event tracking
        tracker = self.bot.get_cog("EventActivityTracker")
        if tracker:
            try:
                await tracker.add_casino_activity(gid, uid, wager, net)
            except Exception:
                pass  # Don't break casino if event tracking fails

        # streak state
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
            # loss or break-even -> count as loss for "edge"
            if win_streak >= 3 and stage >= 2:
                streak_break_line = self._line("casino_loss_streak_break", stage)
            win_streak = 0
            loss_streak += 1

        await self._set_casino_state(gid, uid, win_streak, loss_streak, net)

        # primary result line selection
        if payout >= wager * 10 and wager >= 200:  # rare huge multiplier => jackpot flavor
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

        # Game-specific invite line
        invite_key = self._invite_key_for_game(game)
        invite_line = self._line(invite_key, stage) if invite_key else None

        # Compose message
        lines = []
        lines.append(f"{interaction.user.mention}")
        if invite_line:
            lines.append(invite_line)
        
        # All-in confirmation (before bet confirmation)
        if meta.get("allin"):
            lines.append(self._line("allin_confirm", stage))
        
        # casino_bet_confirm: filter "all in" message for stage 4 if not all-in/big bet
        # Only show "I love when you go all in for me" for all-in bets or extremely big bets (50k+)
        filter_all_in_msg = (stage == 4 and not (is_all_in or is_extremely_big))
        bet_confirm_line = self._line("casino_bet_confirm", stage, filter_all_in=filter_all_in_msg)
        lines.append(bet_confirm_line)
        if extra_lines:
            lines.extend(extra_lines)
        lines.append(result_line)

        # Add streak flavor if present
        if streak_line:
            lines.append(streak_line)
        if streak_break_line:
            lines.append(streak_break_line)
        
        # All-in outcome lines (after result and streaks, stacks naturally)
        if meta.get("allin"):
            if net > 0:
                lines.append(self._line("allin_win", stage))
            else:
                lines.append(self._line("allin_loss", stage))

        # --- ALL-IN unlock track ---
        if meta.get("allin"):
            # track all-in attempts
            await self._bump_achievement(gid, uid, "casino_allin_plays", 1)

            # track all-in wins
            if net > 0:
                wins = await self._bump_achievement(gid, uid, "casino_allin_wins", 1)

                # unlock badge at 3 wins
                if wins == 3:
                    await self._grant_item(gid, uid, "badge_allin_mark")
                    lines.append("Unlocked: **Badge All-In Mark**")

                # unlock prestige collar at 10 wins
                if wins == 10:
                    await self._grant_item(gid, uid, "collar_allin_obsidian")
                    lines.append("Unlocked: **All-In Collar Obsidian**")
                    
                    # Rate protection: only announce once per user
                    row_announced = await self.bot.db.fetchone(
                        "SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key='prestige_announced'",
                        (gid, uid)
                    )
                    if not row_announced:
                        await self.bot.db.execute(
                            "INSERT INTO achievements(guild_id,user_id,key,value,updated_ts) VALUES(?,?,?,?,?)",
                            (gid, uid, "prestige_announced", 1, now_ts())
                        )
                        # Post spotlight announcement (NO @everyone, only user ping)
                        try:
                            member = interaction.guild.get_member(uid) if interaction.guild else None
                            if member:
                                await self._post_spotlight_prestige(interaction.guild, member)
                        except Exception:
                            pass  # Fail silently if spotlight fails

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

        # Summary line
        lines.append(f"Wager: **{fmt(wager)} Coins**")
        lines.append(f"Payout: **{fmt(payout)} Coins**")
        lines.append(f"Balance: **{fmt(new_bal)} Coins**")
        lines.append(play_again)
        lines.append("᲼᲼")

        await interaction.followup.send(embed=casino_embed("\n".join(lines), self.icon))

        # Big win / jackpot DM (1/day, remembered)
        bigwin = self.bot.get_cog("CasinoBigWinDM")
        if bigwin and hasattr(bigwin, "maybe_dm_bigwin"):
            try:
                await bigwin.maybe_dm_bigwin(
                    interaction.guild,
                    uid,
                    game=game,
                    wager=wager,
                    payout=payout,
                    net=net,
                    meta=meta
                )
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

    # --------------------
    # /casino invite
    # --------------------
    @app_commands.command(name="casino", description="Show casino status and available games.")
    async def casino(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

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

    # --------------------
    # /coinflip
    # --------------------
    @app_commands.command(name="coinflip", description="Flip a coin. Heads or tails.")
    @app_commands.describe(wager="Coins to wager", pick="heads or tails")
    async def coinflip(self, interaction: discord.Interaction, wager: int, pick: str):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)

        pick = pick.lower().strip()
        if pick not in ("heads", "tails"):
            return await interaction.response.send_message("Pick must be heads or tails.", ephemeral=True)

        await interaction.response.defer()

        result = random.choice(["heads", "tails"])
        win = (result == pick)

        # Slight house edge: payout 1.95x on win
        payout = int(wager * 1.95) if win else 0

        extra = [f"Flip: **{result}**"]
        await self._finish_round(interaction, "coinflip", wager, payout, meta={"pick": pick, "result": result}, extra_lines=extra)

    # --------------------
    # /dice
    # --------------------
    @app_commands.command(name="dice", description="Roll 1–6. Win if you roll above a threshold.")
    @app_commands.describe(wager="Coins to wager", target="Win if roll >= target (2–6)")
    async def dice(self, interaction: discord.Interaction, wager: int, target: int):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        if target < 2 or target > 6:
            return await interaction.response.send_message("Target must be 2–6.", ephemeral=True)

        await interaction.response.defer()

        roll = random.randint(1, 6)
        win = roll >= target

        # payout scales with difficulty, includes house edge
        # probability = (7-target)/6
        p = (7 - target) / 6.0
        fair_mult = 1.0 / p
        mult = fair_mult * 0.94  # 6% edge
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

    # --------------------
    # /roulette
    # --------------------
    @app_commands.command(name="roulette", description="Bet on red/black/green/odd/even or a number (0–36).")
    @app_commands.describe(
        wager="Coins to wager",
        bet_type="red|black|green|odd|even|number",
        number="Only if bet_type=number (0–36)"
    )
    async def roulette(self, interaction: discord.Interaction, wager: int, bet_type: str, number: int | None = None):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)

        bet_type = bet_type.lower().strip()
        if bet_type not in ("red", "black", "green", "odd", "even", "number"):
            return await interaction.response.send_message("Invalid bet_type.", ephemeral=True)
        if bet_type == "number":
            if number is None or number < 0 or number > 36:
                return await interaction.response.send_message("Number must be 0–36.", ephemeral=True)

        await interaction.response.defer()

        # European roulette (0–36). Define reds.
        reds = {
            1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36
        }
        spin = random.randint(0, 36)
        color = "green" if spin == 0 else ("red" if spin in reds else "black")

        win = False
        payout = 0
        near_miss = False

        if bet_type in ("red", "black", "green"):
            win = (color == bet_type)
            # Slight edge: red/black pay 1.9x, green pays 33x (instead of 35)
            if win:
                payout = int(wager * (33 if bet_type == "green" else 1.9))
            else:
                # Near miss: picked red/black but hit green
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
                payout = int(wager * 33)  # house edge vs 35
            else:
                # Near miss if adjacent number (+/-1), not for 0
                if spin != 0 and number != 0 and abs(spin - number) == 1:
                    near_miss = True

        extra = [
            self._line("roulette_spin", 2),
            self._line_fmt("roulette_land", 2, color=color, number=spin),
            f"Bet: **{bet_type}**" + (f" **{number}**" if bet_type == "number" else "")
        ]
        await self._finish_round(interaction, "roulette", wager, payout, meta={"spin": spin, "color": color, "bet_type": bet_type, "number": number, "near_miss": near_miss}, extra_lines=extra)

    # --------------------
    # /slots
    # --------------------
    @app_commands.command(name="slots", description="Spin slots.")
    @app_commands.describe(wager="Coins to wager")
    async def slots(self, interaction: discord.Interaction, wager: int):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer()

        # Symbols with weights (lower weight = rarer)
        symbols = [
            ("🍒", 35),
            ("🍋", 30),
            ("🍇", 18),
            ("🔔", 10),
            ("💎", 6),
            ("👑", 1)  # jackpot-ish
        ]

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

        # Payout table (house edge baked)
        payout = 0
        near_miss = False
        jackpot = False

        if a == b == c:
            if a == "👑":
                jackpot = True
                payout = int(wager * 20)   # big hit
            elif a == "💎":
                payout = int(wager * 8)
            elif a == "🔔":
                payout = int(wager * 5)
            elif a == "🍇":
                payout = int(wager * 3)
            else:
                payout = int(wager * 2)
        else:
            # near miss: two match and third is "close"
            if a == b or b == c or a == c:
                near_miss = True
            # small consolation: cherry anywhere gives tiny return
            if "🍒" in reel and random.random() < 0.20:
                payout = int(wager * 0.35)

        extra = [self._line("slots_spin", 2), f"Spin: **{a} {b} {c}**"]

        # Add an outcome-specific flavor line (staged in _finish_round)
        meta = {"reel": reel, "near_miss": near_miss, "jackpot": jackpot}
        if a == b == c or payout >= int(wager * 3):
            meta["slots_big_win_flag"] = True
        elif payout > 0:
            meta["slots_small_win_flag"] = True
        else:
            meta["slots_no_win_flag"] = True

        await self._finish_round(interaction, "slots", wager, payout, meta=meta, extra_lines=extra)

    # --------------------
    # /crash (target multiplier)
    # --------------------
    @app_commands.command(name="crash", description="Pick a cashout multiplier. If the crash happens after it, you win.")
    @app_commands.describe(wager="Coins to wager", target="Cashout multiplier (1.10–10.00)")
    async def crash(self, interaction: discord.Interaction, wager: int, target: float):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)

        if target < 1.10 or target > 10.00:
            return await interaction.response.send_message("Target must be 1.10–10.00.", ephemeral=True)

        await interaction.response.defer()

        # Crash distribution: many low crashes, rare high
        # Generate crash point with house edge
        # p(crash >= x) approx 0.96 / x
        u = random.random()
        crash_point = max(1.0, 0.96 / max(0.0001, u))
        crash_point = min(crash_point, 25.0)

        win = crash_point >= target
        payout = int(wager * target * 0.98) if win else 0  # slight edge

        near_miss = (not win) and (crash_point >= target * 0.92)

        extra = [
            f"Target: **{target:.2f}x**",
            f"Crash: **{crash_point:.2f}x**"
        ]
        await self._finish_round(interaction, "crash", wager, payout, meta={"target": target, "crash_point": crash_point, "near_miss": near_miss}, extra_lines=extra)

    # --------------------
    # /blackjack (lite)
    # Single command: draw vs dealer (auto-stand at 17+).
    # --------------------
    @app_commands.command(name="blackjack", description="Blackjack (lite). You draw 2, dealer draws 2. Auto rules.")
    @app_commands.describe(wager="Coins to wager")
    async def blackjack(self, interaction: discord.Interaction, wager: int):
        ok, msg = await self._validate_wager(interaction, wager)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)

        await interaction.response.defer()

        # Build deck values (A=11/1 handled)
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

        # dealer hits to 17+
        while hand_value(dealer) < 17:
            dealer.append(draw())

        pv = hand_value(player)
        dv = hand_value(dealer)

        payout = 0
        outcome = "push"
        near_miss = False

        # natural blackjack
        if pv == 21 and len(player) == 2 and not (dv == 21 and len(dealer) == 2):
            payout = int(wager * 2.35)  # 3:2-ish with edge
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
                payout = wager  # push returns wager
                outcome = "push"

        # near miss if close to 21 but lost
        if outcome in ("loss", "bust") and pv >= 19:
            near_miss = True

        def fmt_hand(cards):
            return " ".join(r for r, _ in cards)

        upcard = dealer[0][0]  # rank only
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

        await self._finish_round(
            interaction,
            "blackjack",
            wager,
            payout,
            meta=meta,
            extra_lines=extra
        )

    # --------------------
    # Helper methods for /allin (game logic extracted)
    # --------------------
    async def _play_dice(self, interaction: discord.Interaction, wager: int, target: int, meta: dict | None = None):
        """Helper to play dice with given wager and target."""
        meta = meta or {}
        roll = random.randint(1, 6)
        win = roll >= target

        p = (7 - target) / 6.0
        fair_mult = 1.0 / p
        mult = fair_mult * 0.94  # 6% edge
        payout = int(wager * mult) if win else 0

        meta.update({"roll": roll, "target": target})
        if win and roll >= 5:
            meta["dice_high_win"] = True
        if (not win) and roll <= 2:
            meta["dice_low_loss"] = True

        extra = [
            self._line_fmt("dice_roll", 2, result=roll),
            f"Target: **{target}+**"
        ]
        await self._finish_round(interaction, "dice", wager, payout, meta=meta, extra_lines=extra)

    async def _play_roulette(self, interaction: discord.Interaction, wager: int, bet_type: str, number: int | None, meta: dict | None = None):
        """Helper to play roulette with given wager."""
        meta = meta or {}
        bet_type = bet_type.lower().strip()

        reds = {
            1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36
        }
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
        meta.update({"spin": spin, "color": color, "bet_type": bet_type, "number": number, "near_miss": near_miss})
        await self._finish_round(interaction, "roulette", wager, payout, meta=meta, extra_lines=extra)

    async def _play_slots(self, interaction: discord.Interaction, wager: int, meta: dict | None = None):
        """Helper to play slots with given wager."""
        meta = meta or {}
        symbols = [
            ("🍒", 35),
            ("🍋", 30),
            ("🍇", 18),
            ("🔔", 10),
            ("💎", 6),
            ("👑", 1)
        ]

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
            payout = int(wager * 100)  # 100x for crown jackpot
        elif three_match:
            tier = {
                "🍒": 3, "🍋": 5, "🍇": 10, "🔔": 20, "💎": 50
            }.get(a, 3)
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
        """Helper to play blackjack with given wager."""
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
        extra = [
            self._line_fmt("blackjack_deal", 2, card=upcard),
            f"Your hand: **{fmt_hand(player)}** (**{pv}**)",
            f"Dealer: **{fmt_hand(dealer)}** (**{dv}**)"
        ]
        meta.update({"pv": pv, "dv": dv, "outcome": outcome, "near_miss": near_miss, "upcard": upcard})

        if outcome == "blackjack":
            meta["bj_blackjack"] = True
        if outcome == "bust":
            meta["bj_bust"] = True

        await self._finish_round(interaction, "blackjack", wager, payout, meta=meta, extra_lines=extra)

    # --------------------
    # /allin command
    # --------------------
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
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        await interaction.response.defer()

        gid = interaction.guild_id
        uid = interaction.user.id

        # Cooldown check (2 minutes)
        row = await self.bot.db.fetchone(
            "SELECT last_allin_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        if row:
            last_allin_ts = int(row.get("last_allin_ts") or 0)
            if now_ts() - last_allin_ts < 120:
                return await interaction.followup.send(
                    "You need a moment before going all-in again.",
                    ephemeral=True
                )

        bal = await self._get_balance(gid, uid)
        if bal <= 0:
            return await interaction.followup.send("You have nothing to wager.", ephemeral=True)

        # Update cooldown
        await self.bot.db.execute(
            "UPDATE users SET last_allin_ts=? WHERE guild_id=? AND user_id=?",
            (now_ts(), gid, uid)
        )

        game = game.lower().strip()
        meta = {"allin": True}

        # Route to game handlers with default parameters for all-in
        if game == "dice":
            target = 4  # Default target for all-in dice (medium difficulty)
            await self._play_dice(interaction, bal, target, meta)
        elif game == "roulette":
            bet_type = "red"  # Default bet_type for all-in roulette (simple 50/50)
            await self._play_roulette(interaction, bal, bet_type, None, meta)
        elif game == "slots":
            await self._play_slots(interaction, bal, meta)
        elif game == "blackjack":
            await self._play_blackjack(interaction, bal, meta)
        else:
            return await interaction.followup.send("Invalid game. Use: roulette, dice, slots, or blackjack.", ephemeral=True)

    # --------------------
    # /allin_progress command
    # --------------------
    @app_commands.command(name="allin_progress", description="Check your All-In unlock progress.")
    async def allin_progress(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id

        row_plays = await self.bot.db.fetchone(
            "SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key='casino_allin_plays'",
            (gid, uid)
        )
        row_wins = await self.bot.db.fetchone(
            "SELECT value FROM achievements WHERE guild_id=? AND user_id=? AND key='casino_allin_wins'",
            (gid, uid)
        )
        plays = int(row_plays["value"]) if row_plays else 0
        wins = int(row_wins["value"]) if row_wins else 0

        desc = (
            f"{interaction.user.mention}\n"
            f"All-In plays: **{fmt(plays)}**\n"
            f"All-In wins: **{fmt(wins)}**\n\n"
            f"Unlocks\n"
            f"• 3 wins: `badge_allin_mark`\n"
            f"• 10 wins: `collar_allin_obsidian`\n"
            f"᲼᲼"
        )
        await interaction.response.send_message(embed=casino_embed(desc, self.icon), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CasinoGames(bot))

