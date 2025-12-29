from __future__ import annotations
import json
import csv
import io
from typing import Optional, List, Dict, Any
from datetime import datetime
from core.db import Database
from core.utility import now_ts

class AuditService:
    """Service for managing audit logs with enhanced features."""
    
    def __init__(self, db: Database):
        self.db = db
        self.retention_days = 90  # Default retention
    
    async def log_action(
        self,
        guild_id: int,
        actor_id: Optional[int],
        target_user_id: Optional[int],
        action: str,
        meta: Optional[Dict[str, Any]] = None
    ):
        """Log an audit action."""
        meta_json = json.dumps(meta or {})
        await self.db.audit(guild_id, actor_id, target_user_id, action, meta_json, now_ts())
    
    async def get_audit_logs(
        self,
        guild_id: int,
        actor_id: Optional[int] = None,
        target_user_id: Optional[int] = None,
        action: Optional[str] = None,
        since_ts: Optional[int] = None,
        until_ts: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit logs with filters."""
        params = [guild_id]
        where_clauses = ["guild_id=?"]
        
        if actor_id:
            where_clauses.append("actor_id=?")
            params.append(actor_id)
        
        if target_user_id:
            where_clauses.append("target_user_id=?")
            params.append(target_user_id)
        
        if action:
            where_clauses.append("action=?")
            params.append(action)
        
        if since_ts:
            where_clauses.append("created_ts>=?")
            params.append(since_ts)
        
        if until_ts:
            where_clauses.append("created_ts<=?")
            params.append(until_ts)
        
        where_sql = " AND ".join(where_clauses)
        params.append(limit)
        
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM audit_log
            WHERE {where_sql}
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            tuple(params)
        )
        
        result = []
        for row in rows:
            try:
                meta = json.loads(row["meta"] or "{}")
            except Exception:
                meta = {}
            
            result.append({
                "id": int(row["id"]),
                "guild_id": int(row["guild_id"]),
                "actor_id": int(row["actor_id"]) if row["actor_id"] else None,
                "target_user_id": int(row["target_user_id"]) if row["target_user_id"] else None,
                "action": str(row["action"]),
                "meta": meta,
                "created_ts": int(row["created_ts"])
            })
        
        return result
    
    async def export_to_csv(
        self,
        guild_id: int,
        since_ts: Optional[int] = None,
        until_ts: Optional[int] = None
    ) -> str:
        """Export audit logs to CSV format."""
        logs = await self.get_audit_logs(
            guild_id=guild_id,
            since_ts=since_ts,
            until_ts=until_ts,
            limit=10000
        )
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["ID", "Timestamp", "Actor ID", "Target User ID", "Action", "Meta"])
        
        # Rows
        for log in logs:
            writer.writerow([
                log["id"],
                datetime.fromtimestamp(log["created_ts"]).isoformat(),
                log["actor_id"] or "",
                log["target_user_id"] or "",
                log["action"],
                json.dumps(log["meta"])
            ])
        
        return output.getvalue()
    
    async def export_to_json(
        self,
        guild_id: int,
        since_ts: Optional[int] = None,
        until_ts: Optional[int] = None
    ) -> str:
        """Export audit logs to JSON format."""
        logs = await self.get_audit_logs(
            guild_id=guild_id,
            since_ts=since_ts,
            until_ts=until_ts,
            limit=10000
        )
        
        return json.dumps(logs, indent=2)
    
    async def get_statistics(
        self,
        guild_id: int,
        since_ts: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get audit log statistics."""
        where_clause = "guild_id=?"
        params = [guild_id]
        
        if since_ts:
            where_clause += " AND created_ts>=?"
            params.append(since_ts)
        
        # Total count
        total_row = await self.db.fetchone(
            f"SELECT COUNT(*) as count FROM audit_log WHERE {where_clause}",
            tuple(params)
        )
        total = int(total_row["count"]) if total_row else 0
        
        # Action breakdown
        action_rows = await self.db.fetchall(
            f"""
            SELECT action, COUNT(*) as count
            FROM audit_log
            WHERE {where_clause}
            GROUP BY action
            ORDER BY count DESC
            """,
            tuple(params)
        )
        
        action_breakdown = {
            str(row["action"]): int(row["count"])
            for row in action_rows
        }
        
        # Actor breakdown (top 10)
        actor_rows = await self.db.fetchall(
            f"""
            SELECT actor_id, COUNT(*) as count
            FROM audit_log
            WHERE {where_clause} AND actor_id IS NOT NULL
            GROUP BY actor_id
            ORDER BY count DESC
            LIMIT 10
            """,
            tuple(params)
        )
        
        actor_breakdown = {
            int(row["actor_id"]): int(row["count"])
            for row in actor_rows
        }
        
        return {
            "total": total,
            "action_breakdown": action_breakdown,
            "top_actors": actor_breakdown
        }
    
    async def prune_old_logs(self, retention_days: Optional[int] = None):
        """Remove audit logs older than retention period."""
        days = retention_days or self.retention_days
        cutoff_ts = now_ts() - (days * 86400)
        await self.db.execute(
            "DELETE FROM audit_log WHERE created_ts < ?",
            (cutoff_ts,)
        )

