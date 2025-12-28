from __future__ import annotations

import json
import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts, fmt
from utils.helpers import isla_embed as helper_isla_embed
from utils.embed_utils import create_embed

def isla_embed(desc: str, icon: str) -> discord.Embed:
    return helper_isla_embed(desc, icon=icon)


DEFAULT_COLLARS_BASE = [
    ("collar_base_black", "Basic Collar Black", 150),
    ("collar_base_red", "Basic Collar Red", 250),
    ("collar_base_white", "Basic Collar White", 250),
    ("collar_base_blue", "Basic Collar Blue", 350),
    ("collar_base_pink", "Basic Collar Pink", 350),
    ("collar_base_green", "Basic Collar Green", 450),
    ("collar_base_purple", "Basic Collar Purple", 450),
]

DEFAULT_COLLARS_PREMIUM = [
    ("collar_premium_goldtrim", "Premium Collar Gold Trim", 7000),
    ("collar_premium_neon", "Premium Collar Neon", 12000),
    ("collar_premium_leather", "Premium Collar Leather", 15000),
]

DEFAULT_COLLARS_PRESTIGE = [
    ("collar_prestige_obsidian", "Prestige Collar Obsidian", 65000),
    ("collar_prestige_crowned", "Prestige Collar Crowned", 95000),
]

DEFAULT_LIMITED = [
    ("collar_limited_winter_silver", "Limited Winter Collar Silver", "limited", 18000, {"season": "winter"}),
    ("collar_limited_valentine_rose", "Limited Valentine Collar Rose", "limited", 22000, {"season": "valentine"})
]


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    async def _ensure_user(self, gid: int, uid: int):
        row = await self.bot.db.fetchone("SELECT user_id FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if not row:
            start = int(self.bot.cfg.get("economy", "start_balance", default=250))
            await self.bot.db.execute(
                "INSERT INTO users(guild_id,user_id,coins,obedience,xp,lce,last_active_ts) VALUES(?,?,?,?,?,?,?)",
                (gid, uid, start, 0, 0, 0, now_ts())
            )

    async def _get_coins(self, gid: int, uid: int) -> int:
        await self._ensure_user(gid, uid)
        row = await self.bot.db.fetchone("SELECT coins FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        return int(row["coins"]) if row else 0

    async def _set_coins(self, gid: int, uid: int, coins: int):
        await self.bot.db.execute("UPDATE users SET coins=? WHERE guild_id=? AND user_id=?", (coins, gid, uid))

    async def seed_default_shop(self, gid: int):
        # Base collars
        for item_id, name, price in DEFAULT_COLLARS_BASE:
            meta = {"color": item_id.split("_")[-1]}
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active)
                VALUES(?,?,?,?,?,?,?,1)
                """,
                (gid, item_id, name, "base", price, "collar", json.dumps(meta))
            )

        for item_id, name, price in DEFAULT_COLLARS_PREMIUM:
            meta = {"style": "premium"}
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active)
                VALUES(?,?,?,?,?,?,?,1)
                """,
                (gid, item_id, name, "premium", price, "collar", json.dumps(meta))
            )

        for item_id, name, price in DEFAULT_COLLARS_PRESTIGE:
            meta = {"style": "prestige"}
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active)
                VALUES(?,?,?,?,?,?,?,1)
                """,
                (gid, item_id, name, "prestige", price, "collar", json.dumps(meta))
            )

        for item_id, name, tier, price, meta in DEFAULT_LIMITED:
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active)
                VALUES(?,?,?,?,?,?,?,0)
                """,
                (gid, item_id, name, tier, int(price), "collar", json.dumps(meta))
            )

        # --- ALL-IN themed cosmetics (can be shop + unlock) ---
        allin_items = [
            ("badge_allin_mark", "Badge All-In Mark", "premium", 9000, "badge", {"style": "allin", "rarity": "premium"}),
            ("collar_allin_strap_black", "All-In Collar Black Strap", "premium", 14000, "collar", {"style": "allin", "color": "black"}),
            ("collar_allin_strap_red", "All-In Collar Red Strap", "premium", 16000, "collar", {"style": "allin", "color": "red"}),
            ("collar_allin_obsidian", "All-In Collar Obsidian", "prestige", 85000, "collar", {"style": "allin", "rarity": "prestige"}),
        ]
        for item_id, name, tier, price, slot, meta in allin_items:
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active)
                VALUES(?,?,?,?,?,?,?,1)
                """,
                (gid, item_id, name, tier, int(price), slot, json.dumps(meta))
            )

    @app_commands.command(name="collars_setup", description="(Admin) Seed default collar shop items and enable collar equips.")
    @app_commands.checks.has_permissions(administrator=True)
    async def collars_setup(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id

        await self.seed_default_shop(gid)
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id, collars_role_enabled, collars_role_prefix, log_channel_id) VALUES(?,?,?,?)",
            (gid, 0, "Collar", int(self.bot.cfg.get("channels", "logs", default=0) or 0))
        )

        desc = "Collar shop seeded.\nUse `/shop tier:base` to browse.\nUse `/buy item_id:...` then `/equip collar item_id:...`.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="shop", description="Browse the shop.")
    @app_commands.describe(tier="base|premium|prestige|limited")
    async def shop(self, interaction: discord.Interaction, tier: str = "base"):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        tier = tier.lower().strip()
        if tier not in ("base", "premium", "prestige", "limited"):
            tier = "base"

        rows = await self.bot.db.fetchall(
            "SELECT item_id,name,price,slot FROM shop_items WHERE guild_id=? AND tier=? AND active=1 ORDER BY price ASC LIMIT 25",
            (gid, tier)
        )
        if not rows:
            embed = create_embed("No items found for that tier.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = []
        for r in rows:
            lines.append(f"**{r['name']}** — `{r['item_id']}` — **{fmt(int(r['price']))} Coins**")
        desc = f"{interaction.user.mention}\n{tier.title()} Shop\n\n" + "\n".join(lines) + "\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="buy", description="Buy a shop item with Coins.")
    async def buy(self, interaction: discord.Interaction, item_id: str):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        await self._ensure_user(gid, uid)

        row = await self.bot.db.fetchone(
            "SELECT name,price,slot,active FROM shop_items WHERE guild_id=? AND item_id=?",
            (gid, item_id)
        )
        if not row or int(row["active"]) != 1:
            embed = create_embed("That item isn't available.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        price = int(row["price"])
        coins = await self._get_coins(gid, uid)
        if coins < price:
            embed = create_embed("Not enough Coins.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._set_coins(gid, uid, coins - price)
        await self.bot.db.execute(
            """
            INSERT INTO inventory(guild_id,user_id,item_id,qty,acquired_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(guild_id,user_id,item_id)
            DO UPDATE SET qty = qty + 1
            """,
            (gid, uid, item_id, 1, now_ts())
        )

        desc = f"{interaction.user.mention}\nPurchased **{row['name']}** for **{fmt(price)} Coins**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="inventory", description="View your inventory.")
    async def inventory(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id

        rows = await self.bot.db.fetchall(
            "SELECT item_id, qty FROM inventory WHERE guild_id=? AND user_id=? ORDER BY acquired_ts DESC LIMIT 50",
            (gid, uid)
        )
        if not rows:
            embed = create_embed("Inventory is empty.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = [f"`{r['item_id']}` x{int(r['qty'])}" for r in rows]
        desc = f"{interaction.user.mention}\nInventory\n\n" + "\n".join(lines) + "\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)

    @app_commands.command(name="equip", description="Equip an item you own (e.g., collar).")
    @app_commands.describe(slot="collar", item_id="Item ID from your inventory")
    async def equip(self, interaction: discord.Interaction, slot: str, item_id: str):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        gid = interaction.guild_id
        uid = interaction.user.id
        slot = slot.lower().strip()
        if slot not in ("collar", "badge"):
            embed = create_embed("Unsupported slot.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv = await self.bot.db.fetchone(
            "SELECT qty FROM inventory WHERE guild_id=? AND user_id=? AND item_id=?",
            (gid, uid, item_id)
        )
        if not inv or int(inv["qty"]) <= 0:
            embed = create_embed("You don't own that item.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await self.bot.db.execute(
            """
            INSERT INTO equips(guild_id,user_id,slot,item_id,equipped_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(guild_id,user_id,slot)
            DO UPDATE SET item_id=excluded.item_id, equipped_ts=excluded.equipped_ts
            """,
            (gid, uid, slot, item_id, now_ts())
        )

        desc = f"{interaction.user.mention}\nEquipped `{item_id}` in **{slot}**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
