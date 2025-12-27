# Unified Event Activity System Implementation

## ✅ Completed

### 1. Database Schema (`islabot/core/db.py`)
- ✅ `events` table (unified schema with event_id as TEXT, event_type, token_name, climax_ts)
- ✅ `event_boss` table (boss HP tracking with last_tick_ts and milestone buckets)
- ✅ `event_user_day` table (daily per-user stats: messages, voice, casino, tokens, rituals, cached DP)
- ✅ `event_user_state` table (anti-spam cooldown and VC refresh timestamps)
- ✅ `event_token_ledger` table (audit trail for all token transactions)
- ✅ `event_boss_tick` table (boss damage tick history for transparency)

### 2. Event Activity Tracker (`cogs/event_activity_tracker.py`)
- ✅ In-memory counters (live_msg, live_vc_seconds, live_vc_reduced_seconds, etc.)
- ✅ Message counting with 5-second cooldown (excludes spam channel)
- ✅ Voice tracking with AFK reduction (60-minute threshold, 35% multiplier)
- ✅ Voice reduction warning DM system
- ✅ Casino activity tracking (wager + net)
- ✅ Token spending/earning tracking with ledger
- ✅ Ritual completion marking
- ✅ Periodic flush to database (60-second intervals)
- ✅ Rolling boss HP tick (30-second intervals)
- ✅ Milestone detection (80/60/40/20/0 percent thresholds)

### 3. Integration Hooks
- ✅ MessageTracker forwards messages to EventActivityTracker
- ✅ VoiceTracker forwards voice sessions to EventActivityTracker
- ✅ CasinoGames forwards casino rounds to EventActivityTracker
- ✅ Orders forwards ritual completions to EventActivityTracker
- ✅ Events cog forwards token earning/spending to EventActivityTracker

### 4. Core Damage Formula (`core/boss_damage.py`)
- ✅ Logarithmic scaling function `g(x, k) = ln(1 + x/k)`
- ✅ Daily damage calculation with all 6 buckets
- ✅ Devotion points calculation for leaderboards
- ✅ Constants defined (K values, base multipliers)

## 📋 System Architecture

### In-Memory Tracking
- Counters stored in `defaultdict` keyed by `(guild_id, event_id, user_id, day_ymd)`
- User state stored in dicts keyed by `(guild_id, event_id, user_id)`
- Flushed to database every 60 seconds
- State persisted periodically to survive restarts

### Damage Calculation Flow
1. Activity occurs (message, voice, casino, ritual, token spend)
2. Tracked in memory by EventActivityTracker
3. Flushed to `event_user_day` table every 60 seconds
4. Boss HP tick runs every 30 seconds:
   - Queries `event_user_day` for rows updated since last tick
   - Computes DP deltas for changed rows
   - Updates `dp_cached` and boss HP
   - Checks milestones

### Voice AFK Reduction
- Tracks `vc_last_refresh_ts` per user per event
- If `(now - last_refresh) >= 3600` seconds (60 minutes):
  - Voice time goes to `vc_reduced_minutes` bucket
  - Sent to `live_vc_reduced_seconds` in-memory
  - Multiplier of 0.35 applied during DP calculation
- Sending any message (spam excluded) resets refresh timestamp
- Warning DM sent once per "reduced" state (resets when user messages)

### Message Cooldown
- One message counts per 5 seconds per user for boss damage
- Cooldown tracked in `last_msg_counted_ts` per user per event
- All messages (except spam) refresh voice timer, but only one per 5s counts for damage

## 🔌 Integration Points

### Message Tracking
```python
# In MessageTracker.on_message()
tracker = self.bot.get_cog("EventActivityTracker")
if tracker:
    await tracker.handle_message(message)
```

### Voice Tracking
```python
# In VoiceTracker.on_voice_state_update (when leaving VC)
tracker = self.bot.get_cog("EventActivityTracker")
if tracker:
    await tracker.add_voice_time(gid, uid, session_seconds)
```

### Casino Tracking
```python
# In CasinoGames._finish_round()
tracker = self.bot.get_cog("EventActivityTracker")
if tracker:
    await tracker.add_casino_activity(gid, uid, wager, net)
```

### Ritual Completion
```python
# In Orders.order_complete() (when kind == "ritual")
tracker = self.bot.get_cog("EventActivityTracker")
if tracker:
    await tracker.mark_ritual_done(gid, uid)
```

### Token Transactions
```python
# When tokens are earned (Events.event_claim)
tracker.add_token_earned(gid, uid, amount, "milestone_claim", meta)

# When tokens are spent (Events.quest_reroll, future shop integration)
tracker.add_tokens_spent(gid, uid, amount, "quest_reroll", meta)
```

## 🎯 Formula Details

### Damage Points (DP)
```
DP = 
  260 * g(TS, 25) +          # tokens spent
  160 * RC +                  # ritual completion (0 or 1)
  110 * g(CN, 10000) +        # casino net (clamped to >= 0)
  95  * g(CW, 20000) +        # casino wager
  80  * g(M, 20) +            # messages (cooldown applied)
  80  * g(V_eff, 30)          # voice effective (AFK reduced)
```

Where:
- `g(x, k) = ln(1 + x/k)` (logarithmic scaling, no caps)
- `V_eff = vc_minutes + (vc_reduced_minutes * 0.35)`

### Devotion Points (Leaderboard)
```
DEV_day = 
  2 * I(TS > 0) +
  3 * RC +
  1 * I(M >= 1) +
  1 * I(V >= 10) +
  1 * I(CW >= 1000)
```

## 📊 Database Queries

### Get Top Damage Contributors
```sql
SELECT user_id, SUM(dp_cached) AS total_dp
FROM event_user_day
WHERE guild_id=? AND event_id=?
GROUP BY user_id
ORDER BY total_dp DESC
LIMIT 10;
```

### Get Boss Status
```sql
SELECT hp_current, hp_max, last_tick_ts, last_announce_hp_bucket
FROM event_boss
WHERE guild_id=? AND event_id=?;
```

### Get User's Daily Stats
```sql
SELECT * FROM event_user_day
WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?;
```

## ⚠️ Remaining Work / Future Enhancements

1. **Token Shop Integration**
   - Hook into shop purchases to call `add_tokens_spent()`
   - Currently only quest reroll is hooked up

2. **Leaderboard Commands**
   - Implement `/event leaderboard` command
   - Show Damage and Devotion leaderboards
   - Tie-break logic (DEV > tokens > earlier participation)

3. **Milestone Announcements**
   - Integrate milestone handling with events cog
   - Post milestone announcements to #orders
   - Process milestone rewards

4. **Event Start/End Integration**
   - Create `event_boss` row when holiday/seasonal event starts
   - Initialize boss HP from user count or config
   - Handle event end cleanup

5. **State Restoration on Startup**
   - Load persisted user state from `event_user_state` on cog init
   - Restore in-memory cooldown and refresh timestamps

6. **Multi-Event Support**
   - Currently prioritizes holiday_week > season_era
   - Could support dual-write (holiday + era simultaneously)
   - Handle event overlaps gracefully

7. **Testing & Tuning**
   - Test with 1000+ users
   - Tune K values for logarithmic scaling
   - Adjust boss HP based on server size
   - Verify milestone timing

## 🔧 Configuration

### Constants (in `event_activity_tracker.py`)
- `MESSAGE_COOLDOWN_SECONDS = 5`
- `VC_REDUCE_AFTER_SECONDS = 3600` (60 minutes)
- `VC_REDUCED_MULT = 0.35`
- `FLUSH_EVERY = 60` (seconds)
- `BOSS_TICK_EVERY = 30` (seconds)

### Formula Constants (in `core/boss_damage.py`)
- `K_TS = 25` (tokens)
- `K_CN = 10000` (casino net)
- `K_CW = 20000` (casino wager)
- `K_M = 20` (messages)
- `K_V = 30` (voice minutes)

- `BASE_TS = 260`
- `BASE_RC = 160`
- `BASE_CN = 110`
- `BASE_CW = 95`
- `BASE_M = 80`
- `BASE_V = 80`

