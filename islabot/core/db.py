from __future__ import annotations
import aiosqlite
from contextlib import asynccontextmanager

class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self._in_tx: bool = False

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        # Enable WAL and foreign keys for better performance and integrity
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA foreign_keys=ON;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def execute(self, sql: str, params=(), commit: bool = True):
        """Execute SQL statement. If commit=False, don't commit (for use in transactions)."""
        assert self.conn
        await self.conn.execute(sql, params)
        # Only commit if explicitly requested AND not inside a transaction
        effective_commit = commit and not self._in_tx
        if effective_commit:
            await self.conn.commit()

    async def executemany(self, sql: str, params_list, commit: bool = True):
        """Execute SQL statement multiple times with different parameters."""
        assert self.conn
        await self.conn.executemany(sql, params_list)
        # Only commit if explicitly requested AND not inside a transaction
        effective_commit = commit and not self._in_tx
        if effective_commit:
            await self.conn.commit()

    async def commit(self):
        """Explicitly commit the current transaction."""
        assert self.conn
        await self.conn.commit()

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager: BEGIN on enter, COMMIT on success, ROLLBACK on exception."""
        assert self.conn
        self._in_tx = True
        try:
            await self.conn.execute("BEGIN")
            yield self
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
        finally:
            self._in_tx = False

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

    async def _ensure_column(self, table: str, col: str, ddl: str, commit: bool = True):
        """Add column if missing (SQLite)."""
        assert self.conn
        try:
            rows = await self.fetchall(f"PRAGMA table_info({table});")
            existing = {r["name"] for r in rows}
            if col not in existing:
                await self.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};", commit=commit)
        except Exception as e:
            # Table might not exist yet, that's okay
            print(f"Warning: Could not check/add column {col} to {table}: {e}")

    async def migrate(self):
        """Run database migrations. Handles errors gracefully. Wrapped in a single transaction."""
        try:
            async with self.transaction():
                await self._migrate_tables()
        except Exception as e:
            print(f"Database migration error: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise

    async def _migrate_tables(self):
        """Internal migration method (called within transaction)."""
        try:
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

            # Note: events table uses is_active, not status. events_legacy has status.
            # Index on events_legacy for status (if needed)
            await self.execute("CREATE INDEX IF NOT EXISTS idx_events_legacy_guild_status ON events_legacy(guild_id, status);")
            await self.execute("CREATE INDEX IF NOT EXISTS idx_events_guild_type ON events(guild_id, event_type);")
            await self.execute("CREATE INDEX IF NOT EXISTS idx_events_guild_active ON events(guild_id, is_active);")

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

            await self.execute("CREATE INDEX IF NOT EXISTS idx_quests_event ON quests(guild_id, event_id);")
            await self.execute("CREATE INDEX IF NOT EXISTS idx_quests_active ON quests(guild_id, active);")

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

            # =========================
            # V3 SCHEMA: 7-day-window immersion/progression system
            # All tables prefixed with v3_ to avoid collision with legacy tables
            # =========================

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_guilds (
              guild_id TEXT PRIMARY KEY,
              created_at INTEGER NOT NULL DEFAULT 0,
              name_cache TEXT,
              settings_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_users (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              created_at INTEGER NOT NULL DEFAULT 0,
              join_ts INTEGER NOT NULL DEFAULT 0,
              last_seen_ts INTEGER NOT NULL DEFAULT 0,
              is_opted_out INTEGER NOT NULL DEFAULT 0,
              opt_out_ts INTEGER,
              data_deleted_ts INTEGER,
              PRIMARY KEY (guild_id, user_id)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_user_profile (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              persona_mode TEXT NOT NULL DEFAULT 'default',
              nickname_preference TEXT NOT NULL DEFAULT '',
              nickname_opt_in INTEGER NOT NULL DEFAULT 0,
              dm_opt_in INTEGER NOT NULL DEFAULT 0,
              public_callouts_opt_in INTEGER NOT NULL DEFAULT 0,
              interaction_opts_json TEXT NOT NULL DEFAULT '{}',
              notes_user_visible TEXT NOT NULL DEFAULT '',
              updated_at INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (guild_id, user_id)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_activity_daily (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              date_key TEXT NOT NULL,
              message_count INTEGER NOT NULL DEFAULT 0,
              reaction_count INTEGER NOT NULL DEFAULT 0,
              voice_seconds INTEGER NOT NULL DEFAULT 0,
              dap_points INTEGER NOT NULL DEFAULT 0,
              was_points INTEGER NOT NULL DEFAULT 0,
              first_msg_ts INTEGER,
              last_msg_ts INTEGER,
              last_voice_ts INTEGER,
              PRIMARY KEY (guild_id, user_id, date_key)
            );
            """)

            await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_v3_activity_daily_date
            ON v3_activity_daily(guild_id, date_key);
            """)

            await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_v3_activity_daily_user_date
            ON v3_activity_daily(guild_id, user_id, date_key);
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_voice_sessions (
              session_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              channel_id TEXT,
              join_ts INTEGER NOT NULL,
              leave_ts INTEGER,
              seconds_total INTEGER NOT NULL DEFAULT 0,
              seconds_credited INTEGER NOT NULL DEFAULT 0,
              afk_filtered INTEGER NOT NULL DEFAULT 0,
              meta_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_progression_core (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              coins_balance INTEGER NOT NULL DEFAULT 0,
              coins_lifetime_earned INTEGER NOT NULL DEFAULT 0,
              coins_lifetime_burned INTEGER NOT NULL DEFAULT 0,
              activity_xp_hidden INTEGER NOT NULL DEFAULT 0,
              orders_completed_7d INTEGER NOT NULL DEFAULT 0,
              orders_late_7d INTEGER NOT NULL DEFAULT 0,
              orders_failed_7d INTEGER NOT NULL DEFAULT 0,
              orders_forfeited_7d INTEGER NOT NULL DEFAULT 0,
              streak_current_days INTEGER NOT NULL DEFAULT 0,
              streak_best_days INTEGER NOT NULL DEFAULT 0,
              obedience_7d_cached INTEGER,
              was_7d_cached INTEGER,
              weekly_claim_last_week_key TEXT,
              weekly_claim_last_amount INTEGER NOT NULL DEFAULT 0,
              debt_amount INTEGER NOT NULL DEFAULT 0,
              inactive_days_streak INTEGER NOT NULL DEFAULT 0,
              last_qualifying_activity_ts INTEGER,
              start_balance_granted INTEGER NOT NULL DEFAULT 0,
              updated_at INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (guild_id, user_id)
            );
            """)

            # Ensure start_balance_granted column exists for existing installations
            await self._ensure_column("v3_progression_core", "start_balance_granted", "INTEGER NOT NULL DEFAULT 0", commit=False)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_ranks (
              guild_id TEXT NOT NULL,
              rank_id TEXT NOT NULL,
              rank_index INTEGER NOT NULL,
              rank_name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              role_id TEXT,
              coin_band_min_lce INTEGER NOT NULL DEFAULT 0,
              obedience_required INTEGER NOT NULL DEFAULT 0,
              gates_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY (guild_id, rank_id)
            );
            """)

            # Ensure obedience_required column exists for existing installations
            await self._ensure_column("v3_ranks", "obedience_required", "INTEGER NOT NULL DEFAULT 0", commit=False)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_rank_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              rank_id TEXT NOT NULL,
              changed_ts INTEGER NOT NULL,
              reason TEXT NOT NULL DEFAULT '',
              actor_user_id TEXT,
              note TEXT NOT NULL DEFAULT ''
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_orders (
              order_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              order_type TEXT NOT NULL,
              status TEXT NOT NULL,
              issued_ts INTEGER NOT NULL,
              due_ts INTEGER NOT NULL,
              accepted_ts INTEGER,
              completed_ts INTEGER,
              reward_coins INTEGER NOT NULL DEFAULT 0,
              penalty_debt INTEGER NOT NULL DEFAULT 0,
              season_id TEXT,
              meta_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_orders_daily (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              date_key TEXT NOT NULL,
              completed INTEGER NOT NULL DEFAULT 0,
              late INTEGER NOT NULL DEFAULT 0,
              failed INTEGER NOT NULL DEFAULT 0,
              forfeited INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (guild_id, user_id, date_key)
            );
            """)

            await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_v3_orders_daily_user_date
            ON v3_orders_daily(guild_id, user_id, date_key);
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_daily_challenges (
              challenge_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              date_key TEXT NOT NULL,
              challenge_type TEXT NOT NULL,
              progress_current INTEGER NOT NULL DEFAULT 0,
              progress_target INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'active',
              reward_json TEXT NOT NULL DEFAULT '{}',
              season_id TEXT,
              created_ts INTEGER NOT NULL,
              completed_ts INTEGER
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_longterm_goals (
              goal_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              goal_type TEXT NOT NULL,
              title TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              is_hidden INTEGER NOT NULL DEFAULT 0,
              progress_current INTEGER NOT NULL DEFAULT 0,
              progress_target INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'active',
              reward_json TEXT NOT NULL DEFAULT '{}',
              season_id TEXT,
              created_ts INTEGER NOT NULL,
              completed_ts INTEGER
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_achievements (
              achievement_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description_public TEXT NOT NULL DEFAULT '',
              is_hidden INTEGER NOT NULL DEFAULT 0,
              criteria_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_user_achievements (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              achievement_id TEXT NOT NULL,
              unlocked_ts INTEGER NOT NULL,
              season_id TEXT,
              PRIMARY KEY (guild_id, user_id, achievement_id)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_items (
              item_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              rarity TEXT NOT NULL DEFAULT 'common',
              price_coins INTEGER NOT NULL DEFAULT 0,
              is_seasonal INTEGER NOT NULL DEFAULT 0,
              season_id TEXT,
              metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_user_inventory (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              item_id TEXT NOT NULL,
              qty INTEGER NOT NULL DEFAULT 1,
              acquired_ts INTEGER NOT NULL,
              acquired_source TEXT NOT NULL DEFAULT '',
              is_equipped INTEGER NOT NULL DEFAULT 0,
              meta_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY (guild_id, user_id, item_id)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_transactions (
              txn_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              direction TEXT NOT NULL,
              amount INTEGER NOT NULL,
              reason_code TEXT NOT NULL,
              ref_type TEXT,
              ref_id TEXT,
              season_id TEXT,
              flags_json TEXT NOT NULL DEFAULT '[]',
              created_ts INTEGER NOT NULL
            );
            """)

            await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_v3_transactions_user_time
            ON v3_transactions(guild_id, user_id, created_ts);
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_transaction_summaries (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              period_type TEXT NOT NULL,
              period_key TEXT NOT NULL,
              earned_total INTEGER NOT NULL DEFAULT 0,
              spent_total INTEGER NOT NULL DEFAULT 0,
              net_total INTEGER NOT NULL DEFAULT 0,
              top_sources_json TEXT NOT NULL DEFAULT '{}',
              top_sinks_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY (guild_id, user_id, period_type, period_key)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_seasons (
              season_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              name TEXT NOT NULL,
              start_ts INTEGER NOT NULL,
              end_ts INTEGER NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 0,
              meta_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_user_season_stats (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              season_id TEXT NOT NULL,
              season_currency_balance INTEGER NOT NULL DEFAULT 0,
              season_currency_earned INTEGER NOT NULL DEFAULT 0,
              season_msg_count INTEGER NOT NULL DEFAULT 0,
              season_voice_seconds INTEGER NOT NULL DEFAULT 0,
              season_was_points INTEGER NOT NULL DEFAULT 0,
              season_activity_xp_hidden INTEGER NOT NULL DEFAULT 0,
              season_orders_completed INTEGER NOT NULL DEFAULT 0,
              season_orders_failed INTEGER NOT NULL DEFAULT 0,
              season_tasks_completed INTEGER NOT NULL DEFAULT 0,
              updated_at INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (guild_id, user_id, season_id)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_leaderboard_snapshots (
              snapshot_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              scope TEXT NOT NULL,
              scope_key TEXT NOT NULL,
              category TEXT NOT NULL,
              generated_ts INTEGER NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}'
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_admin_notes (
              note_id INTEGER PRIMARY KEY AUTOINCREMENT,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              author_user_id TEXT NOT NULL,
              note TEXT NOT NULL,
              created_ts INTEGER NOT NULL
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_user_flags (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              warnings_count INTEGER NOT NULL DEFAULT 0,
              disciplines_count INTEGER NOT NULL DEFAULT 0,
              safeword_applied INTEGER NOT NULL DEFAULT 0,
              last_warning_ts INTEGER,
              meta_json TEXT NOT NULL DEFAULT '{}',
              PRIMARY KEY (guild_id, user_id)
            );
            """)

            await self.execute("""
            CREATE TABLE IF NOT EXISTS v3_privacy_requests (
              request_id TEXT PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              request_type TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              created_ts INTEGER NOT NULL,
              closed_ts INTEGER
            );
            """)

        except Exception as e:
            print(f"Database migration error: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise

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

    # =========================
    # V3 Helper Methods
    # =========================

    async def ensure_v3_guild(self, gid: int, name_cache: str | None = None):
        """Ensure v3_guilds row exists."""
        assert self.conn
        import time
        now = int(time.time())
        await self.execute(
            "INSERT OR IGNORE INTO v3_guilds(guild_id, created_at, name_cache) VALUES(?, ?, ?)",
            (str(gid), now, name_cache)
        )

    async def ensure_v3_user(self, gid: int, uid: int, join_ts: int | None = None):
        """Ensure v3_users row exists."""
        assert self.conn
        import time
        now = int(time.time())
        join = join_ts if join_ts is not None else now
        await self.execute(
            "INSERT OR IGNORE INTO v3_users(guild_id, user_id, created_at, join_ts) VALUES(?, ?, ?, ?)",
            (str(gid), str(uid), now, join)
        )

    async def v3_set_last_seen(self, gid: int, uid: int, ts: int):
        """Update last_seen_ts in v3_users."""
        assert self.conn
        await self.execute(
            "UPDATE v3_users SET last_seen_ts=? WHERE guild_id=? AND user_id=?",
            (ts, str(gid), str(uid))
        )

    async def v3_bump_message_daily(self, gid: int, uid: int, date_key: str, ts: int, inc: int = 1):
        """Bump message count for a user on a specific date."""
        assert self.conn
        await self.execute(
            """INSERT INTO v3_activity_daily(guild_id, user_id, date_key, message_count, last_msg_ts, first_msg_ts)
               VALUES(?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, date_key) DO UPDATE SET
                 message_count=message_count+?,
                 last_msg_ts=?,
                 first_msg_ts=COALESCE(first_msg_ts, ?)""",
            (str(gid), str(uid), date_key, inc, ts, ts, inc, ts, ts)
        )

    async def v3_bump_reaction_daily(self, gid: int, uid: int, date_key: str, ts: int, inc: int = 1):
        """Bump reaction count for a user on a specific date."""
        assert self.conn
        await self.execute(
            """INSERT INTO v3_activity_daily(guild_id, user_id, date_key, reaction_count)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, date_key) DO UPDATE SET reaction_count=reaction_count+?""",
            (str(gid), str(uid), date_key, inc, inc)
        )

    async def v3_add_voice_seconds_daily(self, gid: int, uid: int, date_key: str, seconds: int, ts: int):
        """Add voice seconds for a user on a specific date."""
        assert self.conn
        await self.execute(
            """INSERT INTO v3_activity_daily(guild_id, user_id, date_key, voice_seconds, last_voice_ts)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, date_key) DO UPDATE SET
                 voice_seconds=voice_seconds+?,
                 last_voice_ts=?""",
            (str(gid), str(uid), date_key, seconds, ts, seconds, ts)
        )

    async def v3_track_message(self, gid: int, uid: int, date_key: str, ts: int, inc: int = 1, commit: bool = True):
        """Combined helper: ensures v3_user exists, updates last_seen_ts, and bumps message count."""
        assert self.conn
        import time
        if commit:
            async with self.transaction():
                await self._v3_track_message_internal(gid, uid, date_key, ts, inc)
        else:
            await self._v3_track_message_internal(gid, uid, date_key, ts, inc)

    async def _v3_track_message_internal(self, gid: int, uid: int, date_key: str, ts: int, inc: int):
        """Internal helper for v3_track_message (no commit handling)."""
        import time
        now = int(time.time())
        # Ensure v3_user exists
        await self.execute(
            "INSERT OR IGNORE INTO v3_users(guild_id, user_id, created_at, join_ts) VALUES(?, ?, ?, ?)",
            (str(gid), str(uid), ts, ts),
            commit=False
        )
        # Update last_seen_ts
        await self.execute(
            "UPDATE v3_users SET last_seen_ts=? WHERE guild_id=? AND user_id=?",
            (ts, str(gid), str(uid)),
            commit=False
        )
        # Bump message count
        await self.execute(
            """INSERT INTO v3_activity_daily(guild_id, user_id, date_key, message_count, last_msg_ts, first_msg_ts)
               VALUES(?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, date_key) DO UPDATE SET
                 message_count=message_count+?,
                 last_msg_ts=?,
                 first_msg_ts=COALESCE(first_msg_ts, ?)""",
            (str(gid), str(uid), date_key, inc, ts, ts, inc, ts, ts),
            commit=False
        )

    async def v3_track_reaction(self, gid: int, uid: int, date_key: str, ts: int, inc: int = 1, commit: bool = True):
        """Combined helper: ensures v3_user exists, updates last_seen_ts, and bumps reaction count."""
        assert self.conn
        if commit:
            async with self.transaction():
                await self._v3_track_reaction_internal(gid, uid, date_key, ts, inc)
        else:
            await self._v3_track_reaction_internal(gid, uid, date_key, ts, inc)

    async def _v3_track_reaction_internal(self, gid: int, uid: int, date_key: str, ts: int, inc: int):
        """Internal helper for v3_track_reaction (no commit handling)."""
        import time
        # Ensure v3_user exists
        await self.execute(
            "INSERT OR IGNORE INTO v3_users(guild_id, user_id, created_at, join_ts) VALUES(?, ?, ?, ?)",
            (str(gid), str(uid), ts, ts),
            commit=False
        )
        # Update last_seen_ts
        await self.execute(
            "UPDATE v3_users SET last_seen_ts=? WHERE guild_id=? AND user_id=?",
            (ts, str(gid), str(uid)),
            commit=False
        )
        # Bump reaction count
        await self.execute(
            """INSERT INTO v3_activity_daily(guild_id, user_id, date_key, reaction_count)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, date_key) DO UPDATE SET reaction_count=reaction_count+?""",
            (str(gid), str(uid), date_key, inc, inc),
            commit=False
        )

    async def v3_track_voice_seconds(self, gid: int, uid: int, date_key: str, ts: int, seconds: int, commit: bool = True):
        """Combined helper: ensures v3_user exists, updates last_seen_ts, and adds voice seconds."""
        assert self.conn
        if commit:
            async with self.transaction():
                await self._v3_track_voice_seconds_internal(gid, uid, date_key, ts, seconds)
        else:
            await self._v3_track_voice_seconds_internal(gid, uid, date_key, ts, seconds)

    async def _v3_track_voice_seconds_internal(self, gid: int, uid: int, date_key: str, ts: int, seconds: int):
        """Internal helper for v3_track_voice_seconds (no commit handling)."""
        import time
        # Ensure v3_user exists
        await self.execute(
            "INSERT OR IGNORE INTO v3_users(guild_id, user_id, created_at, join_ts) VALUES(?, ?, ?, ?)",
            (str(gid), str(uid), ts, ts),
            commit=False
        )
        # Update last_seen_ts
        await self.execute(
            "UPDATE v3_users SET last_seen_ts=? WHERE guild_id=? AND user_id=?",
            (ts, str(gid), str(uid)),
            commit=False
        )
        # Add voice seconds
        await self.execute(
            """INSERT INTO v3_activity_daily(guild_id, user_id, date_key, voice_seconds, last_voice_ts)
               VALUES(?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, date_key) DO UPDATE SET
                 voice_seconds=voice_seconds+?,
                 last_voice_ts=?""",
            (str(gid), str(uid), date_key, seconds, ts, seconds, ts),
            commit=False
        )

    async def v3_apply_coins_delta(
        self, gid: int, uid: int, delta: int, counts_toward_lce: bool, reason_code: str,
        ref_type: str | None = None, ref_id: str | None = None, season_id: str | None = None,
        flags_json: str = "[]", commit: bool = True
    ):
        """Apply coins delta and record transaction."""
        assert self.conn
        import time
        import uuid
        now = int(time.time())
        txn_id = str(uuid.uuid4())
        direction = "credit" if delta > 0 else "debit"
        amount = abs(delta)

        # Record transaction
        await self.execute(
            """INSERT INTO v3_transactions(txn_id, guild_id, user_id, direction, amount, reason_code, ref_type, ref_id, season_id, flags_json, created_ts)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (txn_id, str(gid), str(uid), direction, amount, reason_code, ref_type, ref_id, season_id, flags_json, now),
            commit=commit
        )

        # Update progression_core
        if counts_toward_lce and delta > 0:
            await self.execute(
                """INSERT INTO v3_progression_core(guild_id, user_id, coins_balance, coins_lifetime_earned, updated_at)
                   VALUES(?, ?, ?, ?, ?)
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET
                     coins_balance=coins_balance+?,
                     coins_lifetime_earned=coins_lifetime_earned+?,
                     updated_at=?""",
                (str(gid), str(uid), delta, delta, now, delta, delta, now),
                commit=commit
            )
        else:
            await self.execute(
                """INSERT INTO v3_progression_core(guild_id, user_id, coins_balance, updated_at)
                   VALUES(?, ?, ?, ?)
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET
                     coins_balance=coins_balance+?,
                     updated_at=?""",
                (str(gid), str(uid), delta, now, delta, now),
                commit=commit
            )

    async def v3_recompute_was_7d(self, gid: int, uid: int, last_7_date_keys: list[str]) -> int:
        """Recompute 7-day WAS from v3_activity_daily and store in v3_progression_core."""
        assert self.conn
        import time
        if not last_7_date_keys:
            return 0

        placeholders = ",".join(["?"] * len(last_7_date_keys))
        row = await self.fetchone(
            f"""
            SELECT
              COALESCE(SUM(message_count), 0) AS msg,
              COALESCE(SUM(reaction_count), 0) AS react,
              COALESCE(SUM(voice_seconds), 0) AS voice_sec
            FROM v3_activity_daily
            WHERE guild_id=? AND user_id=? AND date_key IN ({placeholders})
            """,
            [str(gid), str(uid)] + last_7_date_keys,
        )

        msg = int(row["msg"]) if row else 0
        react = int(row["react"]) if row else 0
        voice_sec = int(row["voice_sec"]) if row else 0

        voice_minutes = voice_sec // 60
        was = int(msg * 3 + react * 1 + min(voice_minutes, 600) * 2)

        now = int(time.time())
        await self.execute(
            """INSERT INTO v3_progression_core(guild_id, user_id, was_7d_cached, updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET
                 was_7d_cached=?,
                 updated_at=?""",
            (str(gid), str(uid), was, now, was, now)
        )
        return was

    async def v3_recompute_obedience_7d(self, gid: int, uid: int, last_7_date_keys: list[str]) -> int:
        """Recompute obedience 7-day window and store in v3_progression_core."""
        assert self.conn
        import time
        if not last_7_date_keys:
            return 0

        placeholders = ",".join(["?"] * len(last_7_date_keys))
        row = await self.fetchone(
            f"""
            SELECT
              COALESCE(SUM(completed), 0) AS comp,
              COALESCE(SUM(late), 0) AS late,
              COALESCE(SUM(failed), 0) AS failed,
              COALESCE(SUM(forfeited), 0) AS forfeit
            FROM v3_orders_daily
            WHERE guild_id=? AND user_id=? AND date_key IN ({placeholders})
            """,
            [str(gid), str(uid)] + last_7_date_keys,
        )

        comp = int(row["comp"]) if row else 0
        late = int(row["late"]) if row else 0
        failed = int(row["failed"]) if row else 0
        forfeit = int(row["forfeit"]) if row else 0

        obedience = comp - (late + failed + forfeit)

        now = int(time.time())
        await self.execute(
            """INSERT INTO v3_progression_core(guild_id, user_id, orders_completed_7d, orders_late_7d, orders_failed_7d, orders_forfeited_7d, obedience_7d_cached, updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET
                 orders_completed_7d=?,
                 orders_late_7d=?,
                 orders_failed_7d=?,
                 orders_forfeited_7d=?,
                 obedience_7d_cached=?,
                 updated_at=?""",
            (str(gid), str(uid), comp, late, failed, forfeit, obedience, now,
             comp, late, failed, forfeit, obedience, now)
        )
        return obedience

    async def v3_grant_start_balance_once(self, gid: int, uid: int, amount: int):
        """Grant start balance exactly once per user (idempotent)."""
        assert self.conn
        import time
        if amount <= 0:
            return
        
        async with self.transaction():
            # Ensure progression_core row exists
            await self.execute(
                """INSERT OR IGNORE INTO v3_progression_core(guild_id, user_id, updated_at)
                   VALUES(?, ?, ?)""",
                (str(gid), str(uid), int(time.time())),
                commit=False
            )
            
            # Check if already granted
            row = await self.fetchone(
                "SELECT start_balance_granted FROM v3_progression_core WHERE guild_id=? AND user_id=?",
                (str(gid), str(uid))
            )
            
            if row and int(row["start_balance_granted"] or 0) != 0:
                return  # Already granted
            
            # Grant the balance
            await self.v3_apply_coins_delta(
                gid, uid, delta=amount, counts_toward_lce=True,
                reason_code="start_balance", ref_type="system",
                commit=False
            )
            
            # Mark as granted
            await self.execute(
                "UPDATE v3_progression_core SET start_balance_granted=1 WHERE guild_id=? AND user_id=?",
                (str(gid), str(uid)),
                commit=False
            )

    async def v3_wipe_user(self, gid: int, uid: int):
        """Hard delete all v3_* rows for a user (privacy-safe)."""
        assert self.conn
        v3_tables = [
            "v3_users", "v3_user_profile", "v3_activity_daily", "v3_voice_sessions",
            "v3_progression_core", "v3_rank_history", "v3_orders_daily",
            "v3_orders", "v3_daily_challenges", "v3_longterm_goals",
            "v3_user_achievements", "v3_user_inventory", "v3_user_season_stats",
            "v3_admin_notes", "v3_user_flags", "v3_privacy_requests",
            "v3_transactions", "v3_transaction_summaries"
        ]
        for table in v3_tables:
            try:
                await self.execute(f"DELETE FROM {table} WHERE guild_id=? AND user_id=?", (str(gid), str(uid)))
            except Exception:
                pass  # Table might not exist, ignore

