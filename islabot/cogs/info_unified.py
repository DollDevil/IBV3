from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
from utils.info_embed import info_embed
from utils.embed_utils import create_embed

# Keep the titles short and the descriptions clear.
INFO_TOPICS: dict[str, dict] = {
    "islabot": {
        "title": "IslaBot",
        "desc": (
            "Hey.\n\n"
            "IslaBot runs the server economy, quests, orders, and casino.\n"
            "It also tracks activity and ranks.\n\n"
            "Core commands:\n"
            "• `/start`\n"
            "• `/profile`\n"
            "• `/daily`\n"
            "• `/quests`\n"
            "• `/order_personal`\n"
            "• `/casino`\n\n"
            "Control commands:\n"
            "• `/safeword` (neutral tone)\n"
            "• `/vacation` (pause penalties)\n"
            "• `/opt-out` (reset + exclude)\n"
            "᲼᲼"
        ),
    },
    "casino": {
        "title": "Casino",
        "desc": (
            "Casino uses Coins.\n\n"
            "Games:\n"
            "• Blackjack\n"
            "• Roulette\n"
            "• Dice\n"
            "• Slots\n\n"
            "Main commands:\n"
            "• `/casino` (overview)\n"
            "• `/casino_stats`\n\n"
            "Game commands:\n"
            "• `/blackjack` • `/roulette` • `/dice` • `/slots`\n\n"
            "Notes:\n"
            "• Big wins can trigger a DM (max once/day)\n"
            "• Jackpots / 10,000+ wins may show in Spotlight\n"
            "᲼᲼"
        ),
    },
    "blackjack": {
        "title": "Blackjack",
        "desc": (
            "Goal: get close to 21 without going over.\n\n"
            "Commands:\n"
            "• `/blackjack <bet>`\n"
            "• `/blackjack_hit`\n"
            "• `/blackjack_stand`\n"
            "• `/blackjack_allin`\n\n"
            "Notes:\n"
            "• Bust = loss\n"
            "• Blackjack pays higher (if enabled)\n"
            "᲼᲼"
        ),
    },
    "roulette": {
        "title": "Roulette",
        "desc": (
            "Bet on outcomes, then spin.\n\n"
            "Commands:\n"
            "• `/roulette <bet> <choice>`\n"
            "• `/roulette_allin <choice>`\n\n"
            "Common choices:\n"
            "• `red` / `black`\n"
            "• `0–36` (if number bets enabled)\n"
            "᲼᲼"
        ),
    },
    "dice": {
        "title": "Dice",
        "desc": (
            "Roll a number and resolve payouts based on thresholds.\n\n"
            "Commands:\n"
            "• `/dice <bet>`\n"
            "• `/dice_allin`\n\n"
            "Notes:\n"
            "• Higher rolls pay more\n"
            "• Low rolls lose the wager\n"
            "᲼᲼"
        ),
    },
    "slots": {
        "title": "Slots",
        "desc": (
            "Spin reels for symbol matches.\n\n"
            "Commands:\n"
            "• `/slots <bet>`\n"
            "• `/slots_allin`\n\n"
            "Notes:\n"
            "• Small wins happen often\n"
            "• Big wins are rarer and may trigger DMs/Spotlight\n"
            "᲼᲼"
        ),
    },
    "orders": {
        "title": "Orders",
        "desc": (
            "Orders are timed tasks with rewards.\n\n"
            "Commands:\n"
            "• `/orders` (board)\n"
            "• `/order_accept <id>`\n"
            "• `/order_progress <id>`\n"
            "• `/order_complete <id>`\n\n"
            "Notes:\n"
            "• Vacation: private orders don't appear\n"
            "• Vacation: public orders don't count\n"
            "᲼᲼"
        ),
    },
    "quests": {
        "title": "Quests",
        "desc": (
            "Quests are structured goals (daily/weekly/elite).\n\n"
            "Commands:\n"
            "• `/quests [tier]`\n"
            "• `/quest_progress <id>`\n"
            "• `/quest_claim <id>`\n"
            "• `/quest_reroll`\n\n"
            "Rewards:\n"
            "• Coins / Obedience / Event Tokens\n"
            "᲼᲼"
        ),
    },
    "vacation": {
        "title": "Vacation",
        "desc": (
            "Vacation pauses penalties.\n\n"
            "Rules:\n"
            "• Min: 3 days\n"
            "• Max: 30 days\n"
            "• Cooldown: 24h after ending (natural or `/vacationstop`)\n\n"
            "Effects:\n"
            "• Tax won't accrue\n"
            "• Failure penalties won't trigger\n"
            "• Private orders/tasks won't appear\n"
            "• Public orders don't count\n\n"
            "Commands:\n"
            "• `/vacation <days>`\n"
            "• `/vacationstop`\n"
            "᲼᲼"
        ),
    },
    "safeword": {
        "title": "Safeword",
        "desc": (
            "Safeword switches Isla's tone to neutral for you.\n\n"
            "You still have access to:\n"
            "• coins, quests, orders, casino, profile\n\n"
            "Neutral means:\n"
            "• no degrading language\n"
            "• no flirt escalation\n"
            "• no targeted callouts\n\n"
            "Commands:\n"
            "• `/safeword` (toggle)\n"
            "• `/safeword_status`\n"
            "᲼᲼"
        ),
    },
    "optout": {
        "title": "Opt-Out",
        "desc": (
            "Opt-out removes you from IslaBot systems.\n\n"
            "What it does:\n"
            "• Stops earning coins/obedience\n"
            "• Removes tracking/leaderboards\n"
            "• Resets your progress\n\n"
            "Commands:\n"
            "• `/opt-out`\n"
            "• `/opt-out_confirm <token>`\n"
            "• `/opt-in`\n"
            "᲼᲼"
        ),
    },
}

TOPIC_CHOICES = [
    app_commands.Choice(name="IslaBot Overview", value="islabot"),
    app_commands.Choice(name="Casino (Overview)", value="casino"),
    app_commands.Choice(name="Casino: Blackjack", value="blackjack"),
    app_commands.Choice(name="Casino: Roulette", value="roulette"),
    app_commands.Choice(name="Casino: Dice", value="dice"),
    app_commands.Choice(name="Casino: Slots", value="slots"),
    app_commands.Choice(name="Orders", value="orders"),
    app_commands.Choice(name="Quests", value="quests"),
    app_commands.Choice(name="Vacation", value="vacation"),
    app_commands.Choice(name="Safeword", value="safeword"),
    app_commands.Choice(name="Opt-Out", value="optout"),
]


class UnifiedInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="Show info about IslaBot features.")
    @app_commands.choices(topic=TOPIC_CHOICES)
    async def info(self, interaction: discord.Interaction, topic: app_commands.Choice[str]):
        key = topic.value
        data = INFO_TOPICS.get(key) or INFO_TOPICS["islabot"]
        e = info_embed(data["title"], data["desc"])
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(UnifiedInfo(bot))

