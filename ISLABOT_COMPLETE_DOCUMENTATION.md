# IslaBot V3 - Complete Feature & Command Documentation

## Overview
IslaBot is a comprehensive Discord bot that manages economy, orders, events, casino games, moderation, user progression, and community engagement. The bot features a strict "boss/manager" persona with PG-13 content, consent-based interactions, and extensive tracking systems.

---

## Core Systems & Features

### 1. Economy System
- **Coins**: Primary currency used throughout the bot
- **Daily Claims**: Users can claim daily coins (streak-based bonuses)
- **Weekly Payouts**: Weekly bonuses for active participation
- **Peer Transfers**: Users can send coins to each other (with daily limits)
- **Tax System**: Inactivity tax that accumulates debt over time
- **Transaction Ledger**: Complete history of all coin transactions
- **Wallet System**: Structured wallet with coins, tax debt, and timestamps

### 2. Orders System
- **Order Catalog**: Available orders for users to accept
- **Order Types**: Hourly, daily, event-specific, personal orders
- **Acceptance System**: Users accept orders with deadlines
- **Completion Tracking**: Proof submission and validation
- **Penalties**: Auto-penalties for missed deadlines
- **Streaks**: Obedience streaks unlock bonuses (daily claims, forgiveness tokens)
- **Micro-Orders**: Quick instant orders (`/obey`, `/kneel`)
- **Begging System**: Users can beg for mercy (costs coins)
- **Forgiveness**: Purchase forgiveness or earn via streaks

### 3. Event System
- **Seasonal Events**: Spring, Summer, Autumn, Winter themes
- **Holiday Events**: Special holiday-themed events
- **Boss Fights**: Community fights against event bosses
- **Boss HP System**: Boss HP decreases based on community activity
- **Damage Points (DP)**: Calculated from messages, voice, casino, tokens, rituals
- **Event Tokens**: Currency earned during events
- **Event Shops**: Token-based shops during events
- **Rituals**: Daily event activities
- **Quests**: Daily, weekly, and elite quests during events
- **Milestones**: Boss HP milestones trigger announcements
- **Leaderboards**: Event contribution leaderboards

### 4. Casino System
- **Games Available**: Blackjack, Roulette, Dice, Slots
- **Wagering**: All games use coins as currency
- **Big Win Detection**: Large wins trigger special DMs
- **Casino Royalty**: Top wagerers receive special roles
- **Daily Recap**: Daily summaries of casino activity
- **Statistics Tracking**: Detailed casino stats per user
- **Damage Integration**: Casino activity contributes to event boss damage

### 5. Voice & Activity Tracking
- **Voice Minutes**: Tracks time spent in voice channels
- **Reduced Multiplier**: After 1 hour without messages, voice damage is reduced
- **Message Counting**: Counts messages (5-second cooldown, excludes spam channel)
- **Activity Flushing**: Periodic writes to database
- **Voice Refresh**: Sending messages restores full voice damage strength

### 6. Discipline & Moderation
- **Warnings**: Admin can warn users
- **Strikes**: Strike system with auto-escalation
- **Timeouts**: Discord timeouts with optional coin seizure
- **Mutes**: Role-based muting with auto-expiration
- **Nickname Enforcement**: Temporary enforced nicknames
- **Coin Seizure**: Remove coins as punishment
- **Fines**: Add debt instead of removing coins
- **Debt System**: Track punishment debt
- **Penance Tasks**: Generate tasks to work off debt
- **Pardons**: Clear punishments/strikes
- **Auto-Expiration**: Punishments expire automatically

### 7. User Progression
- **XP System**: Experience points tracked
- **Stage System**: Progression stages (0-4) affecting bot tone
- **Favor System**: Favor stages with different interactions
- **Ranks**: Rank titles based on progression (Stray, Worthless Pup, Leashed Pup, etc.)
- **LCE (Lifetime Coin Earnings)**: Track total coins earned
- **Activity Tracking**: Daily activity counters (messages, commands, coins, orders)

### 8. Shop & Inventory
- **Shop Tiers**: Base, Premium, Prestige, Limited items
- **Item Categories**: Attention, mercy, buffs, cosmetics, collars
- **Inventory System**: User-owned items
- **Collar System**: Equippable collar items with roles
- **Perks**: Purchaseable perks (attention, mercy uses, buffs)

### 9. Privacy & Controls
- **Opt-Out System**: Users can hard-delete all data and stop tracking
- **Opt-In System**: Re-join after opting out
- **Safeword**: Switch bot to neutral tone (no degrading language)
- **Vacation Mode**: Pause penalties temporarily
- **Consent System**: Granular consent for orders, DMs, humiliation, callouts
- **18+ Verification**: Age verification requirement
- **Audit Logging**: Complete audit trail of all actions

### 10. Configuration & Admin
- **Feature Flags**: Enable/disable modules per guild/channel
- **Channel Config**: Per-channel key-value configuration
- **Guild Config**: Server-wide settings (roles, channels, economy, orders, moderation)
- **Personality Hot-Reload**: Reload personality/tone responses without restart
- **Admin Tools**: Comprehensive admin command suite
- **Staff Notes**: Private admin notes on users
- **User Profiles**: Deep admin views of user data

### 11. Custom Events (Calendar)
- **Event Creation**: Create custom server events with modals
- **Event Participation**: Join/leave events
- **Entry Costs**: Optional coin entry fees
- **Event Roles**: Automatic role assignment
- **Event Scheduling**: Future-dated events

### 12. Announcements & Reminders
- **Immediate Announcements**: Send announcements right away
- **Scheduled Announcements**: Schedule announcements with repeats (hourly/daily/weekly)
- **Personal Reminders**: Users can set personal reminders
- **Background Loops**: Automatic execution of scheduled tasks

### 13. Context Menu Commands (Right-Click Apps)
- **Praise**: Mod-only public praise messages
- **Humiliate**: Mod-only public correction (requires consent)
- **Add Note**: Mod-only staff note addition
- **Coin Tip**: Any user can tip coins to others

---

## All Commands

### Core Commands (`/core_commands`)
- **`/commands [category]`** - Show commands organized by category
- **`/about`** - Learn about Isla and how the system works
- **`/ping`** - Bot latency, shard info, and uptime
- **`/status`** - View active modules and event status (public-safe)

### Economy Commands (`/coins_group`)
- **`/coins balance`** - View your coin balance, tax debt, and pending deductions
- **`/coins daily`** - Claim daily coins (streak-based bonuses)
- **`/coins weekly`** - Claim weekly payout bonus
- **`/coins pay <user> <amount>`** - Send coins to another user (daily limit: 500)
- **`/coins top [period]`** - Leaderboard by day/week/all-time
- **`/coins shop`** - View purchasable perks
- **`/coins buy <perk>`** - Purchase a perk
- **`/coins burn <amount>`** - Sacrifice coins for attention
- **`/coins tax status`** - View inactivity tax rules and next tick
- **`/coins history [user]`** - View transaction history

### Orders Commands (`/orders_group`)
- **`/orders view`** - View available orders
- **`/orders accept <order_id>`** - Accept an order (starts timer)
- **`/orders complete <order_id> [proof]`** - Complete an order with optional proof
- **`/orders forfeit <order_id>`** - Forfeit an order (penalty)
- **`/orders streak`** - View your obedience streak and bonuses
- **`/obey`** - Instant micro-order (quick task)
- **`/kneel`** - Small commitment task with minor coin changes
- **`/beg [reason]`** - Request mercy (costs coins; may reduce punishment)
- **`/forgive`** - Purchase forgiveness or use earned forgiveness token

### Discipline Commands (`/discipline_group`)
**User-Facing:**
- **`/punishments`** - View your active punishments, duration, and conditions to clear
- **`/debt`** - View debt/penalties owed
- **`/penance`** - Generate a penance task to work off debt

**Moderator-Facing:**
- **`/discipline warn <user> [reason]`** - Warn a user (logged)
- **`/discipline strike <user> <count> [reason]`** - Add strikes (auto-escalation)
- **`/discipline timeout <user> <duration> [reason] [seize_coins]`** - Timeout user + optional coin seizure
- **`/discipline mute <user> <duration> [reason]`** - Mute user via role
- **`/discipline nickname <user> <nickname> <duration>`** - Enforce temporary nickname
- **`/discipline seize <user> <amount> [reason]`** - Remove coins as punishment
- **`/discipline fine <user> <amount> [reason]`** - Add debt instead of removing coins
- **`/discipline pardon <user> [what]`** - Clear punishments/strikes

### Event Commands (`/events`)
- **`/event`** - View current active season/holiday, boss fight, and questboard
- **`/event_boss`** - View current event boss status
- **`/boss_leaderboard`** - Top contributors for current boss fight
- **`/event_progress`** - Your personal progress in active boss/event
- **`/event_claim`** - Claim unlocked event milestone rewards
- **`/tokens`** - View your current event token balance
- **`/season`** - View current season/holiday wrapper
- **`/season_shop`** - View season shop (token store)
- **`/quests`** - View quests (daily/weekly/elite)
- **`/quest_progress <quest_id>`** - Check your progress on a quest
- **`/quest_claim <quest_id>`** - Claim quest reward if complete
- **`/quest_reroll <quest_id>`** - Reroll one daily quest (costs tokens or coins)

**Event Group Subcommands (`/event` group):**
- **`/event info`** - View current event info
- **`/event boss`** - View current event boss
- **`/event progress`** - View boss progress and your contribution today
- **`/event leaderboard`** - View event leaderboards
- **`/event ritual`** - View today's ritual info
- **`/event shop`** - View event shop info

**Staff Event Commands:**
- **`/event_start_holiday <name> <token_name>`** - Manually start a holiday week event
- **`/event_start_season <season> <token_name>`** - Start seasonal event
- **`/event_start_boss <boss_name> <hp_max> <token_name>`** - Start boss fight event

### Custom Events Commands (`/custom_events_group`)
- **`/event create`** - Interactive event wizard (creates custom calendar event)
- **`/event list`** - View upcoming custom events
- **`/event join <event_id>`** - Join event and get role (pays entry cost if set)
- **`/event leave <event_id>`** - Leave a custom event

### Casino Commands (`/casino_games`)
- **`/casino`** - Casino overview and stats
- **`/casino_stats`** - Detailed casino statistics
- **`/blackjack <bet>`** - Play blackjack
- **`/roulette <bet_type> <amount>`** - Play roulette (number, color, even/odd)
- **`/dice <bet> <target>`** - Roll dice (target 2-6)
- **`/slots <bet>`** - Play slots

### Shop Commands (`/shop`)
- **`/shop [tier]`** - Browse shop (base/premium/prestige/limited)
- **`/buy <item_id>`** - Buy a shop item with coins
- **`/inventory`** - View your inventory
- **`/equip <item_id>`** - Equip an item (if equippable)
- **`/collars_setup`** - (Admin) Seed default collar shop items

### Profile Commands (`/profile`)
- **`/profile [user]`** - View user profile (coins, stage, rank, stats)
- **`/start`** - Begin your journey with Isla

### Privacy Commands (`/privacy`)
- **`/optout`** - Hard leave Isla system (deletes data, stops tracking)
- **`/optin`** - Re-join Isla system after opting out

### Safeword Commands (`/safeword`)
- **`/safeword`** - Toggle safeword (switch to neutral tone)
- **`/safeword_status`** - Check safeword status

### Vacation Commands (`/vacation_watch`)
- **`/vacation`** - Request vacation mode (pause penalties)

### Consent Commands (`/consent`)
- **`/verify`** - 18+ verification and consent setup
- **`/consent`** - Update consent preferences

### Tributes Commands (`/tributes`)
- **`/tribute <amount> [note]`** - Log a symbolic tribute (no payment processing)

### Moderation Commands (`/moderation`)
- **`/purge <count>`** - Delete messages from channel
- **`/slowmode <seconds>`** - Set slowmode for channel
- **`/lockdown`** - Toggle lockdown (disable sending messages)
- **`/dev_reload_personality`** - (Admin) Reload personality.json

### Admin Tools Commands (`/admin_tools`)
**Feature Management:**
- **`/feature_list`** - (Mod) List feature flags (available modules)
- **`/feature_set <feature> <enabled>`** - (Admin) Enable/disable feature at guild level
- **`/feature_set_channel <feature> <channel> <enabled>`** - (Admin) Enable/disable feature in channel

**Channel Config:**
- **`/channelcfg_set <channel> <key> <value>`** - (Admin) Set channel config key=value
- **`/channelcfg_get <channel> <key>`** - (Mod) Get channel config key
- **`/channelcfg_del <channel> <key>`** - (Admin) Delete channel config key

**User Notes & Discipline:**
- **`/note_set <user> <note>`** - (Mod) Set private admin note on user
- **`/note_view <user>`** - (Mod) View admin note on user
- **`/discipline_add <user> <kind> <points> [reason]`** - (Mod) Add warning/discipline entry
- **`/discipline_view <user> [limit]`** - (Mod) View discipline totals + entries

**User Management:**
- **`/admin_profile <user>`** - (Mod) Deep view of user's Isla profile + activity
- **`/user_optout <user> [reason]`** - (Admin) Force-opt-out user
- **`/user_optin <user> [reason]`** - (Admin) Re-enable tracking for opted-out user
- **`/user_safeword <user> <minutes> [reason]`** - (Admin) Force safeword on user
- **`/user_unsafeword <user> [reason]`** - (Admin) Clear user's safeword
- **`/user_status <user>`** - (Mod) View Isla status (opt-out + safeword + stats)

### Configuration Commands (`/config_group`)
- **`/config roles`** - Wizard to set role IDs (18+, consent, muted, punishment, ranks)
- **`/config channels`** - Wizard to set channel IDs (logs, announcements, orders, intros, spam)
- **`/config economy`** - Wizard to set economy rules (daily amount, streak, limits, tax)
- **`/config orders`** - Wizard to set order rules (frequency, types, windows, penalties, rewards)
- **`/config moderation`** - Wizard to set moderation rules (filters, antispam, escalation, raid mode)

### Announcement Commands (`/announce_and_remind`)
- **`/announce send <message> [title]`** - Immediate announcement
- **`/announce schedule <when> <message> <repeat> [interval_minutes] [title]`** - Schedule announcement with repeats
- **`/remind <when> <message>`** - Set personal reminder

### Duel Commands (`/duel_cog`)
- **`/duel <user> <amount>`** - Challenge user to duel (both stake coins, minigame determines winner)

### Info Commands (`/info_unified`)
- **`/info <topic>`** - Show info about IslaBot features (islabot, casino, blackjack, roulette, dice, slots, orders, quests, vacation, optout)

### Voice Stats Commands (`/voice_stats`)
- **`/voice`** - View voice minutes logged today

### Tax Commands (`/quarterly_tax`)
- Tax system runs automatically in background

### Context Menu Commands (Right-Click → Apps)
- **Praise** - (Mods) Public praise message
- **Humiliate** - (Mods) Public correction (requires consent role)
- **Add Note** - (Mods) Add staff note on user
- **Coin Tip** - Tip coins to user (opens modal)

---

## Background Systems & Automation

### 1. Message Tracking
- Tracks all messages (5-second cooldown per user)
- Excludes spam channel
- Counts toward event boss damage
- Flushes to database every 60 seconds

### 2. Voice Tracking
- Tracks voice channel sessions every 30 seconds
- Credits voice time to active events
- Reduces multiplier after 60 minutes without messages
- DMs user once when reduction begins
- Sending messages restores full strength

### 3. Event Scheduler
- Flushes message + voice counters every 60 seconds
- Updates boss HP every 30 seconds
- Triggers milestone announcements (80%, 60%, 40%, 20%, 0%)
- Calculates damage points from all activity sources

### 4. Tax System
- Tracks inactivity tax
- Accumulates debt over time
- Quarterly tax cycles
- Users can pay off debt

### 5. Punishment Expiry
- Automatically expires timed punishments
- Removes mute roles
- Reverts enforced nicknames
- Clears expired strikes

### 6. Daily Presence
- Tracks daily activity
- Manages daily claim windows
- UK timezone-based (GMT/BST)

### 7. Vacation Watch
- Monitors vacation mode
- Manages vacation expiration
- Welcomes users back

### 8. Casino Royalty
- Tracks top wagerers
- Assigns royalty roles
- Updates periodically

### 9. Big Win DMs
- Detects large casino wins
- Sends DM (max once per day)
- Tracks winnings

### 10. Daily Recap
- Generates casino activity summaries
- Sends to configured channels

### 11. Announcement Scheduler
- Executes scheduled announcements
- Handles repeating schedules (hourly/daily/weekly)
- Runs every 10 seconds

### 12. Reminder System
- Executes personal reminders
- DMs users at scheduled time
- Runs every 10 seconds

### 13. Personality Hot-Reload
- Checks personality.json file modification time
- Automatically reloads on file change
- Sanitizes all strings
- No bot restart required

---

## Database Tables

### Core User Tables
- **`users`** - User data (coins, debt, stage, favor_stage, last_msg_ts, safeword, vacation)
- **`consent`** - User consent preferences (18+ verification, orders, DMs, humiliation, callouts)
- **`user_activity_daily`** - Daily activity counters (messages, commands, coins, orders, tributes)

### Economy Tables
- **`economy_wallet`** - Wallet system (coins, tax_debt, last_tax_ts)
- **`economy_daily`** - Daily claim tracking (streak, last_claim_ts)
- **`economy_weekly`** - Weekly payout tracking
- **`economy_ledger`** - Transaction history (all coin movements)

### Orders Tables
- **`orders_catalog`** - Available orders
- **`orders_claims`** - Accepted orders with deadlines
- **`obedience_profile`** - Obedience streaks and stats
- **`obedience_penalties`** - Penalty tracking
- **`orders_active`** - Active order assignments (legacy)

### Discipline Tables
- **`discipline_punishments`** - Active punishments (warnings, strikes, timeouts, mutes, nicknames, seizures, fines)
- **`discipline_strikes`** - Strike history
- **`discipline_nicknames`** - Enforced nickname history
- **`discipline_debt`** - Debt tracking
- **`discipline_log`** - Discipline action log

### Shop & Inventory Tables
- **`shop_items`** - Shop item catalog
- **`inventory`** - User-owned items
- **`collars`** - Equipped collars with roles

### Event Tables
- **`events`** - Event definitions (seasonal, holiday, boss)
- **`event_boss`** - Boss HP and status
- **`event_user_day`** - Daily per-user event stats (messages, voice, casino, tokens, rituals, DP)
- **`event_user_state`** - User state (cooldowns, refresh timestamps)
- **`event_token_ledger`** - Token transaction history
- **`event_boss_tick`** - Boss damage tick history
- **`events_custom`** - Custom calendar events
- **`events_custom_participants`** - Custom event participants

### Casino Tables
- **`casino_stats`** - Casino statistics per user
- **`casino_royalty`** - Casino royalty rankings
- **`casino_bigwin`** - Big win tracking

### Moderation & Admin Tables
- **`user_admin_notes`** - Admin notes on users
- **`user_notes`** - Staff notes (from context menu)
- **`user_discipline`** - Discipline entries (legacy)
- **`audit_log`** - Complete audit trail
- **`staff_actions`** - Staff action log

### Configuration Tables
- **`feature_flags`** - Feature flags per guild/channel
- **`channel_config`** - Per-channel configuration
- **`guild_config`** - Server-wide configuration
- **`server_state`** - Server state (stage cap, etc.)

### Privacy Tables
- **`optout`** - Opt-out status
- **`optout_confirm`** - Opt-out confirmation tokens

### Announcement Tables
- **`announce_jobs`** - Scheduled announcements
- **`personal_reminders`** - Personal reminders

### Other Tables
- **`tribute_log`** - Tribute history
- **`spotlight`** - Spotlight/leaderboard entries
- **`weekly_stats`** - Weekly statistics
- **`onboarding_state`** - Onboarding progress
- **`mem`** - Key-value memory storage

---

## Core Services & Utilities

### Core Services (`islabot/core/`)
- **`FlagService`** - Feature flag management (enable/disable modules)
- **`ChannelConfigService`** - Per-channel configuration management
- **`Personality`** - Hot-reloadable personality/tone system
- **`Database`** - Database connection and migrations
- **`Config`** - Configuration file loader

### Utilities (`islabot/utils/`)
- **`economy.py`** - Economy helper functions (wallet, transactions)
- **`guild_config.py`** - Guild configuration helpers
- **`isla_style.py`** - Embed styling and formatting
- **`uk_parse.py`** - UK timezone parsing (durations, dates)
- **`uk_time.py`** - UK timezone helpers (GMT/BST)
- **`consent.py`** - Consent checking utilities
- **`helpers.py`** - General helper functions

### Tone & Personality
- **`tone.py`** - Tone pool selection
- **`personality.py`** - Personality hot-reload system
- **`order_templates.py`** - Order message templates
- **`order_tones.py`** - Order-specific tones
- **`seasonal_tones.py`** - Seasonal event tones
- **`isla_text.py`** - Text sanitization

### Event Systems
- **`boss_damage.py`** - Boss damage calculation formulas
- **`event_scoring.py`** - Event scoring system
- **`event_thumbs.py`** - Event thumbs/reactions
- **`holiday_configs.py`** - Holiday event configurations
- **`seasonal_configs.py`** - Seasonal event configurations

### Progression
- **`ranks.py`** - Rank system definitions
- **`favor.py`** - Favor system logic

---

## Key Features

### Permission System
- **Moderator**: Can use moderation commands, view notes, use discipline
- **Admin**: Can configure features, manage users, set configs
- **Consent-Based**: Humiliation and some interactions require consent role

### Privacy & Safety
- **Opt-Out**: Complete data deletion
- **Safeword**: Neutral tone switch
- **Vacation**: Temporary pause
- **Audit Logging**: Complete action history
- **Consent Granularity**: Per-feature consent

### Timezone Handling
- All times use UK timezone (Europe/London)
- Automatic GMT/BST switching
- UK time used for daily resets, event timing, etc.

### Personality System
- **Stage-Based**: Tone changes based on user stage (0-4)
- **Favor-Based**: Different interactions based on favor
- **Hot-Reloadable**: Edit personality.json without restart
- **Sanitized**: All text sanitized for safety

### Economy Balance
- **Daily Limits**: Transfer limits, claim windows
- **Streak Bonuses**: Rewards for consistency
- **Tax System**: Prevents hoarding
- **Transaction Ledger**: Complete audit trail

### Event Integration
- **Multi-Activity**: Messages, voice, casino, tokens, rituals all contribute
- **Logarithmic Scaling**: Prevents single-user dominance
- **Milestone Rewards**: Boss HP milestones unlock rewards
- **Token Economy**: Event-specific currency

---

## Command Summary by Category

**User Commands (Everyday Use):**
- `/start`, `/profile`, `/coins balance`, `/coins daily`, `/coins weekly`, `/coins pay`, `/coins shop`, `/coins buy`, `/coins burn`, `/coins history`
- `/orders view`, `/orders accept`, `/orders complete`, `/orders streak`, `/obey`, `/kneel`, `/beg`, `/forgive`
- `/punishments`, `/debt`, `/penance`
- `/event`, `/event progress`, `/tokens`, `/quests`, `/quest_claim`, `/season_shop`
- `/casino`, `/blackjack`, `/roulette`, `/dice`, `/slots`
- `/shop`, `/buy`, `/inventory`, `/equip`
- `/verify`, `/consent`, `/safeword`, `/vacation`, `/optout`, `/optin`
- `/info`, `/commands`, `/about`, `/ping`, `/status`
- `/remind`, `/duel`
- `/tribute`, `/voice`

**Moderator Commands:**
- `/purge`, `/slowmode`, `/lockdown`
- `/feature_list`, `/channelcfg_get`, `/note_set`, `/note_view`, `/discipline_add`, `/discipline_view`, `/admin_profile`, `/user_status`
- All `/discipline` commands
- Context menu: Praise, Humiliate, Add Note

**Admin Commands:**
- `/feature_set`, `/feature_set_channel`, `/channelcfg_set`, `/channelcfg_del`
- `/user_optout`, `/user_optin`, `/user_safeword`, `/user_unsafeword`
- `/config roles`, `/config channels`, `/config economy`, `/config orders`, `/config moderation`
- `/announce send`, `/announce schedule`
- `/event_start_holiday`, `/event_start_season`, `/event_start_boss`
- `/dev_reload_personality`
- `/collars_setup`

---

## Total Command Count

**Slash Commands**: ~90+ commands
**Context Menu Commands**: 4 commands
**Command Groups**: 10+ groups with subcommands

---

## Technical Details

- **Language**: Python 3.10+
- **Framework**: discord.py (async)
- **Database**: SQLite (aiosqlite)
- **Timezone**: UK (Europe/London, GMT/BST)
- **Content Rating**: PG-13
- **Persona**: Strict "boss/manager" with controlled interactions

---

*Last Updated: 2025*
*IslaBot V3 - Complete Documentation*

