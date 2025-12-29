# Cog Consolidation Mapping

This document maps the old cog structure to the new consolidated structure.

## New Structure

### 1. Commands ✅ (COMPLETE)
- **File**: `islabot/cogs/commands.py`
- **Merged from**:
  - `alive.py` - Activity tracking and personality hot-reload
  - `core_commands.py` - /commands, /about, /ping, /status
  - `info_unified.py` - /info command
  - `context_apps.py` - Context menu commands (Praise, Humiliate, Add Note, Coin Tip)

### 2. Admin (TODO)
- **File**: `islabot/cogs/admin.py`
- **To merge**:
  - `admin_tools.py` - Admin test commands
  - `config_group.py` - Channel and role configuration
  - `discipline_group.py` - Discipline/penalty commands

### 3. Data (TODO)
- **File**: `islabot/cogs/data.py`
- **To merge**:
  - `moderation.py` - Message tracking and weekly stats
  - `progression.py` - User progression tracking
  - `voice_tracker.py` - Voice channel activity tracking
  - `message_tracker.py` - Message hourly tracking
  - `event_activity_tracker.py` - Event activity tracking (messages, voice, casino, tokens, rituals)
  - `voice_stats.py` - Voice statistics display

### 4. Onboarding (TODO)
- **File**: `islabot/cogs/onboarding.py` (already exists, needs merging)
- **To merge**:
  - `onboarding.py` - Welcome messages, auto roles, rules acceptance, role selection
  - `consent.py` - Member verification and consent management

### 5. Announcements (TODO)
- **File**: `islabot/cogs/announcements.py`
- **To merge**:
  - `daily_presence.py` - Daily presence messages
  - `announce_and_remind.py` - Announcement and reminder commands
  - `leaderboard.py` - Spotlight leaderboard tracking and display
  - `casino_daily_recap.py` - Daily casino recap announcements

### 6. Orders (TODO)
- **File**: `islabot/cogs/orders.py` (already exists, needs merging)
- **To merge**:
  - `orders.py` - Order system (create, accept, complete, refuse)
  - `orders_group.py` - Order group commands
  - `tributes.py` - Tribute logging (may belong in Orders or Economy)

### 7. Events (TODO)
- **File**: `islabot/cogs/events.py` (already exists, needs merging)
- **To merge**:
  - `events.py` - Event system
  - `event_group.py` - Event group commands
  - `event_scheduler.py` - Event scheduling and boss HP updates
  - `event_boss_cmd.py` - Boss command handlers
  - `custom_events_group.py` - Custom event management

### 8. Economy (TODO)
- **File**: `islabot/cogs/economy.py` (already exists, needs merging)
- **To merge**:
  - `economy.py` - Core economy commands (balance, daily, burn)
  - `shop.py` - Shop system
  - `quarterly_tax.py` - Tax collection system
  - `coins_group.py` - Coin management group commands

### 9. Gambling (TODO)
- **File**: `islabot/cogs/gambling.py`
- **To merge**:
  - `casino_core.py` - Casino core system (highlights, recent rounds)
  - `casino_games.py` - Casino game commands (blackjack, roulette, dice, slots)
  - `casino_bigwin_dm.py` - Big win DM notifications
  - `casino_royalty.py` - Casino royalty role management

### 10. User (TODO)
- **File**: `islabot/cogs/user.py`
- **To merge**:
  - `privacy.py` - Privacy and opt-out commands
  - `profile.py` - User profile display
  - `safeword.py` - Safeword system
  - `vacation_watch.py` - Vacation system
  - `auto_reply.py` - Auto-reply system
  - `duel_cog.py` - Duel system

### 11. Personality (ALREADY IN CORE)
- **Location**: `islabot/core/`
- **Files** (already consolidated):
  - `embedder.py` - Embed formatting
  - `personality.py` - Personality system
  - `tone.py` - Tone management
  - `isla_text.py` - Text sanitization
  - `seasonal_configs.py` - Seasonal configurations
  - `seasonal_tones.py` - Seasonal tones
  - `holiday_configs.py` - Holiday configurations

## Migration Strategy

1. ✅ Create new consolidated cog files
2. ✅ Merge code from old cogs (preserve all functionality)
3. ✅ Update imports and dependencies
4. ✅ Update `bot.py` COGS list
5. ⏳ Test each consolidated cog
6. ⏳ Remove old cog files after verification

## Notes

- Preserve all task loops and schedulers
- Maintain all command groups and app commands
- Keep all database interactions
- Preserve all event listeners
- Maintain backward compatibility during transition

