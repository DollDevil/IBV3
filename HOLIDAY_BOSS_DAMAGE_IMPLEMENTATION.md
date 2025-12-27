# Holiday Boss Damage Formula Implementation Status

## ✅ Completed

### 1. Database Schema
- ✅ Added `boss_daily_stats` table for per-user daily damage tracking
- ✅ Added `boss_daily_scaling` table for global damage scaling
- ✅ Added `token_offerings` table for token-to-damage conversions

### 2. Core Damage Formula Module (`core/boss_damage.py`)
- ✅ Normalization function `f_normalize()` with sqrt-based diminishing returns
- ✅ Daily damage calculation function `calculate_daily_damage()`
- ✅ Global scaling calculation `calculate_global_scale()`
- ✅ Participation bonus logic (10% multiplier for 2+ requirements)
- ✅ Devotion points calculation for leaderboard
- ✅ Helper functions for HP calculation and expected damage

### 3. Constants & Configuration
- ✅ Daily caps: TS=250, CN=50k, CW=150k, M=250, V=240
- ✅ Base multipliers: TS=180, RC=120, CN=80, CW=70, M=60, V=60
- ✅ Participation thresholds defined
- ✅ Anti-spam/anti-idle constants defined

## 🚧 In Progress / Partially Implemented

### 4. Integration with Events System
- ⚠️ Added imports for boss_damage module
- ⚠️ Created scheduler stub `tick_boss_daily_finalize()` (not yet activated)
- ⚠️ Legacy calculation preserved for backward compatibility

## 📋 Remaining Work

### High Priority

1. **Daily Damage Finalization** (`_boss_finalize_daily_damage`)
   - Aggregate user activity for previous day
   - Track tokens spent (need to add tracking when users spend tokens)
   - Track ritual completions (already tracked via Orders cog)
   - Track casino net/wager (need CasinoCore integration)
   - Track messages/voice with anti-spam rules
   - Apply participation bonus
   - Apply global scaling
   - Store in `boss_daily_stats`
   - Apply damage to boss HP

2. **Token Spending Tracking**
   - Hook into `/event_claim`, `/season_shop`, token offerings
   - Log token spends to `boss_daily_stats.tokens_spent`
   - Currently tokens are spent but not tracked for boss damage

3. **Casino Net Tracking**
   - Track profit/loss per user per day (CasinoCore integration)
   - Currently only wager is tracked, need net profit/loss

4. **Anti-Spam Message Filtering**
   - Integrate `filter_valid_message()` into MessageTracker
   - Apply cooldown (max 1 count per 12 seconds per user)
   - Only count messages >= 8 chars or with links

5. **Voice Session Validation**
   - Integrate `check_voice_session_valid()` into VoiceTracker
   - Track muted/deafened percentage
   - Require minimum 5-minute sessions
   - Optional: require at least 1 message/day

6. **Token Offerings System**
   - Add `/event_offering` command for users to spend tokens for damage
   - Track in `token_offerings` table
   - Apply damage multipliers (22/24/26 per token based on bundle size)

### Medium Priority

7. **Leaderboards**
   - Damage Leaderboard: Sum of DP_user over event days
   - Devotion Leaderboard: Sum of DEV_day points
   - Add `/event leaderboard` command with both views
   - Tie-break logic (DEV > tokens > earlier participation)

8. **Global Scaling Implementation**
   - Calculate expected daily damage from boss HP
   - Retrieve yesterday's actual damage
   - Apply scaling factor (0.75-1.35 range)
   - Store in `boss_daily_scaling` table

9. **Embed Templates**
   - Event Start (Day 0)
   - Daily Ritual Available
   - Boss Status Update
   - Milestone Reached
   - Leaderboard Snapshot
   - Shop Drop
   - Easter Egg Hint
   - Climax Day Announcement
   - Event End Wrap
   - Reward DMs

10. **Default Boss HP Tuning**
    - Use `calculate_boss_hp_from_users()` for holiday weeks
    - Default: 3,500,000 HP for 1000 users
    - Scale based on server size

### Low Priority / Future Enhancements

11. **Shop Integration**
    - Hook holiday shop items into shop system
    - Implement pricing tiers (40-320 tokens)
    - Add glow upgrades and prestige items

12. **Raffle System**
    - 5 tokens per ticket
    - Up to 10 tickets/day
    - Prize pool system

13. **Ritual Boost Purchases**
    - 20 tokens: +1 ritual streak buffer
    - 35 tokens: +10% tokens tomorrow (once/day)

## Implementation Notes

### Current Architecture
- Legacy `_boss_calculate()` uses ES (Event Score) system with hourly/daily caps
- New system uses DP (Damage Points) with daily finalization
- Both can coexist: legacy for seasonal finales, new for holiday weeks

### Integration Points Needed

1. **Token Spending Hook**
   ```python
   # In events.py when tokens are spent:
   await self._log_token_spend(gid, user_id, scope_event_id, amount, day_key)
   ```

2. **Casino Net Hook**
   ```python
   # In CasinoCore when game completes:
   await self._log_casino_result(gid, user_id, wager, payout, net, day_key)
   ```

3. **Message Filtering**
   ```python
   # In MessageTracker on_message:
   if filter_valid_message(message.content):
       # count message
   ```

4. **Daily Finalization**
   ```python
   # At 00:10 UK time:
   await self._boss_finalize_daily_damage(guild, boss_eid, day_key)
   ```

## Testing Plan

1. **Unit Tests**
   - Test damage formula with various inputs
   - Test normalization function
   - Test participation bonus logic
   - Test global scaling

2. **Integration Tests**
   - Test daily finalization with sample data
   - Test leaderboard calculations
   - Test milestone unlocking

3. **Live Testing**
   - Start a test holiday week
   - Monitor daily damage calculations
   - Verify boss HP decreases correctly
   - Check leaderboard accuracy

## Default Values (for tuning)

- Boss HP: 3,500,000 (for 1000 users)
- Expected Daily Damage: ~564,516 (HP / 6.2)
- Token Earnings: ~15/day active, ~6/day casual
- Shop Pricing: 40-320 tokens (basic to prestige)

