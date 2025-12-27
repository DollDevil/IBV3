from __future__ import annotations
import json
import random
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

import discord
from discord.ext import commands, tasks

from core.utils import now_ts, now_local
from core.isla_text import sanitize_isla_text

# Simple author+description embed only (no pings)
def simple_embed(desc: str, icon: str) -> discord.Embed:
    e = discord.Embed(description=desc)
    e.set_author(name="Isla", icon_url=icon)
    return e

def parse_window(s: str) -> Tuple[Tuple[int,int], Tuple[int,int]]:
    a,b = s.split("-")
    ah,am = [int(x) for x in a.split(":")]
    bh,bm = [int(x) for x in b.split(":")]
    return (ah,am), (bh,bm)

def mins(hm: Tuple[int,int]) -> int:
    return hm[0]*60 + hm[1]

def now_minute_of_day() -> int:
    t = now_local()
    return t.hour*60 + t.minute

def fmt(n: int) -> str:
    return f"{n:,}"

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

    # last time we checked casino recap window start
    last_presence_ts: int = 0

class DailyPresence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.thoughts = self._load_thoughts()
        self.icon = self.thoughts["meta"]["author_icon_default"]
        self.state: Dict[int, DailyState] = {}  # guild_id -> state
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    def _load_thoughts(self) -> dict:
        import os
        thoughts_path = self.bot.cfg.get("presence", "thoughts_path", default="data/isla_presence_thoughts.json")
        # Make path relative to islabot directory
        bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(bot_dir, thoughts_path)
        if not os.path.exists(path):
            # Return empty structure if file doesn't exist
            return {"meta": {"author_icon_default": ""}, "routing": {}, "thoughts": {}}
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
            # Mood-based selection (e.g., PHASE1_GREET)
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
        return msg.id

    async def _activity_since(self, channel: discord.TextChannel, since_ts: int) -> Tuple[int,int]:
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
        """
        Returns (total_voice_seconds, top_voice_uid) for [since_ts, now]
        using voice_events (precise).
        """
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
        # Replace with your actual obedience/WAS leaderboard query.
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

    # ---- Casino recap stats: total wagered + top spender within a time window ----
    async def _casino_window_stats(self, guild: discord.Guild, since_ts: int) -> Tuple[int, Optional[int]]:
        """
        Uses msg_memory JSON rounds logs:
        context: casino_rounds:{guild_id}:{week}
        Each round: {ts, uid, wager, ...}
        Returns (total_wagered, top_spender_uid)
        """
        gid = guild.id
        # Search recent weeks to cover midnight/weekly boundary (best-effort)
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

    # ---- Daily schedule: random start (12-15) and random sleep (00-03) ----
    def _pick_daily_times(self) -> Tuple[int,int]:
        (sh, sm), (eh, em) = parse_window(self.bot.cfg.get("presence", "morning_start_window", default="12:00-15:00"))
        start = random.randint(mins((sh,sm)), mins((eh,em)))
        (sh2, sm2), (eh2, em2) = parse_window(self.bot.cfg.get("presence", "sleep_window", default="00:00-03:00"))
        # sleep window crosses midnight often; treat as 0..180
        sleep = random.randint(mins((sh2,sm2)), mins((eh2,em2)))
        return start, sleep

    def _is_sleep_time(self, current_minute: int, sleep_minute: int) -> bool:
        # sleep_minute is in 00:00-03:00 range (0..180)
        return current_minute <= sleep_minute  # after midnight

    def _mood_for_day(self) -> str:
        # Simple: random drift weighted. You can later tie this to weekly mood engine.
        # Returns: "good", "bad", or "neutral"
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
        # base delay between "thoughts" while awake
        base = random.randint(6*60, 18*60)  # 6–18 min
        mult = self._pace_multiplier(mood)
        return int(base * mult)

    # ---- Silence chain: step timing ----
    def _silence_followup_delay(self, mood: str) -> int:
        # after she posts, if it stays quiet, she pokes again sooner
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

        # Step 0: greeting
        if st.chain_step == 0:
            st.last_orders_msg_id = await self._send(guild, "MORNING", self._pick("PHASE1_GREET", st.mood))
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            st.last_presence_ts = st.last_post_ts
            st.chain_step = 1
            return

        # Step 1: observe overnight vibe (activity + casino hint)
        if st.chain_step == 1:
            # Use last_presence_ts as window start; if not set, use 8–12h-ish
            since_ts = st.last_presence_ts or (now_ts() - random.randint(6*3600, 12*3600))

            # observe orders activity since last_presence
            msg_count, uniq = await self._activity_since(orders, since_ts)

            # observe casino stats since last_presence
            casino_total, _ = await self._casino_window_stats(guild, since_ts)

            # observe voice stats since last_presence
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

        # Step 2: reactive follow-up (reactions or silence)
        if st.chain_step == 2:
            reacts = await self._reaction_count(orders, st.last_orders_msg_id)
            msg_count, uniq = await self._activity_since(orders, st.last_post_ts - 12*60)  # last 12 min
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

        # Step 3: if casino was active, prompt recap + post stats in casino
        if st.chain_step == 3:
            since_ts = st.last_presence_ts or (now_ts() - random.randint(6*3600, 12*3600))
            casino_total, top_uid = await self._casino_window_stats(guild, since_ts)

            # Only do this branch if there was meaningful casino action
            if casino_total >= 2500:
                # prompt in orders, then stats in casino
                await self._send(guild, "CASINO_RECAP_PROMPT", self._pick("CASINO_RECAP_PROMPT"))

                # stats message (casino channel)
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

        # Step 4: leaderboard poke
        if st.chain_step == 4:
            await self._send(guild, "LEADERBOARD_PROMPT", self._pick("LEADERBOARD_PROMPT"))
            top_user = await self._get_top_user_mention(guild)
            line = self._pick("LEADERBOARD_REACT").replace("{top_user}", top_user)
            await self._send(guild, "LEADERBOARD_REACT", line)

            st.chain_step = 5
            st.last_post_ts = now_ts()
            st.last_chain_ts = st.last_post_ts
            return

        # Step 5: optional micro order if quiet
        if st.chain_step == 5:
            msg_count, uniq = await self._activity_since(orders, st.last_post_ts - 15*60)
            if msg_count < low_msg and uniq < low_uniq:
                await self._send(guild, "MICRO_ORDER", self._pick("MICRO_ORDER"))
            st.chain_step = 6
            st.last_post_ts = now_ts()
            return

    async def _awake_behavior_weights(self, st: DailyState) -> dict:
        """
        Behavior weights by mood.
        Neutral = most common.
        Good = more playful/interactive.
        Bad = more pressuring, still not spammy.
        """
        if st.mood == "good":
            return {
                "react_check": 0.18,
                "choose_topic": 0.14,
                "question_bait": 0.22,
                "casino_peek": 0.18,
                "leaderboard_peek": 0.18,
                "mini_order": 0.10
            }
        if st.mood == "bad":
            return {
                "react_check": 0.20,
                "choose_topic": 0.08,
                "question_bait": 0.18,
                "casino_peek": 0.16,
                "leaderboard_peek": 0.20,
                "mini_order": 0.18
            }
        return {  # neutral
            "react_check": 0.14,
            "choose_topic": 0.10,
            "question_bait": 0.22,
            "casino_peek": 0.16,
            "leaderboard_peek": 0.18,
            "mini_order": 0.20
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
        # Orders channel: prompt -> check -> respond
        prompt = {
            "neutral": [
                "If you're here, react to this.\nI want to see a pulse.\n᲼᲼",
                "React if you're awake.\n᲼᲼"
            ],
            "good": [
                "React for me.\nLet me see who's paying attention.\n᲼᲼",
                "Tap a reaction.\nShow me you're here.\n᲼᲼"
            ],
            "bad": [
                "React.\nNow.\n᲼᲼",
                "If you're here, prove it.\nReact.\n᲼᲼"
            ]
        }[st.mood]

        msg_id = await self._send(guild, "MORNING", random.choice(prompt))
        if not msg_id:
            return

        # wait 2–4 minutes (scaled by mood) then check
        wait_sec = int(random.randint(120, 240) * self._pace_multiplier(st.mood))
        st.last_post_ts = now_ts()

        # store for followup
        st.last_orders_msg_id = msg_id
        st.last_chain_ts = now_ts()

    async def _do_question_bait(self, guild: discord.Guild, st: DailyState):
        prompts = {
            "neutral": [
                "Say something.\nWhat are you doing today?\n᲼᲼",
                "What's the plan today.\nOne message.\n᲼᲼",
                "Talk to me.\nWhat's your mood.\n᲼᲼"
            ],
            "good": [
                "Talk to me.\nWhat are you up to today.\nMake it interesting.\n᲼᲼",
                "Tell me what you're doing.\nI'm listening.\n᲼᲼",
                "Give me one detail about your day.\nI'll decide if it's cute.\n᲼᲼"
            ],
            "bad": [
                "Speak.\nWhat are you doing.\n᲼᲼",
                "I'm bored.\nSay something useful.\n᲼᲼",
                "Tell me what you did today.\nMake it worth reading.\n᲼᲼"
            ]
        }[st.mood]
        await self._send(guild, "MORNING", random.choice(prompts))

    async def _do_choose_topic(self, guild: discord.Guild, st: DailyState):
        # A simple "pick 1" post. Users react; Isla responds next post based on reactions count.
        topics = [
            ("💬", "chat"),
            ("🎰", "casino"),
            ("📈", "leaderboard")
        ]
        opener = {
            "neutral": "Pick something.\nReact.\n᲼᲼",
            "good": "Pick for me.\nI'll follow your lead.\n᲼᲼",
            "bad": "Choose.\nDon't waste my time.\n᲼᲼"
        }[st.mood]
        lines = [opener] + [f"{e} {name}" for e, name in topics]
        msg_id = await self._send(guild, "MORNING", "\n".join(lines))

        # Add reactions (best effort)
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
            # no casino action: a quick tease in orders
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

        # put the spender callout in casino channel (cleaner)
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
            "neutral": [
                "One message.\nThen you can lurk again.\n᲼᲼",
                "Say something.\nI want to see you.\n᲼᲼"
            ],
            "good": [
                "One message for me.\nMake it cute.\n᲼᲼",
                "Say something.\nI'm in the mood to read.\n᲼᲼"
            ],
            "bad": [
                "One message.\nNow.\n᲼᲼",
                "Speak.\nDon't make me wait.\n᲼᲼"
            ]
        }[st.mood]
        await self._send(guild, "MORNING", random.choice(orders))

    async def _maybe_spotlight(self, guild: discord.Guild, st: DailyState):
        # Hard daily cap for spotlight
        cap = int(self.bot.cfg.get("presence", "spotlight_posts_per_day_max", default=3))
        if st.spotlight_posts_sent >= cap:
            return

        # Lightweight: only occasionally, not chained
        if random.random() > 0.12:
            return

        await self._send(guild, "SPOTLIGHT_HIGHLIGHT", random.choice(self.thoughts["thoughts"]["SPOTLIGHT_HIGHLIGHT"]))
        st.spotlight_posts_sent += 1
        # count spotlight posts inside posts_sent as well (simple)
        st.posts_sent += 1

    async def _start_day_if_needed(self, guild: discord.Guild, st: DailyState):
        # pick times and mood once per day
        st.start_minute, st.sleep_minute = self._pick_daily_times()
        st.mood = self._mood_for_day()
        st.posts_sent = 0
        st.spotlight_posts_sent = 0
        st.chain_step = 0
        st.last_post_ts = 0
        st.last_presence_ts = now_ts() - random.randint(6*3600, 12*3600)  # so she can comment on "overnight"
        st.awake = False

    @tasks.loop(seconds=30)
    async def tick(self):
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

            # Wake up sometime 12:00–15:00
            if not st.awake and cur_min >= st.start_minute and cur_min < 24*60:
                st.awake = True

            # Sleep between 00:00–03:00 (after midnight)
            # If we've crossed midnight, cur_min is small (0..)
            if st.awake and cur_min <= st.sleep_minute:
                await self._send(guild, "SLEEP", self._pick("SLEEP"))
                st.awake = False
                continue

            if not st.awake:
                continue

            # Daily post budget (keeps it alive but not spammy)
            min_posts = int(self.bot.cfg.get("presence", "awake_posts_per_day_min", default=10))
            max_posts = int(self.bot.cfg.get("presence", "awake_posts_per_day_max", default=25))
            if st.posts_sent >= max_posts:
                continue

            # Morning routine chain runs first until completion
            now = now_ts()
            if st.chain_step < 6:
                # chain pacing: next step after 5–15m scaled by mood
                if st.last_chain_ts == 0 or (now - st.last_chain_ts) >= self._silence_followup_delay(st.mood):
                    await self._run_morning_chain(guild, st)
                    st.posts_sent += 1
                continue

            # After routine chain: occasional "alive updates" (pace by mood)
            delay = self._next_delay_sec(st.mood)

            # Ensure minimum posts happen on awake days
            if st.posts_sent < min_posts:
                delay = max(240, delay // 2)

            if st.last_post_ts and (now - st.last_post_ts) < delay:
                continue

            # After routine chain: interactive "alive updates"
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

    @tick.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(DailyPresence(bot))

