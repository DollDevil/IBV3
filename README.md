# IslaBot V3

A professional-grade Discord bot with personality, economy, events, and interactive features.

## Features

- **Economy System**: Coins, ledger, daily claims, payments
- **Progression System**: Ranks, WAS (Weekly Activity Score), weekly bonuses
- **Casino Games**: Coin flip, dice, slots, roulette, blackjack, crash
- **Order System**: Dynamic orders, rituals, streaks, personal tasks
- **Event System**: Seasonal events, holiday weeks, boss fights, quests
- **Quarterly Tax**: Predictable 10% tax every 4 months
- **User Controls**: Vacation mode, safeword, opt-out
- **Onboarding**: Interactive welcome system with pronoun selection
- **Presence System**: Daily automated posts with mood-based interactions
- **Shop System**: Cosmetics, collars, badges, limited items
- **Voice Tracking**: Activity tracking for events and stats

## Requirements

- Python 3.10+
- discord.py 2.4.0+
- aiosqlite 0.20.0+
- PyYAML 6.0.2+

## Setup

1. Install dependencies:
   ```bash
   pip install -r islabot/requirements.txt
   ```

2. Copy and configure `config.yml`:
   ```yaml
   token: "YOUR_BOT_TOKEN"
   guilds:
     - YOUR_GUILD_ID
   channels:
     orders: CHANNEL_ID
     spotlight: CHANNEL_ID
     casino: CHANNEL_ID
     spam: CHANNEL_ID
     # ... other channels
   ```

3. Run the bot:
   ```bash
   python -m islabot.bot
   ```

## Configuration

See `config.yml` for all configuration options including:
- Guild and channel IDs
- Economy settings
- Presence/post scheduling
- Order settings
- Casino configuration

## Database

The bot uses SQLite (`islabot.sqlite3`). The database schema is automatically created and migrated on first run.

## Hosting (Wispbyte Ready)

This bot is configured for Wispbyte hosting:
- All dependencies in `requirements.txt`
- Database path is relative (works with Wispbyte's file system)
- No hardcoded paths
- Proper error handling for production

## Structure

```
islabot/
├── bot.py              # Main entry point
├── config.yml          # Configuration (copy from template)
├── cogs/               # Bot cogs/commands
├── core/               # Core utilities (db, config, utils)
├── utils/              # Helper utilities
└── data/               # JSON data files
```

## License

Private - All rights reserved

