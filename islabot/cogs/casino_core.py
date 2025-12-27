from __future__ import annotations

import json
import discord
from discord.ext import commands

from core.utils import now_ts


class CasinoCore(commands.Cog):
    """
    Core casino logging and memory system.
    Provides methods for other casino cogs to log rounds and retrieve highlights.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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


async def setup(bot: commands.Bot):
    await bot.add_cog(CasinoCore(bot))

