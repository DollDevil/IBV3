from __future__ import annotations
import aiosqlite

class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def execute(self, sql: str, params=()):
        assert self.conn
        await self.conn.execute(sql, params)
        await self.conn.commit()

    async def fetchone(self, sql: str, params=()):
        assert self.conn
        cur = await self.conn.execute(sql, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchall(self, sql: str, params=()):
        assert self.conn
        cur = await self.conn.execute(sql, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    async def _ensure_column(self, table: str, col: str, ddl: str):
        """Add column if missing (SQLite)."""
        assert self.conn
        rows = await self.fetchall(f"PRAGMA table_info({table});")
        existing = {r["name"] for r in rows}
        if col not in existing:
            await self.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")

    async def migrate(self):
        await self.execute("""
        CREATE TABLE IF NOT EXISTS users (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          coins    INTEGER NOT NULL DEFAULT 0,
          lce      INTEGER NOT NULL DEFAULT 0,
          debt     INTEGER NOT NULL DEFAULT 0,
          stage    INTEGER NOT NULL DEFAULT 0,
          favor_stage INTEGER NOT NULL DEFAULT 0,
          last_msg_ts INTEGER,
          daily_claim_day INTEGER,
          safeword_until_ts INTEGER,
          PRIMARY KEY (guild_id, user_id)
        );
        """)
        
        # Ensure favor_stage column exists for existing installations
        await self._ensure_column("users", "favor_stage", "INTEGER NOT NULL DEFAULT 0")

        await self.execute("""
        CREATE TABLE IF NOT EXISTS consent (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          verified_18 INTEGER NOT NULL DEFAULT 0,
          consent_ok  INTEGER NOT NULL DEFAULT 0,
          opt_orders  INTEGER NOT NULL DEFAULT 0,
          opt_public_callouts INTEGER NOT NULL DEFAULT 0,
          opt_dm INTEGER NOT NULL DEFAULT 0,
          opt_humiliation INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS server_state (
          guild_id INTEGER PRIMARY KEY,
          stage_cap INTEGER NOT NULL DEFAULT 4
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS orders_active (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          order_key TEXT NOT NULL,
          accepted_ts INTEGER NOT NULL,
          deadline_ts INTEGER NOT NULL,
          reward INTEGER NOT NULL,
          status TEXT NOT NULL,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS mem (
          guild_id INTEGER NOT NULL,
          k TEXT NOT NULL,
          v TEXT NOT NULL,
          ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, k)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
          guild_id INTEGER NOT NULL,
          item_id TEXT NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          price INTEGER NOT NULL,
          kind TEXT NOT NULL,
          role_id INTEGER,
          stage_required INTEGER NOT NULL DEFAULT 0,
          enabled INTEGER NOT NULL DEFAULT 1,
          event_only INTEGER NOT NULL DEFAULT 0,
          event_key TEXT,
          PRIMARY KEY (guild_id, item_id)
        );
        """)
        
        # Migrate item_key to item_id if needed
        try:
            await self._ensure_column("shop_items", "item_id", "TEXT")
            # Copy item_key to item_id for existing rows
            await self.execute("""
                UPDATE shop_items SET item_id = item_key WHERE item_id IS NULL OR item_id = ''
            """)
        except Exception:
            pass  # Column might already exist

        # Note: New inventory table uses item_id (defined below)
        # This old definition kept for backward compatibility check

        await self.execute("""
        CREATE TABLE IF NOT EXISTS collars (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          collar_key TEXT NOT NULL,
          role_id INTEGER NOT NULL,
          equipped_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS tribute_log (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          amount INTEGER NOT NULL,
          note TEXT,
          ts INTEGER NOT NULL
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS spotlight (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          day_key INTEGER NOT NULL,
          msg_count INTEGER NOT NULL DEFAULT 0,
          coins_earned INTEGER NOT NULL DEFAULT 0,
          coins_burned INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id, day_key)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS seasonal_state (
          guild_id INTEGER PRIMARY KEY,
          event_key TEXT,
          starts_ts INTEGER,
          ends_ts INTEGER,
          enabled INTEGER NOT NULL DEFAULT 0
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
          guild_id     INTEGER NOT NULL,
          user_id      INTEGER NOT NULL,
          channel_id   INTEGER,
          started_ts   INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS voice_daily (
          guild_id   INTEGER NOT NULL,
          user_id    INTEGER NOT NULL,
          day_key    TEXT NOT NULL,
          seconds    INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id, day_key)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_daily_guild_day ON voice_daily(guild_id, day_key);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS voice_events (
          guild_id    INTEGER NOT NULL,
          user_id     INTEGER NOT NULL,
          channel_id  INTEGER,
          start_ts    INTEGER NOT NULL,
          end_ts      INTEGER NOT NULL,
          seconds     INTEGER NOT NULL
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_events_guild_end ON voice_events(guild_id, end_ts);
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_events_guild_user_end ON voice_events(guild_id, user_id, end_ts);
        """)

        # =========================
        # MESSAGE TRACKING (hourly buckets) - EventSystem adapter
        # =========================
        await self.execute("""
        CREATE TABLE IF NOT EXISTS message_hourly (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          channel_id INTEGER NOT NULL,
          hour_ts INTEGER NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id, channel_id, hour_ts)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_hourly_time ON message_hourly(guild_id, hour_ts);
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_hourly_user ON message_hourly(guild_id, user_id, hour_ts);
        """)

        # =========================
        # VOICE TRACKING (EventSystem adapter - new schema)
        # =========================
        # Note: These tables use join_ts/leave_ts and day_ts (integer) for EventSystem compatibility
        # The old voice_sessions (started_ts) and voice_daily (day_key text) tables coexist for legacy code
        await self.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions_es (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          join_ts INTEGER NOT NULL,
          leave_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id, join_ts)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_sessions_es_leave ON voice_sessions_es(guild_id, leave_ts);
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_sessions_es_user ON voice_sessions_es(guild_id, user_id, join_ts);
        """)

        # Optional: daily VC aggregate for faster window_minutes (UTC day buckets)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS voice_daily_es (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          day_ts INTEGER NOT NULL,
          minutes INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id, day_ts)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_daily_es_day ON voice_daily_es(guild_id, day_ts);
        """)

        # Optional: Order completion log for boss ES tracking
        await self.execute("""
        CREATE TABLE IF NOT EXISTS order_completion_log (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          ts INTEGER NOT NULL,
          kind TEXT NOT NULL,
          PRIMARY KEY (guild_id, user_id, ts, kind)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_order_completion_log_time ON order_completion_log(guild_id, ts);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS coin_ledger (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          ts       INTEGER NOT NULL,
          delta    INTEGER NOT NULL,
          reason   TEXT NOT NULL
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_guild_user_ts ON coin_ledger(guild_id, user_id, ts);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS weekly_stats (
          guild_id INTEGER NOT NULL,
          week_key TEXT NOT NULL,
          user_id  INTEGER NOT NULL,
          msg_count INTEGER NOT NULL DEFAULT 0,
          react_count INTEGER NOT NULL DEFAULT 0,
          voice_seconds INTEGER NOT NULL DEFAULT 0,
          casino_wagered INTEGER NOT NULL DEFAULT 0,
          was INTEGER NOT NULL DEFAULT 0,
          weekly_bonus_claimed INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, week_key, user_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_weekly_stats_guild_week ON weekly_stats(guild_id, week_key);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          item_id  TEXT NOT NULL,
          qty      INTEGER NOT NULL DEFAULT 1,
          acquired_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id, item_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS equips (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          slot     TEXT NOT NULL,
          item_id  TEXT NOT NULL,
          equipped_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id, slot)
        );
        """)

        # Update shop_items schema if needed (ensure tier, slot, meta_json columns exist)
        await self._ensure_column("shop_items", "tier", "TEXT DEFAULT 'base'")
        await self._ensure_column("shop_items", "slot", "TEXT DEFAULT 'collar'")
        await self._ensure_column("shop_items", "meta_json", "TEXT DEFAULT '{}'")
        
        # Handle item_key -> item_id migration if needed
        try:
            # Check if item_key column exists (old schema)
            rows = await self.fetchall("PRAGMA table_info(shop_items);")
            has_item_key = any(r["name"] == "item_key" for r in rows)
            has_item_id = any(r["name"] == "item_id" for r in rows)
            
            if has_item_key and not has_item_id:
                # Add item_id column and copy from item_key
                await self.execute("ALTER TABLE shop_items ADD COLUMN item_id TEXT;")
                await self.execute("UPDATE shop_items SET item_id = item_key WHERE item_id IS NULL;")
        except Exception:
            pass  # Ignore migration errors

        await self.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
          guild_id INTEGER PRIMARY KEY,
          collars_role_enabled INTEGER NOT NULL DEFAULT 0,
          collars_role_prefix TEXT NOT NULL DEFAULT "Collar",
          log_channel_id INTEGER NOT NULL DEFAULT 0
        );
        """)

        # Add missing columns (SQLite "ALTER TABLE ADD COLUMN" is safe)
        await self._ensure_column("shop_items", "event_only", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("shop_items", "event_key", "TEXT")
        
        await self.execute("""
        CREATE TABLE IF NOT EXISTS casino_user_state (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          win_streak INTEGER NOT NULL DEFAULT 0,
          loss_streak INTEGER NOT NULL DEFAULT 0,
          last_net INTEGER NOT NULL DEFAULT 0,
          last_play_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)
        
        await self.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          key      TEXT NOT NULL,
          value    INTEGER NOT NULL DEFAULT 0,
          updated_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id, key)
        );
        """)
        
        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_achievements_guild_user ON achievements(guild_id, user_id);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS casino_bigwin_state (
          guild_id INTEGER NOT NULL,
          user_id  INTEGER NOT NULL,
          best_net INTEGER NOT NULL DEFAULT 0,
          best_payout INTEGER NOT NULL DEFAULT 0,
          best_ts INTEGER NOT NULL DEFAULT 0,
          last_dm_day_key TEXT NOT NULL DEFAULT "",
          last_dm_ts INTEGER NOT NULL DEFAULT 0,
          bigwins_count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS orders (
          guild_id INTEGER NOT NULL,
          order_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          scope TEXT NOT NULL,
          owner_user_id INTEGER NOT NULL DEFAULT 0,
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          reward_coins INTEGER NOT NULL DEFAULT 0,
          reward_obedience INTEGER NOT NULL DEFAULT 0,
          requirement_json TEXT NOT NULL,
          hint_channel_id INTEGER NOT NULL DEFAULT 0,
          max_slots INTEGER NOT NULL DEFAULT 1,
          slots_taken INTEGER NOT NULL DEFAULT 0,
          created_ts INTEGER NOT NULL,
          start_ts INTEGER NOT NULL,
          due_ts INTEGER NOT NULL,
          status TEXT NOT NULL,
          posted_channel_id INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, order_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS order_runs (
          guild_id INTEGER NOT NULL,
          order_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          accepted_ts INTEGER NOT NULL,
          due_ts INTEGER NOT NULL,
          status TEXT NOT NULL,
          progress_json TEXT NOT NULL DEFAULT "{}",
          completed_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, order_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS order_stats (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          completed_total INTEGER NOT NULL DEFAULT 0,
          failed_total INTEGER NOT NULL DEFAULT 0,
          current_streak INTEGER NOT NULL DEFAULT 0,
          best_streak INTEGER NOT NULL DEFAULT 0,
          last_complete_day_key TEXT NOT NULL DEFAULT "",
          last_action_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS order_system_state (
          guild_id INTEGER NOT NULL,
          key TEXT NOT NULL,
          value TEXT NOT NULL,
          PRIMARY KEY (guild_id, key)
        );
        """)

        # Unified event system schema (new design)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS events (
          guild_id INTEGER NOT NULL,
          event_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          name TEXT NOT NULL,
          token_name TEXT NOT NULL,
          start_ts INTEGER NOT NULL,
          end_ts INTEGER NOT NULL,
          climax_ts INTEGER NOT NULL DEFAULT 0,
          is_active INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, event_id)
        );
        """)
        
        # Legacy events table (for backward compatibility during migration)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS events_legacy (
          guild_id INTEGER NOT NULL,
          event_id INTEGER NOT NULL,
          type TEXT NOT NULL,
          parent_event_id INTEGER DEFAULT NULL,
          name TEXT NOT NULL,
          start_ts INTEGER NOT NULL,
          end_ts INTEGER NOT NULL,
          status TEXT NOT NULL,
          config_json TEXT NOT NULL,
          created_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, event_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_guild_status ON events(guild_id, status);
        CREATE INDEX IF NOT EXISTS idx_events_guild_type ON events(guild_id, type);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_state (
          guild_id INTEGER NOT NULL,
          event_id INTEGER NOT NULL,
          key TEXT NOT NULL,
          value TEXT NOT NULL,
          updated_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, event_id, key)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_state_event ON event_state(guild_id, event_id);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_contrib (
          guild_id INTEGER NOT NULL,
          event_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          score_total INTEGER NOT NULL DEFAULT 0,
          breakdown_json TEXT NOT NULL DEFAULT "{}",
          caps_json TEXT NOT NULL DEFAULT "{}",
          last_update_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, event_id, user_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_contrib_event ON event_contrib(guild_id, event_id);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_claims (
          guild_id INTEGER NOT NULL,
          event_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          claim_key TEXT NOT NULL,
          claimed_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, event_id, user_id, claim_key)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS token_balances (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          scope_event_id INTEGER NOT NULL,
          tokens INTEGER NOT NULL DEFAULT 0,
          updated_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id, scope_event_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_tokens_scope ON token_balances(guild_id, scope_event_id);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS quests (
          guild_id INTEGER NOT NULL,
          quest_id INTEGER NOT NULL,
          event_id INTEGER DEFAULT NULL,
          tier TEXT NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          requirement_json TEXT NOT NULL,
          reward_json TEXT NOT NULL,
          start_ts INTEGER NOT NULL,
          end_ts INTEGER NOT NULL,
          max_completions_per_user INTEGER NOT NULL DEFAULT 1,
          active INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (guild_id, quest_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_quests_event ON quests(guild_id, event_id);
        CREATE INDEX IF NOT EXISTS idx_quests_active ON quests(guild_id, active);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS quest_runs (
          guild_id INTEGER NOT NULL,
          quest_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          status TEXT NOT NULL,
          progress_json TEXT NOT NULL DEFAULT "{}",
          started_ts INTEGER NOT NULL,
          completed_ts INTEGER NOT NULL DEFAULT 0,
          claimed_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, quest_id, user_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_quest_runs_user ON quest_runs(guild_id, user_id);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_system_state (
          guild_id INTEGER NOT NULL,
          key TEXT NOT NULL,
          value TEXT NOT NULL,
          PRIMARY KEY (guild_id, key)
        );
        """)

        # Easter egg winners (single-winner tracking)
        # Event boss state
        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_boss (
          guild_id INTEGER NOT NULL,
          event_id TEXT NOT NULL,
          boss_name TEXT NOT NULL,
          hp_max INTEGER NOT NULL,
          hp_current INTEGER NOT NULL,
          last_tick_ts INTEGER NOT NULL DEFAULT 0,
          last_announce_hp_bucket INTEGER NOT NULL DEFAULT 100,
          PRIMARY KEY (guild_id, event_id)
        );
        """)
        
        # Daily per-user stats (source of truth for scoring)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_user_day (
          guild_id INTEGER NOT NULL,
          event_id TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          day_ymd TEXT NOT NULL,
          msg_count INTEGER NOT NULL DEFAULT 0,
          vc_minutes INTEGER NOT NULL DEFAULT 0,
          vc_reduced_minutes INTEGER NOT NULL DEFAULT 0,
          ritual_done INTEGER NOT NULL DEFAULT 0,
          tokens_spent INTEGER NOT NULL DEFAULT 0,
          casino_wager INTEGER NOT NULL DEFAULT 0,
          casino_net INTEGER NOT NULL DEFAULT 0,
          dp_cached REAL NOT NULL DEFAULT 0,
          last_update_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, event_id, user_id, day_ymd)
        );
        """)
        
        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_user_day_rank
        ON event_user_day(guild_id, event_id, day_ymd, dp_cached DESC);
        """)
        
        # Per-user anti-spam and VC refresh state
        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_user_state (
          guild_id INTEGER NOT NULL,
          event_id TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          last_msg_counted_ts INTEGER NOT NULL DEFAULT 0,
          vc_last_refresh_ts INTEGER NOT NULL DEFAULT 0,
          vc_reduced_warned INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, event_id, user_id)
        );
        """)
        
        # Token transactions (audit + sinks)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_token_ledger (
          guild_id INTEGER NOT NULL,
          event_id TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          ts INTEGER NOT NULL,
          delta INTEGER NOT NULL,
          reason TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}'
        );
        """)
        
        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_token_ledger_user
        ON event_token_ledger(guild_id, event_id, user_id, ts);
        """)
        
        # Boss tick contributions (optional but great for transparency)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_boss_tick (
          guild_id INTEGER NOT NULL,
          event_id TEXT NOT NULL,
          ts INTEGER NOT NULL,
          damage_total REAL NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}'
        );
        """)
        
        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_boss_tick_time
        ON event_boss_tick(guild_id, event_id, ts);
        """)
        
        await self.execute("""
        CREATE TABLE IF NOT EXISTS easter_egg_winners (
          guild_id INTEGER NOT NULL,
          event_id INTEGER NOT NULL,
          egg_key TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          claimed_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, event_id, egg_key)
        );
        """)

        # Key-value store for one-time flags (onboarding, etc.)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS kv_store (
          k TEXT PRIMARY KEY,
          v TEXT NOT NULL
        );
        """)

        # Onboarding state tracking
        await self.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_state (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          joined_ts INTEGER NOT NULL,
          verified_ts INTEGER NOT NULL DEFAULT 0,
          last_reminder_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_onboarding_state_verified ON onboarding_state(guild_id, verified_ts);
        """)

        # Opt-out confirmation tokens
        await self.execute("""
        CREATE TABLE IF NOT EXISTS optout_confirm (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          token TEXT NOT NULL,
          expires_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        # Staff actions log (optional)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS staff_actions (
          guild_id INTEGER NOT NULL,
          staff_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          ts INTEGER NOT NULL
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_staff_actions_time ON staff_actions(guild_id, ts);
        """)

        # Ensure users table has required columns
        await self._ensure_column("users", "obedience", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "xp", "INTEGER NOT NULL DEFAULT 0")
        
        # User controls: opt-out, safeword, vacation
        await self._ensure_column("users", "opted_out", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "safeword_on", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "safeword_set_ts", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "safeword_reason", "TEXT NOT NULL DEFAULT ''")
        await self._ensure_column("users", "safeword_until_ts", "INTEGER")
        await self._ensure_column("users", "vacation_until_ts", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "vacation_last_used_ts", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "vacation_welcomed_ts", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("users", "last_active_ts", "INTEGER")
        await self._ensure_column("users", "last_allin_ts", "INTEGER")

        # Economy Wallet System (new /coins group)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS economy_wallet (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          coins INTEGER NOT NULL DEFAULT 0,
          tax_debt INTEGER NOT NULL DEFAULT 0,
          last_tax_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS economy_daily (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          streak INTEGER NOT NULL DEFAULT 0,
          last_claim_ymd TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS economy_weekly (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          last_claim_week TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS economy_ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          ts INTEGER NOT NULL,
          delta INTEGER NOT NULL,
          kind TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          other_user_id INTEGER,
          meta_json TEXT NOT NULL DEFAULT '{}'
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_economy_ledger_user_time
        ON economy_ledger(guild_id, user_id, ts DESC);
        """)

        # Orders & Obedience System
        await self.execute("""
        CREATE TABLE IF NOT EXISTS orders_catalog (
          guild_id INTEGER NOT NULL,
          order_id INTEGER NOT NULL,
          order_type TEXT NOT NULL,
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          reward_coins INTEGER NOT NULL DEFAULT 0,
          reward_obed INTEGER NOT NULL DEFAULT 0,
          duration_seconds INTEGER NOT NULL DEFAULT 3600,
          max_slots INTEGER NOT NULL DEFAULT 0,
          starts_ts INTEGER NOT NULL DEFAULT 0,
          ends_ts INTEGER NOT NULL DEFAULT 0,
          is_active INTEGER NOT NULL DEFAULT 1,
          meta_json TEXT NOT NULL DEFAULT '{}',
          PRIMARY KEY (guild_id, order_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS orders_claims (
          guild_id INTEGER NOT NULL,
          order_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          status TEXT NOT NULL,
          accepted_ts INTEGER NOT NULL,
          due_ts INTEGER NOT NULL,
          completed_ts INTEGER NOT NULL DEFAULT 0,
          proof_text TEXT NOT NULL DEFAULT '',
          proof_url TEXT NOT NULL DEFAULT '',
          penalty_coins INTEGER NOT NULL DEFAULT 0,
          penalty_obed INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, order_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS obedience_profile (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          obedience INTEGER NOT NULL DEFAULT 0,
          streak_days INTEGER NOT NULL DEFAULT 0,
          last_streak_ymd TEXT NOT NULL DEFAULT '',
          mercy_uses INTEGER NOT NULL DEFAULT 0,
          forgive_tokens INTEGER NOT NULL DEFAULT 0,
          last_penalty_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS obedience_penalties (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          ts INTEGER NOT NULL,
          kind TEXT NOT NULL,
          coins INTEGER NOT NULL DEFAULT 0,
          obed INTEGER NOT NULL DEFAULT 0,
          cleared INTEGER NOT NULL DEFAULT 0,
          note TEXT NOT NULL DEFAULT ''
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_claims_user
        ON orders_claims(guild_id, user_id, status);
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_catalog_active
        ON orders_catalog(guild_id, order_type, is_active);
        """)

        # Quarterly Tax System
        await self.execute("""
        CREATE TABLE IF NOT EXISTS tax_schedule (
          guild_id INTEGER PRIMARY KEY,
          next_tax_ts INTEGER NOT NULL,
          last_tax_ts INTEGER NOT NULL DEFAULT 0,
          warning_7d_sent INTEGER NOT NULL DEFAULT 0,
          warning_3d_sent INTEGER NOT NULL DEFAULT 0,
          warning_24h_sent INTEGER NOT NULL DEFAULT 0,
          tax_tone_until_ts INTEGER NOT NULL DEFAULT 0
        );
        """)

        # Tax execution log (for transparency)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS tax_log (
          guild_id INTEGER NOT NULL,
          tax_ts INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          coins_before INTEGER NOT NULL,
          coins_taken INTEGER NOT NULL,
          coins_after INTEGER NOT NULL,
          PRIMARY KEY (guild_id, tax_ts, user_id)
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_tax_log_time ON tax_log(guild_id, tax_ts);
        """)

        # Advanced Utility Layer: Feature Flags
        await self.execute("""
        CREATE TABLE IF NOT EXISTS feature_flags (
          guild_id INTEGER NOT NULL,
          scope TEXT NOT NULL,
          scope_id INTEGER NOT NULL,
          feature TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (guild_id, scope, scope_id, feature)
        );
        """)

        # Advanced Utility Layer: Channel Config
        await self.execute("""
        CREATE TABLE IF NOT EXISTS channel_config (
          guild_id INTEGER NOT NULL,
          channel_id INTEGER NOT NULL,
          key TEXT NOT NULL,
          value TEXT NOT NULL,
          PRIMARY KEY (guild_id, channel_id, key)
        );
        """)

        # Advanced Utility Layer: User Admin Notes
        await self.execute("""
        CREATE TABLE IF NOT EXISTS user_admin_notes (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          note TEXT NOT NULL,
          created_by INTEGER NOT NULL,
          created_ts INTEGER NOT NULL,
          updated_ts INTEGER,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        # Advanced Utility Layer: User Discipline
        await self.execute("""
        CREATE TABLE IF NOT EXISTS user_discipline (
          guild_id INTEGER NOT NULL,
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          reason TEXT,
          points INTEGER NOT NULL DEFAULT 1,
          created_by INTEGER NOT NULL,
          created_ts INTEGER NOT NULL
        );
        """)

        # Advanced Utility Layer: User Activity Daily
        await self.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_daily (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          day_key INTEGER NOT NULL,
          messages INTEGER NOT NULL DEFAULT 0,
          commands INTEGER NOT NULL DEFAULT 0,
          coins_earned INTEGER NOT NULL DEFAULT 0,
          coins_burned INTEGER NOT NULL DEFAULT 0,
          orders_taken INTEGER NOT NULL DEFAULT 0,
          orders_completed INTEGER NOT NULL DEFAULT 0,
          tributes_logged INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id, day_key)
        );
        """)

        # Advanced Utility Layer: Audit Log
        await self.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
          guild_id INTEGER NOT NULL,
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor_id INTEGER,
          target_user_id INTEGER,
          action TEXT NOT NULL,
          meta TEXT,
          created_ts INTEGER NOT NULL
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_time ON audit_log(guild_id, created_ts);
        """)

        # Advanced Utility Layer: Opt-out (new table for hard delete system)
        # Discipline & Punishments System
        await self.execute("""
        CREATE TABLE IF NOT EXISTS discipline_punishments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          created_ts INTEGER NOT NULL,
          ends_ts INTEGER NOT NULL DEFAULT 0,
          conditions TEXT NOT NULL DEFAULT '',
          active INTEGER NOT NULL DEFAULT 1,
          issued_by INTEGER NOT NULL DEFAULT 0,
          meta_json TEXT NOT NULL DEFAULT '{}'
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS discipline_strikes (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          strikes INTEGER NOT NULL DEFAULT 0,
          last_strike_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS discipline_nicknames (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          old_nick TEXT NOT NULL DEFAULT '',
          new_nick TEXT NOT NULL DEFAULT '',
          ends_ts INTEGER NOT NULL,
          active INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS discipline_debt (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          debt INTEGER NOT NULL DEFAULT 0,
          updated_ts INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS discipline_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          ts INTEGER NOT NULL,
          action TEXT NOT NULL,
          target_id INTEGER NOT NULL,
          moderator_id INTEGER NOT NULL,
          amount INTEGER NOT NULL DEFAULT 0,
          duration_seconds INTEGER NOT NULL DEFAULT 0,
          reason TEXT NOT NULL DEFAULT ''
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_punishments_active
        ON discipline_punishments(guild_id, user_id, active, ends_ts);
        """)

        # Guild Config & Events System
        await self.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
          guild_id INTEGER NOT NULL,
          key TEXT NOT NULL,
          value TEXT NOT NULL,
          updated_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, key)
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS announce_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          channel_id INTEGER NOT NULL,
          message TEXT NOT NULL,
          embed_title TEXT NOT NULL DEFAULT '',
          repeat_rule TEXT NOT NULL DEFAULT 'none',
          interval_minutes INTEGER NOT NULL DEFAULT 0,
          next_run_ts INTEGER NOT NULL,
          created_ts INTEGER NOT NULL,
          created_by INTEGER NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_announce_jobs_next
        ON announce_jobs(active, next_run_ts);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS personal_reminders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          message TEXT NOT NULL,
          run_ts INTEGER NOT NULL,
          created_ts INTEGER NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
        );
        """)

        await self.execute("""
        CREATE INDEX IF NOT EXISTS idx_personal_reminders_next
        ON personal_reminders(active, run_ts);
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS events_custom (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          start_ts INTEGER NOT NULL,
          end_ts INTEGER NOT NULL DEFAULT 0,
          channel_id INTEGER NOT NULL,
          role_id INTEGER NOT NULL DEFAULT 0,
          entry_cost INTEGER NOT NULL DEFAULT 0,
          reward_coins INTEGER NOT NULL DEFAULT 0,
          max_slots INTEGER NOT NULL DEFAULT 0,
          created_by INTEGER NOT NULL,
          created_ts INTEGER NOT NULL,
          active INTEGER NOT NULL DEFAULT 1
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS events_custom_participants (
          guild_id INTEGER NOT NULL,
          event_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          joined_ts INTEGER NOT NULL,
          PRIMARY KEY (guild_id, event_id, user_id)
        );
        """)

        # User Notes (staff notes)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS user_notes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          note TEXT NOT NULL,
          added_by INTEGER NOT NULL,
          ts INTEGER NOT NULL
        );
        """)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS optout (
          guild_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          opted_out INTEGER NOT NULL DEFAULT 0,
          opted_out_ts INTEGER,
          PRIMARY KEY (guild_id, user_id)
        );
        """)

    async def ensure_user(self, gid: int, uid: int):
        await self.execute("INSERT OR IGNORE INTO users(guild_id,user_id) VALUES(?,?)", (gid, uid))
        await self.execute("INSERT OR IGNORE INTO consent(guild_id,user_id) VALUES(?,?)", (gid, uid))
        await self.execute("INSERT OR IGNORE INTO server_state(guild_id) VALUES(?)", (gid,))

    async def ensure_shop_seeded(self, gid: int):
        # Minimal default shop seed (idempotent) - legacy method, kept for compatibility
        # Note: New shop system uses item_id, not item_key
        pass

    # Advanced Utility Layer: Opt-out methods
    async def is_opted_out(self, gid: int, uid: int) -> bool:
        """Check if user is opted out."""
        row = await self.fetchone("SELECT opted_out FROM optout WHERE guild_id=? AND user_id=?", (gid, uid))
        return bool(row and int(row["opted_out"]) == 1)

    async def set_optout(self, gid: int, uid: int, opted_out: bool, ts: int | None):
        """Set opt-out status."""
        await self.execute("INSERT OR IGNORE INTO optout(guild_id,user_id) VALUES(?,?)", (gid, uid))
        await self.execute(
            "UPDATE optout SET opted_out=?, opted_out_ts=? WHERE guild_id=? AND user_id=?",
            (1 if opted_out else 0, ts, gid, uid),
        )

    async def hard_delete_user(self, gid: int, uid: int):
        """Hard delete all user data across all tables (privacy-safe)."""
        tables = [
            ("users", "guild_id=? AND user_id=?"),
            ("consent", "guild_id=? AND user_id=?"),
            ("orders_active", "guild_id=? AND user_id=?"),
            ("inventory", "guild_id=? AND user_id=?"),
            ("collars", "guild_id=? AND user_id=?"),
            ("spotlight", "guild_id=? AND user_id=?"),
            ("tribute_log", "guild_id=? AND user_id=?"),
            ("user_admin_notes", "guild_id=? AND user_id=?"),
            ("user_activity_daily", "guild_id=? AND user_id=?"),
            ("optout", "guild_id=? AND user_id=?"),
        ]
        for t, where in tables:
            try:
                await self.execute(f"DELETE FROM {t} WHERE {where}", (gid, uid))
            except Exception:
                pass  # Table might not exist, ignore

        # Discipline is per-row table keyed by user_id
        try:
            await self.execute("DELETE FROM user_discipline WHERE guild_id=? AND user_id=?", (gid, uid))
        except Exception:
            pass

    async def audit(self, gid: int, actor_id: int | None, target_user_id: int | None, action: str, meta: str, ts: int):
        """Log an audit entry."""
        meta_truncated = meta[:2000] if meta else "{}"
        await self.execute(
            "INSERT INTO audit_log(guild_id,actor_id,target_user_id,action,meta,created_ts) VALUES(?,?,?,?,?,?)",
            (gid, actor_id, target_user_id, action, meta_truncated, ts),
        )

    async def set_user_safeword(self, gid: int, uid: int, until_ts: int | None):
        """Set safeword until timestamp for a user. until_ts=None clears it."""
        await self.ensure_user(gid, uid)
        await self.execute(
            "UPDATE users SET safeword_until_ts=? WHERE guild_id=? AND user_id=?",
            (until_ts, gid, uid),
        )

