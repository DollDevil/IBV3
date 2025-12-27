# Unified Boss Damage Formula Implementation

## ✅ Completed

### 1. Core Formula Module (`core/boss_damage.py`)
- ✅ Logarithmic scaling function `g_log_scale(x, k)` (no caps)
- ✅ Daily damage calculation with all 6 input buckets
- ✅ Voice effective minutes calculation with AFK reduction
- ✅ Devotion points calculation for leaderboard
- ✅ Constants defined (K values, base multipliers)

### 2. Message Tracking (`cogs/message_tracker.py`)
- ✅ Spam channel exclusion
- ✅ 5-minute cooldown tracking in `boss_message_cooldown` table
- ✅ Voice refresh timestamp updates (resets AFK reduction)
- ✅ `window_counts()` method updated to exclude spam and apply cooldown estimate

### 3. Voice Tracking (`cogs/voice_tracker.py`)
- ✅ Voice refresh timestamp tracking in `boss_voice_refresh` table
- ✅ Voice reduction warning system (DM when >60 min without refresh)
- ✅ `window_effective_minutes()` method for boss damage calculation
- ✅ Warning sent tracking (once per day per user)

### 4. Database Schema (`core/db.py`)
- ✅ `boss_daily_stats` table (tracks daily damage inputs and outputs)
- ✅ `boss_daily_scaling` table (global damage scaling)
- ✅ `boss_message_cooldown` table (5-minute cooldown per user)
- ✅ `boss_voice_refresh` table (voice refresh timestamps and warnings)

## 🚧 Remaining Integration Work

### High Priority

1. **Casino Net Tracking**
   - Extend `CasinoCore.get_window_summary()` to return `net_by_user: dict[int, int]`
   - Currently only returns `wager_by_user`, need to also sum net profit/loss per user

2. **Daily Damage Finalization Function**
   - Implement `_boss_finalize_daily_damage()` in `events.py`
   - Aggregate previous day's activity:
     - Tokens spent (from `token_balances` transactions)
     - Ritual completions (from `order_completion_log`)
     - Casino net/wager (from `CasinoCore`)
     - Messages (from `MessageTracker` with cooldown)
     - Voice effective minutes (from `VoiceTracker.window_effective_minutes()`)
   - Calculate damage points using `calculate_daily_damage()`
   - Apply global scaling
   - Store in `boss_daily_stats`
   - Apply damage to boss HP

3. **Token Spending Tracking**
   - Hook into token spending (when users spend tokens in shop/claim rewards)
   - Log to `boss_daily_stats.tokens_spent` per day
   - Currently tokens are spent but not tracked for boss damage

4. **Boss Calculation Integration**
   - Update `_boss_calculate()` to use new formula for holiday weeks
   - Keep legacy ES system for seasonal events (or migrate both)
   - Add method to detect event type (holiday_week vs season)

### Medium Priority

5. **Leaderboard Commands**
   - Damage Leaderboard: Sum DP_user over event duration
   - Devotion Leaderboard: Sum DEV_day points
   - Add `/event leaderboard` command

6. **Embed Templates**
   - Update boss status embeds
   - Add voice reduction warning embed (already implemented in voice_tracker.py)

7. **Scheduler Activation**
   - Activate `tick_boss_daily_finalize()` scheduler
   - Run at 00:10 UK time to finalize previous day's damage

## Formula Details

### Damage Formula (No Caps, Logarithmic)
```
DP_user = 
  260 * g(TS, 25) +          # tokens spent
  160 * RC +                  # ritual completion (0 or 1)
  110 * g(CN, 10000) +        # casino net (clamped to >= 0)
  95  * g(CW, 20000) +        # casino wager
  80  * g(M, 20) +            # messages (cooldown applied)
  80  * g(V_eff, 30)          # voice effective minutes (AFK reduced)
```

Where `g(x, k) = ln(1 + x/k)` provides diminishing returns without hard caps.

### Voice AFK Reduction
- After 60 minutes in voice without sending a message, contribution reduced to 35%
- Sending any message resets the timer (full strength restored)
- Warning DM sent once per day when reduction applies

### Message Cooldown
- One message counts per 5 minutes per user for boss damage
- No character limit, all channels except spam
- Cooldown is tracked in `boss_message_cooldown` table

### Devotion Points (Leaderboard)
```
DEV_day = 
  2 * I(TS > 0) +
  3 * RC +
  1 * I(M >= 1) +
  1 * I(V >= 10) +
  1 * I(CW >= 1000)
```

## Testing Checklist

- [ ] Message cooldown works (5-minute intervals)
- [ ] Spam channel exclusion works
- [ ] Voice refresh resets AFK reduction
- [ ] Voice warning sends once per day
- [ ] Casino net calculation (profit/loss aggregation)
- [ ] Token spending tracking
- [ ] Daily damage finalization at 00:10 UK
- [ ] Boss HP decreases correctly
- [ ] Leaderboards calculate correctly

