"""
Announcements Cog
Consolidates: daily_presence, announce_and_remind, leaderboard, casino_daily_recap
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from datetime import time
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands

from core.utility import now_ts, now_local, fmt, day_key
from core.personality import sanitize_isla_text, isla_embed as core_isla_embed
from utils.embed_utils import create_embed
from utils.isla_style import isla_embed as style_isla_embed
from utils.uk_parse import parse_when_to_ts, parse_duration_to_seconds, human_eta

UK_TZ = ZoneInfo("Europe/London")

CASINO_THUMBS = [
    "https://i.imgur.com/jzk6IfH.png",
    "https://i.imgur.com/cO7hAij.png",
    "https://i.imgur.com/My3QzNu.png",
    "https://i.imgur.com/kzwCK79.png",
    "https://i.imgur.com/jGnkAKs.png"
]


# Helper functions
def simple_embed(desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(description=desc)
    e.set_author(name="Isla", icon_url=icon)
    return e


def casino_embed(desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(description=sanitize_isla_text(desc))
    e.set_author(name="Isla", icon_url=icon)
    e.set_thumbnail(url=random.choice(CASINO_THUMBS))
    return e


def parse_window(s: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    a, b = s.split("-")
    ah, am = [int(x) for x in a.split(":")]
    bh, bm = [int(x) for x in b.split(":")]
    return (ah, am), (bh, bm)


def mins(hm: Tuple[int, int]) -> int:
    return hm[0] * 60 + hm[1]


def now_minute_of_day() -> int:
    t = now_local()
    return t.hour * 60 + t.minute


@dataclass
class DailyState:
    day_key: str
    awake: bool = False
    start_minute: int = 0
    sleep_minute: int = 0
    mood: str = "neutral"  # "good" | "bad" | "neutral"
    posts_sent: int = 0
    spotlight_posts_sent: int = 0
    last_post_ts: int = 0
    last_orders_msg_id: Optional[int] = None
    chain_step: int = 0
    last_chain_ts: int = 0
    last_presence_ts: int = 0


class Announcements(commands.Cog):
    """
    Consolidated announcements cog:
    - Daily presence system (Isla's daily behavior/mood)
    - Announcement scheduling and reminders
    - Spotlight leaderboard tracking
    - Casino daily recap posts
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        
        # Daily presence state
        self.thoughts = self._load_thoughts()
        self.icon = self.thoughts["meta"].get("author_icon_default", self.icon)
        self.state: Dict[int, DailyState] = {}  # guild_id -> state
        
        # Leaderboard state
        self._last_counted: dict[tuple[int, int], int] = {}  # (guild_id, user_id) -> ts
        
        # Announce group
        self.announce = app_commands.Group(name="announce", description="Announcements")
        self._register_announce_commands()
        
        # Start loops
        self.presence_tick.start()
        self.announce_loop.start()
        self.remind_loop.start()
        self.casino_recap_loop.start()
    
    def cog_unload(self):
        self.presence_tick.cancel()
        self.announce_loop.cancel()
        self.remind_loop.cancel()
        self.casino_recap_loop.cancel()
    
    # ========================================================================
    # DAILY PRESENCE (from daily_presence.py)
    # ========================================================================
    
    def _load_thoughts(self) -> dict:
        import os
        thoughts_path = self.bot.cfg.get("presence", "thoughts_path", default="data/isla_presence_thoughts.json")
        bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(bot_dir, thoughts_path)
        if not os.path.exists(path):
            return {"meta": {"author_icon_default": self.icon}, "routing": {}, "thoughts": {}}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _day_key(self) -> str:
        t = now_local()
        return f"{t.year}-{t.month:02d}-{t.day:02d}"
    
    def _route_channel_id(self, kind: str) -> Optional[int]:
        route = self.thoughts.get("routing", {}).get(kind)
        if not route:
            return None
        return self.bot.cfg.get("channels", route)
    
    def _pick(self, key: str, mood: str = None) -> str:
        pool = self.thoughts["thoughts"].get(key)
        if isinstance(pool, dict) and mood:
            pool = pool.get(mood, pool.get("neutral", []))
            if isinstance(pool, list):
                return random.choice(pool)
        elif isinstance(pool, list):
            return random.choice(pool)
        return ""
    
    async def _send(self, guild: discord.Guild, kind: str, text: str) -> Optional[int]:
        ch_id = self._route_channel_id(kind)
        if not ch_id:
            return None
        ch = guild.get_channel(int(ch_id))
        if not isinstance(ch, discord.TextChannel):
            return None
        text = sanitize_isla_text(text)
        msg = await ch.send(embed=simple_embed(text, self.icon))
        
        if hasattr(self.bot, 'memory'):
            try:
                await self.bot.memory.save_conversation(
                    guild_id=guild.id,
                    channel_id=ch.id,
                    user_id=self.bot.user.id if self.bot.user else 0,
                    message_content=text,
                    bot_response=None,
                    message_id=msg.id,
                    context={"kind": kind, "mood": getattr(self.state.get(guild.id), 'mood', 'neutral')},
                    interaction_type="daily_presence"
                )
            except Exception:
                pass
        
        return msg.id
    
    async def _activity_since(self, channel: discord.TextChannel, since_ts: int) -> Tuple[int, int]:
        msg_count = 0
        speakers = set()
        async for m in channel.history(limit=200):
            if m.created_at.timestamp() < since_ts:
                break
            if m.author.bot:
                continue
            msg_count += 1
            speakers.add(m.author.id)
        return msg_count, len(speakers)
    
    async def _reaction_count(self, channel: discord.TextChannel, message_id: Optional[int]) -> int:
        if not message_id:
            return 0
        try:
            m = await channel.fetch_message(message_id)
            return sum(int(r.count) for r in m.reactions)
        except Exception:
            return 0
    
    async def _voice_window_stats_exact(self, guild: discord.Guild, since_ts: int) -> tuple[int, int | None]:
        gid = guild.id
        now = now_ts()
        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, SUM(seconds) AS total_sec
            FROM voice_events
            WHERE guild_id=? AND end_ts>=? AND end_ts<=?
            GROUP BY user_id
            """,
            (gid, since_ts, now)
        )
        if not rows:
            return (0, None)
        total = 0
        top_uid = None
        top_sec = 0
        for r in rows:
            uid = int(r["user_id"])
            sec = int(r["total_sec"] or 0)
            total += sec
            if sec > top_sec:
                top_sec = sec
                top_uid = uid
        return (total, top_uid)
    
    async def _get_top_user_mention(self, guild: discord.Guild) -> str:
        try:
            row = await self.bot.db.fetchone(
                "SELECT user_id FROM users WHERE guild_id=? ORDER BY lce DESC LIMIT 1",
                (guild.id,)
            )
            if row:
                return f"<@{int(row['user_id'])}>"
        except Exception:
            pass
        return "someone"
    
    async def _casino_window_stats(self, guild: discord.Guild, since_ts: int) -> Tuple[int, Optional[int]]:
        gid = guild.id
        try:
            rows = await self.bot.db.fetchall(
                "SELECT context, hash FROM msg_memory WHERE guild_id=? AND context LIKE 'casino_rounds:%' ORDER BY created_ts DESC LIMIT 4",
                (gid,)
            )
        except Exception:
            return (0, None)
        total = 0
        per_user = {}
        for r in rows:
            try:
                data = json.loads(r["hash"])
                if not isinstance(data, list):
                    continue
            except Exception:
                continue
            for ev in data:
                try:
                    ts = int(ev.get("ts", 0))
                    if ts < since_ts:
                        continue
                    uid = int(ev.get("uid", 0))
                    wager = int(ev.get("wager", 0))
                except Exception:
                    continue
                if uid <= 0 or wager <= 0:
                    continue
                total += wager
                per_user[uid] = per_user.get(uid, 0) + wager
        if not per_user:
            return (total, None)
        top_uid = max(per_user.items(), key=lambda kv: kv[1])[0]
        return (total, top_uid)
    
    def _pick_daily_times(self) -> Tuple[int, int]:
        (sh, sm), (eh, em) = parse_window(self.bot.cfg.get("presence", "morning_start_window", default="12:00-15:00"))
        start = random.randint(mins((sh, sm)), mins((eh, em)))
        (sh2, sm2), (eh2, em2) = parse_window(self.bot.cfg.get("presence", "sleep_window", default="00:00-03:00"))
        sleep = random.randint(mins((sh2, sm2)), mins((eh2, em2)))
        return start, sleep
    
    def _mood_for_day(self) -> str:
        roll = random.random()
        if roll < 0.35:
            return "good"
        if roll > 0.80:
            return "bad"
        return "neutral"
    
    def _pace_multiplier(self, mood: str) -> float:
        if mood == "good":
            return float(self.bot.cfg.get("presence", "mood_awake_fast_mult", default=0.7))
        if mood == "bad":
            return float(self.bot.cfg.get("presence", "mood_tired_slow_mult", default=1.4))
        return 1.0
    
    def _next_delay_sec(self, mood: str) -> int:
        base = random.randint(6*60, 18*60)
        mult = self._pace_multiplier(mood)
        return int(base * mult)
    
    def _silence_followup_delay(self, mood: str) -> int:
        base = random.randint(5*60, 15*60)
        mult = self._pace_multiplier(mood)
        return int(base * mult)
    
    async def _run_morning_chain(self, guild: discord.Guild, st: DailyState):
        orders_id = self.bot.cfg.get("channels", "orders")
        orders = guild.get_channel(int(orders_id)) if orders_id else None
        if not isinstance(orders, discord.TextChannel):
            return
        low_msg = int(self.bot.cfg.get("presence", "low_activity_msg_threshold", default=18))
        low_uniq = int(self.bot.cfg.get("presence", "low_activity_unique_threshold", default=6))
        react_threshold = int(self.bot.cfg.get("presence", "reaction_threshold", default=3))
        
        if st.chain_step == 0:
            st.last_orders_msg_id = await self._send(guild, "MORNING", self._pick("PHASE1_GREET", st.mood))
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            st.last_presence_ts = st.last_post_ts
            st.chain_step = 1
            return
        
        if st.chain_step == 1:
            since_ts = st.last_presence_ts or (now_ts() - random.randint(6*3600, 12*3600))
            msg_count, uniq = await self._activity_since(orders, since_ts)
            casino_total, _ = await self._casino_window_stats(guild, since_ts)
            voice_total_sec, top_voice_uid = await self._voice_window_stats_exact(guild, since_ts)
            if casino_total >= 5000:
                text = self._pick("NIGHT_ACTIVITY_CASINO")
            elif msg_count < low_msg and uniq < low_uniq:
                text = self._pick("NIGHT_ACTIVITY_QUIET")
            else:
                text = self._pick("NIGHT_ACTIVITY_ACTIVE")
            st.last_orders_msg_id = await self._send(guild, "OBSERVE", text)
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            st.chain_step = 2
            return
        
        if st.chain_step == 2:
            reacts = await self._reaction_count(orders, st.last_orders_msg_id)
            msg_count, uniq = await self._activity_since(orders, st.last_post_ts - 12*60)
            if reacts >= react_threshold:
                text = self._pick("REACTION_NOTICED")
            elif msg_count < max(6, low_msg//3) and uniq < max(3, low_uniq//2):
                text = self._pick("FOLLOWUP_REACTIVE_QUIET")
            else:
                text = self._pick("FOLLOWUP_REACTIVE_ACTIVE")
            st.last_orders_msg_id = await self._send(guild, "OBSERVE", text)
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            st.chain_step = 3
            return
        
        if st.chain_step == 3:
            since_ts = st.last_presence_ts or (now_ts() - random.randint(6*3600, 12*3600))
            casino_total, top_uid = await self._casino_window_stats(guild, since_ts)
            if casino_total >= 2500:
                await self._send(guild, "CASINO_RECAP_PROMPT", self._pick("CASINO_RECAP_PROMPT"))
                window_hours = max(1, int((now_ts() - since_ts) / 3600))
                stats_line = self._pick("CASINO_RECAP_STATS").replace("{window}", f"last {window_hours}h").replace("{spent}", fmt(casino_total))
                await self._send(guild, "CASINO_RECAP_STATS", stats_line)
                if top_uid:
                    tops = f"<@{top_uid}>"
                    top_line = self._pick("CASINO_RECAP_TOPSPENDER").replace("{top_spender}", tops)
                    await self._send(guild, "CASINO_RECAP_TOPSPENDER", top_line)
            st.chain_step = 4
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            return
        
        if st.chain_step == 4:
            await self._send(guild, "LEADERBOARD_PROMPT", self._pick("LEADERBOARD_PROMPT"))
            top_user = await self._get_top_user_mention(guild)
            line = self._pick("LEADERBOARD_REACT").replace("{top_user}", top_user)
            await self._send(guild, "LEADERBOARD_REACT", line)
            st.chain_step = 5
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            return
        
        if st.chain_step == 5:
            msg_count, uniq = await self._activity_since(orders, st.last_post_ts - 15*60)
            if msg_count < low_msg and uniq < low_uniq:
                await self._send(guild, "MICRO_ORDER", self._pick("MICRO_ORDER"))
            st.chain_step = 6
            st.last_post_ts = now_ts()
            return
    
    async def _awake_behavior_weights(self, st: DailyState) -> dict:
        if st.mood == "good":
            return {
                "react_check": 0.18, "choose_topic": 0.14, "question_bait": 0.22,
                "casino_peek": 0.18, "leaderboard_peek": 0.18, "mini_order": 0.10
            }
        if st.mood == "bad":
            return {
                "react_check": 0.20, "choose_topic": 0.08, "question_bait": 0.18,
                "casino_peek": 0.16, "leaderboard_peek": 0.20, "mini_order": 0.18
            }
        return {
            "react_check": 0.14, "choose_topic": 0.10, "question_bait": 0.22,
            "casino_peek": 0.16, "leaderboard_peek": 0.18, "mini_order": 0.20
        }
    
    def _weighted_choice(self, weights: dict) -> str:
        r = random.random()
        acc = 0.0
        for k, w in weights.items():
            acc += float(w)
            if r <= acc:
                return k
        return list(weights.keys())[0]
    
    def _connector(self, mood: str) -> str:
        if mood == "good":
            return random.choice(["Mmh.", "Okay.", "Fine.", "So.", "Anyway."])
        if mood == "bad":
            return random.choice(["Right.", "Anyway.", "So.", "Listen.", "Good."])
        return random.choice(["So.", "Anyway.", "Alright.", "Okay.", "Mmh."])
    
    async def _do_react_check(self, guild: discord.Guild, st: DailyState):
        prompt = {
            "neutral": ["If you're here, react to this.\nI want to see a pulse.\n᲼᲼", "React if you're awake.\n᲼᲼"],
            "good": ["React for me.\nLet me see who's paying attention.\n᲼᲼", "Tap a reaction.\nShow me you're here.\n᲼᲼"],
            "bad": ["React.\nNow.\n᲼᲼", "If you're here, prove it.\nReact.\n᲼᲼"]
        }[st.mood]
        msg_id = await self._send(guild, "MORNING", random.choice(prompt))
        if not msg_id:
            return
        st.last_post_ts = now_ts()
        st.last_orders_msg_id = msg_id
        st.last_chain_ts = now_ts()
    
    async def _do_question_bait(self, guild: discord.Guild, st: DailyState):
        prompts = {
            "neutral": ["Say something.\nWhat are you doing today?\n᲼᲼", "What's the plan today.\nOne message.\n᲼᲼", "Talk to me.\nWhat's your mood.\n᲼᲼"],
            "good": ["Talk to me.\nWhat are you up to today.\nMake it interesting.\n᲼᲼", "Tell me what you're doing.\nI'm listening.\n᲼᲼", "Give me one detail about your day.\nI'll decide if it's cute.\n᲼᲼"],
            "bad": ["Speak.\nWhat are you doing.\n᲼᲼", "I'm bored.\nSay something useful.\n᲼᲼", "Tell me what you did today.\nMake it worth reading.\n᲼᲼"]
        }[st.mood]
        await self._send(guild, "MORNING", random.choice(prompts))
    
    async def _do_choose_topic(self, guild: discord.Guild, st: DailyState):
        topics = [("💬", "chat"), ("🎰", "casino"), ("📈", "leaderboard")]
        opener = {
            "neutral": "Pick something.\nReact.\n᲼᲼",
            "good": "Pick for me.\nI'll follow your lead.\n᲼᲼",
            "bad": "Choose.\nDon't waste my time.\n᲼᲼"
        }[st.mood]
        lines = [opener] + [f"{e} {name}" for e, name in topics]
        msg_id = await self._send(guild, "MORNING", "\n".join(lines))
        if msg_id:
            ch_id = self.bot.cfg.get("channels", "orders")
            ch = guild.get_channel(int(ch_id)) if ch_id else None
            if isinstance(ch, discord.TextChannel):
                try:
                    m = await ch.fetch_message(msg_id)
                    for e, _ in topics:
                        await m.add_reaction(e)
                except Exception:
                    pass
            st.last_orders_msg_id = msg_id
    
    async def _do_casino_peek(self, guild: discord.Guild, st: DailyState):
        since_ts = now_ts() - random.randint(3*3600, 8*3600)
        total, top_uid = await self._casino_window_stats(guild, since_ts)
        if total <= 0:
            text = {
                "neutral": "Casino is quiet.\nThat's… unusual.\n᲼᲼",
                "good": "Casino is quiet.\nYou're behaving.\nHow rare.\n᲼᲼",
                "bad": "Casino is quiet.\nSo you're useless everywhere.\n᲼᲼"
            }[st.mood]
            await self._send(guild, "MORNING", text)
            return
        hours = max(1, int((now_ts() - since_ts)/3600))
        intro = {
            "neutral": f"{self._connector(st.mood)} I peeked at the casino.\nLast {hours}h wagered **{fmt(total)} Coins**.\n᲼᲼",
            "good": f"{self._connector(st.mood)} I peeked at the casino.\nLast {hours}h wagered **{fmt(total)} Coins**.\nCute.\n᲼᲼",
            "bad": f"{self._connector(st.mood)} I checked the casino.\nLast {hours}h wagered **{fmt(total)} Coins**.\n᲼᲼"
        }[st.mood]
        await self._send(guild, "MORNING", intro)
        if top_uid:
            tops = f"<@{top_uid}>"
            lines = {
                "neutral": f"Top spender in the last {hours}h: {tops}.\n᲼᲼",
                "good": f"Top spender in the last {hours}h: {tops}.\nI noticed.\n᲼᲼",
                "bad": f"Top spender in the last {hours}h: {tops}.\nAt least someone did something.\n᲼᲼"
            }[st.mood]
            await self._send(guild, "MORNING_CASINO", lines)
    
    async def _do_leaderboard_peek(self, guild: discord.Guild, st: DailyState):
        top_user = await self._get_top_user_mention(guild)
        line = {
            "neutral": f"{self._connector(st.mood)} I checked the leaderboard.\n{top_user} is still on top.\n᲼᲼",
            "good": f"{self._connector(st.mood)} I checked the leaderboard.\n{top_user} is still on top.\nTry to catch them.\n᲼᲼",
            "bad": f"{self._connector(st.mood)} I checked the leaderboard.\n{top_user} is still on top.\nEveryone else is drifting.\n᲼᲼"
        }[st.mood]
        await self._send(guild, "MORNING", line)
    
    async def _do_mini_order(self, guild: discord.Guild, st: DailyState):
        orders = {
            "neutral": ["One message.\nThen you can lurk again.\n᲼᲼", "Say something.\nI want to see you.\n᲼᲼"],
            "good": ["One message for me.\nMake it cute.\n᲼᲼", "Say something.\nI'm in the mood to read.\n᲼᲼"],
            "bad": ["One message.\nNow.\n᲼᲼", "Speak.\nDon't make me wait.\n᲼᲼"]
        }[st.mood]
        await self._send(guild, "MORNING", random.choice(orders))
    
    async def _maybe_spotlight(self, guild: discord.Guild, st: DailyState):
        cap = int(self.bot.cfg.get("presence", "spotlight_posts_per_day_max", default=3))
        if st.spotlight_posts_sent >= cap:
            return
        if random.random() > 0.12:
            return
        await self._send(guild, "SPOTLIGHT_HIGHLIGHT", random.choice(self.thoughts["thoughts"].get("SPOTLIGHT_HIGHLIGHT", [""])))
        st.spotlight_posts_sent += 1
        st.posts_sent += 1
    
    async def _start_day_if_needed(self, guild: discord.Guild, st: DailyState):
        st.start_minute, st.sleep_minute = self._pick_daily_times()
        st.mood = self._mood_for_day()
        st.posts_sent = 0
        st.spotlight_posts_sent = 0
        st.chain_step = 0
        st.last_post_ts = 0
        st.last_presence_ts = now_ts() - random.randint(6*3600, 12*3600)
        st.awake = False
    
    @tasks.loop(seconds=30)
    async def presence_tick(self):
        await self.bot.wait_until_ready()
        if not self.bot.cfg.get("presence", "enabled", default=True):
            return
        for guild in self.bot.guilds:
            gid = guild.id
            day_key = self._day_key()
            st = self.state.get(gid)
            if not st or st.day_key != day_key:
                st = DailyState(day_key=day_key)
                self.state[gid] = st
                await self._start_day_if_needed(guild, st)
            cur_min = now_minute_of_day()
            if not st.awake and cur_min >= st.start_minute and cur_min < 24*60:
                st.awake = True
            if st.awake and cur_min <= st.sleep_minute:
                await self._send(guild, "SLEEP", self._pick("SLEEP"))
                st.awake = False
                continue
            if not st.awake:
                continue
            min_posts = int(self.bot.cfg.get("presence", "awake_posts_per_day_min", default=10))
            max_posts = int(self.bot.cfg.get("presence", "awake_posts_per_day_max", default=25))
            if st.posts_sent >= max_posts:
                continue
            now = now_ts()
            if st.chain_step < 6:
                if st.last_chain_ts == 0 or (now - st.last_chain_ts) >= self._silence_followup_delay(st.mood):
                    await self._run_morning_chain(guild, st)
                    st.posts_sent += 1
                continue
            delay = self._next_delay_sec(st.mood)
            if st.posts_sent < min_posts:
                delay = max(240, delay // 2)
            if st.last_post_ts and (now - st.last_post_ts) < delay:
                continue
            weights = await self._awake_behavior_weights(st)
            behavior = self._weighted_choice(weights)
            try:
                if behavior == "react_check":
                    await self._do_react_check(guild, st)
                elif behavior == "choose_topic":
                    await self._do_choose_topic(guild, st)
                elif behavior == "question_bait":
                    await self._do_question_bait(guild, st)
                elif behavior == "casino_peek":
                    await self._do_casino_peek(guild, st)
                elif behavior == "leaderboard_peek":
                    await self._do_leaderboard_peek(guild, st)
                else:
                    await self._do_mini_order(guild, st)
            except Exception:
                pass
            st.last_post_ts = now_ts()
            st.posts_sent += 1
            await self._maybe_spotlight(guild, st)
    
    @presence_tick.before_loop
    async def before_presence_tick(self):
        await self.bot.wait_until_ready()
    
    # ========================================================================
    # LEADERBOARD (from leaderboard.py)
    # ========================================================================
    
    @commands.Cog.listener("on_message")
    async def on_message_spotlight(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        gid, uid = msg.guild.id, msg.author.id
        await self.bot.db.ensure_user(gid, uid)
        u = await self.bot.db.fetchone(
            "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        if u and u["safeword_until_ts"] and int(u["safeword_until_ts"]) > now_ts():
            return
        key = (gid, uid)
        now = now_ts()
        last = self._last_counted.get(key, 0)
        if now - last < 30:
            return
        self._last_counted[key] = now
        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO spotlight(guild_id,user_id,day_key,msg_count,coins_earned,coins_burned)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(guild_id,user_id,day_key)
               DO UPDATE SET msg_count=msg_count+1""",
            (gid, uid, dk, 1, 0, 0),
        )
    
    async def log_coins_earned(self, gid: int, uid: int, amount: int):
        if amount <= 0:
            return
        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO spotlight(guild_id,user_id,day_key,msg_count,coins_earned,coins_burned)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(guild_id,user_id,day_key)
               DO UPDATE SET coins_earned=coins_earned+?""",
            (gid, uid, dk, 0, amount, 0, amount),
        )
    
    async def log_coins_burned(self, gid: int, uid: int, amount: int):
        if amount <= 0:
            return
        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO spotlight(guild_id,user_id,day_key,msg_count,coins_earned,coins_burned)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(guild_id,user_id,day_key)
               DO UPDATE SET coins_burned=coins_burned+?""",
            (gid, uid, dk, 0, 0, amount, amount),
        )
    
    @app_commands.command(name="spotlight", description="Show today's spotlight leaderboard (activity + coins).")
    async def spotlight(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer()
        gid = interaction.guild.id
        dk = day_key()
        rows = await self.bot.db.fetchall(
            """SELECT user_id,msg_count,coins_earned,coins_burned
               FROM spotlight
               WHERE guild_id=? AND day_key=?
               ORDER BY (coins_earned + coins_burned*2 + msg_count*2) DESC
               LIMIT 10""",
            (gid, dk),
        )
        if not rows:
            await interaction.followup.send("No spotlight data yet today.")
            return
        lines = []
        for i, r in enumerate(rows, start=1):
            uid = int(r["user_id"])
            score = int(r["coins_earned"]) + int(r["coins_burned"]) * 2 + int(r["msg_count"]) * 2
            lines.append(
                f"**{i}.** <@{uid}> — score **{score}** "
                f"(msgs {int(r['msg_count'])}, +{int(r['coins_earned'])}, burned {int(r['coins_burned'])})"
            )
        e = core_isla_embed("Spotlight (Today)", "\n".join(lines), color=0x03A9F4)
        await interaction.followup.send(embed=e)
    
    # ========================================================================
    # ANNOUNCE & REMIND (from announce_and_remind.py)
    # ========================================================================
    
    def _is_mod(self, m: discord.Member) -> bool:
        p = m.guild_permissions
        return p.manage_guild or p.manage_messages or p.administrator
    
    def _register_announce_commands(self):
        self.announce.add_command(self.announce_send)
        self.announce.add_command(self.announce_schedule)
    
    @app_commands.command(name="send", description="Immediate announcement.")
    @app_commands.describe(message="Text to send", title="Embed title (optional)")
    async def announce_send(self, interaction: discord.Interaction, message: str, title: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not self._is_mod(interaction.user):
            return await interaction.response.send_message(embed=style_isla_embed("Not for you.\n᲼᲼", title="Announce"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        embed = create_embed(message + "\n᲼᲼", title=title or "Announcement", color="system", is_dm=False, is_system=True)
        await interaction.channel.send(embed=embed)
        await interaction.followup.send(embed=style_isla_embed("Sent.\n᲼᲼", title="Announce"), ephemeral=True)
    
    @app_commands.command(name="schedule", description="Schedules an announcement with repeats.")
    @app_commands.describe(
        when="Start time: 'in 10m' or 'YYYY-MM-DD HH:MM' (UK)",
        repeat="none, hourly, daily, weekly",
        interval_minutes="For repeat='hourly' you can set interval minutes (optional)",
        title="Embed title (optional)",
        message="Announcement text"
    )
    async def announce_schedule(self, interaction: discord.Interaction, when: str, message: str, repeat: str = "none",
                       interval_minutes: int = 0, title: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not self._is_mod(interaction.user):
            return await interaction.response.send_message(embed=style_isla_embed("Not for you.\n᲼᲼", title="Announce"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        run_ts = parse_when_to_ts(when)
        if run_ts <= now_ts():
            return await interaction.followup.send(embed=style_isla_embed("Bad time.\n᲼᲼", title="Announce"), ephemeral=True)
        rep = repeat.lower().strip()
        if rep not in ("none", "hourly", "daily", "weekly"):
            rep = "none"
        interval_minutes = max(0, int(interval_minutes or 0))
        await self.bot.db.execute(
            """
            INSERT INTO announce_jobs(guild_id,channel_id,message,embed_title,repeat_rule,interval_minutes,next_run_ts,created_ts,created_by,active)
            VALUES(?,?,?,?,?,?,?,?,?,1)
            """,
            (interaction.guild_id, interaction.channel_id, message, title or "", rep, interval_minutes, run_ts, now_ts(), interaction.user.id)
        )
        e = style_isla_embed(
            f"Scheduled.\n\nRuns: {human_eta(run_ts)}\nRepeat: **{rep}**\n᲼᲼",
            title="Announce"
        )
        await interaction.followup.send(embed=e, ephemeral=True)
    
    @app_commands.command(name="remind", description="Personal reminder.")
    @app_commands.describe(when="in 10m / 2h / YYYY-MM-DD HH:MM (UK)", message="Reminder text")
    async def remind(self, interaction: discord.Interaction, when: str, message: str):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        ts = parse_when_to_ts(when)
        if ts <= now_ts():
            return await interaction.followup.send(embed=style_isla_embed("Bad time.\n᲼᲼", title="Reminder"), ephemeral=True)
        await self.bot.db.execute(
            """
            INSERT INTO personal_reminders(guild_id,user_id,message,run_ts,created_ts,active)
            VALUES(?,?,?,?,?,1)
            """,
            (interaction.guild_id, interaction.user.id, message, ts, now_ts())
        )
        e = style_isla_embed(f"Fine.\n\nI'll remind you {human_eta(ts)}.\n᲼᲼", title="Reminder")
        await interaction.followup.send(embed=e, ephemeral=True)
    
    @tasks.loop(seconds=10)
    async def announce_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()
        rows = await self.bot.db.fetchall(
            """
            SELECT id,guild_id,channel_id,message,embed_title,repeat_rule,interval_minutes,next_run_ts
            FROM announce_jobs
            WHERE active=1 AND next_run_ts <= ?
            ORDER BY next_run_ts ASC
            LIMIT 5
            """,
            (now,)
        )
        for r in rows:
            gid = int(r["guild_id"])
            ch_id = int(r["channel_id"])
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            ch = guild.get_channel(ch_id)
            if not isinstance(ch, discord.TextChannel):
                continue
            await ch.send(embed=style_isla_embed(str(r["message"]) + "\n᲼᲼", title=(str(r["embed_title"]) or "Announcement")))
            rep = str(r["repeat_rule"])
            nxt = 0
            if rep == "hourly":
                mins = int(r["interval_minutes"] or 60)
                mins = 60 if mins <= 0 else mins
                nxt = now + mins * 60
            elif rep == "daily":
                nxt = now + 86400
            elif rep == "weekly":
                nxt = now + 7 * 86400
            if nxt > 0:
                await self.bot.db.execute("UPDATE announce_jobs SET next_run_ts=? WHERE id=?", (nxt, int(r["id"])))
            else:
                await self.bot.db.execute("UPDATE announce_jobs SET active=0 WHERE id=?", (int(r["id"]),))
    
    @announce_loop.before_loop
    async def before_announce_loop(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(seconds=10)
    async def remind_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()
        rows = await self.bot.db.fetchall(
            """
            SELECT id,guild_id,user_id,message
            FROM personal_reminders
            WHERE active=1 AND run_ts <= ?
            ORDER BY run_ts ASC
            LIMIT 10
            """,
            (now,)
        )
        for r in rows:
            gid = int(r["guild_id"])
            uid = int(r["user_id"])
            msg = str(r["message"])
            guild = self.bot.get_guild(gid)
            if guild:
                member = guild.get_member(uid)
                if member:
                    try:
                        embed = create_embed(msg + "\n᲼᲼", title="Reminder", color="info", is_dm=True, is_system=False)
                        await member.send(embed=embed)
                    except Exception:
                        pass
            await self.bot.db.execute("UPDATE personal_reminders SET active=0 WHERE id=?", (int(r["id"]),))
    
    @remind_loop.before_loop
    async def before_remind_loop(self):
        await self.bot.wait_until_ready()
    
    # ========================================================================
    # CASINO DAILY RECAP (from casino_daily_recap.py)
    # ========================================================================
    
    async def _ensure_settings(self, gid: int):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id, collars_role_enabled, collars_role_prefix, log_channel_id) VALUES(?,?,?,?)",
            (gid, 0, "Collar", int(self.bot.cfg.get('channels', 'logs', default=0) or 0))
        )
        try:
            await self.bot.db.execute("ALTER TABLE guild_settings ADD COLUMN casino_recap_last_ts INTEGER NOT NULL DEFAULT 0;")
        except Exception:
            pass
    
    async def _get_last_recap_ts(self, gid: int) -> int:
        row = await self.bot.db.fetchone("SELECT casino_recap_last_ts FROM guild_settings WHERE guild_id=?", (gid,))
        if not row:
            return 0
        return int(row["casino_recap_last_ts"] or 0)
    
    async def _set_last_recap_ts(self, gid: int, ts: int):
        await self.bot.db.execute("UPDATE guild_settings SET casino_recap_last_ts=? WHERE guild_id=?", (int(ts), gid))
    
    def _high_activity(self, summary: dict) -> bool:
        min_total_wagered = int(self.bot.cfg.get("casino_recap", "min_total_wagered", default=25000))
        min_rounds = int(self.bot.cfg.get("casino_recap", "min_rounds", default=120))
        min_unique_players = int(self.bot.cfg.get("casino_recap", "min_unique_players", default=25))
        return (
            int(summary["total_wagered"]) >= min_total_wagered
            or int(summary["rounds"]) >= min_rounds
            or int(summary["unique_users"]) >= min_unique_players
        )
    
    def _line(self) -> tuple[str, str]:
        openers = ["I looked at the casino today.", "I checked the tables.", "I read the casino logs."]
        closers = ["If you want to be noticed tomorrow, you know what to do.", "Try harder tomorrow.", "I'll be watching again."]
        return random.choice(openers), random.choice(closers)
    
    async def _post_recap(self, guild: discord.Guild, summary: dict, since_ts: int):
        spotlight_id = int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)
        ch = guild.get_channel(spotlight_id) if spotlight_id else None
        if not isinstance(ch, discord.TextChannel):
            return
        featured = set()
        for uid, _w in (summary.get("top_spenders") or [])[:3]:
            featured.add(int(uid))
        bw = summary.get("biggest_wager")
        if bw and bw.get("uid"):
            featured.add(int(bw["uid"]))
        bnw = summary.get("biggest_net_win")
        if bnw and bnw.get("uid"):
            featured.add(int(bnw["uid"]))
        mp = (summary.get("most_played") or [])
        if mp:
            featured.add(int(mp[0][0]))
        pings = " ".join([f"||<@{uid}>||" for uid in list(featured)[:10]])
        opener, closer = self._line()
        total_wagered = int(summary["total_wagered"])
        rounds = int(summary["rounds"])
        uniq = int(summary["unique_users"])
        lines = []
        lines.append(f"{opener}\n")
        lines.append(f"Last 24h: **{fmt(total_wagered)} Coins wagered**")
        lines.append(f"Rounds: **{fmt(rounds)}**")
        lines.append(f"Players: **{fmt(uniq)}**\n")
        spenders = summary.get("top_spenders") or []
        if spenders:
            lines.append("**Top spenders**")
            for i, (uid, w) in enumerate(spenders[:3], start=1):
                lines.append(f"**#{i}** <@{int(uid)}> — **{fmt(int(w))} Coins**")
            lines.append("")
        if bw:
            lines.append("**Biggest wager**")
            lines.append(f"<@{int(bw['uid'])}> — **{fmt(int(bw['wager']))} Coins** on **{bw['game']}**")
            lines.append("")
        if bnw:
            lines.append("**Biggest win**")
            lines.append(f"<@{int(bnw['uid'])}> — **+{fmt(int(bnw['net']))} Coins** on **{bnw['game']}**")
            lines.append("")
        if mp:
            uid, cnt = mp[0]
            lines.append("**Most games played**")
            lines.append(f"<@{int(uid)}> — **{fmt(int(cnt))} rounds**")
            lines.append("")
        lines.append(closer)
        lines.append("᲼᲼")
        embed = create_embed(
            description=sanitize_isla_text("\n".join(lines)),
            color="casino",
            thumbnail=random.choice(CASINO_THUMBS),
            is_dm=False,
            is_system=True
        )
        await ch.send(content=pings, embed=embed)
    
    @tasks.loop(time=time(hour=21, minute=15, tzinfo=UK_TZ))
    async def casino_recap_loop(self):
        await self.bot.wait_until_ready()
        casino = self.bot.get_cog("CasinoCore")
        if not casino or not hasattr(casino, "get_window_summary"):
            return
        for guild in self.bot.guilds:
            try:
                await self._ensure_settings(guild.id)
                last_ts = await self._get_last_recap_ts(guild.id)
                if last_ts and (now_ts() - last_ts) < 20 * 3600:
                    continue
                since_ts = now_ts() - 24 * 3600
                summary = await casino.get_window_summary(guild.id, since_ts)
                if not self._high_activity(summary):
                    continue
                await self._post_recap(guild, summary, since_ts)
                await self._set_last_recap_ts(guild.id, now_ts())
            except Exception:
                continue
    
    @casino_recap_loop.before_loop
    async def before_casino_recap_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    bot.tree.remove_command("announce", guild=None)
    bot.tree.remove_command("remind", guild=None)
    bot.tree.remove_command("spotlight", guild=None)
    cog = Announcements(bot)
    try:
        await bot.add_cog(cog)
    except Exception as e:
        if "CommandAlreadyRegistered" in str(e):
            bot.tree.remove_command("announce", guild=None)
            bot.tree.remove_command("remind", guild=None)
            bot.tree.remove_command("spotlight", guild=None)
            await bot.add_cog(cog)
        else:
            raise
    try:
        bot.tree.add_command(cog.announce, override=True)
        bot.tree.add_command(cog.remind, override=True)
        bot.tree.add_command(cog.spotlight, override=True)
    except Exception:
        pass

