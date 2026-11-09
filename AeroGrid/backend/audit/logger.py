"""AeroGrid Audit Engine.

Provides an immutable, high-throughput audit logger backed by SQLite WAL mode
for real-time UTM decision tracing, with analytical export to Apache Parquet
via Pandas and PyArrow.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Union

logger = logging.getLogger("aerogrid.audit")


class AuditEngine:
    """Enterprise-grade audit logger using SQLite Write-Ahead Logging (WAL).

    Guarantees strict auditability for UTM agent decisions, conflict resolution,
    and regulatory policy provenance.
    """

    TABLE_NAME = "audit_logs"

    def __init__(self, db_path: str = "backend/audit/aerogrid_audit.db") -> None:
        """Initialize the SQLite database with WAL mode and create the audit table.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = str(Path(db_path).resolve())
        # Ensure target directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Open a SQLite connection configured with WAL and busy timeouts."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # WAL mode configuration for concurrent multi-agent read/write
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        """Create the audit table and performance indices if they do not exist."""
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
            event_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            context_hash TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            decision_justification TEXT NOT NULL,
            retrieved_policy_sources TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            timestamp TEXT NOT NULL,
            parent_decision_id TEXT,
            target_drone_id TEXT
        );
        """
        idx_context = f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_context ON {self.TABLE_NAME}(context_hash);"
        idx_parent = f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_parent ON {self.TABLE_NAME}(parent_decision_id);"
        idx_agent = f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_agent ON {self.TABLE_NAME}(agent_id);"
        idx_drone = f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_drone ON {self.TABLE_NAME}(target_drone_id);"

        with self._get_connection() as conn:
            conn.execute(create_table_sql)
            # Schema migration check: ensure target_drone_id exists if table predated column
            cur = conn.execute(f"PRAGMA table_info({self.TABLE_NAME});")
            existing_cols = [row["name"] for row in cur.fetchall()]
            if "target_drone_id" not in existing_cols:
                conn.execute(f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN target_drone_id TEXT;")

            conn.execute(idx_context)
            conn.execute(idx_parent)
            conn.execute(idx_agent)
            conn.execute(idx_drone)
            conn.commit()

        logger.info("AuditEngine initialized at %s with PRAGMA journal_mode=WAL", self.db_path)

    def insert_log(
        self,
        agent_id: str,
        context_hash: str,
        recommended_action: str,
        decision_justification: str,
        retrieved_policy_sources: Union[List[str], List[dict], str],
        confidence_score: float,
        timestamp: Optional[str] = None,
        parent_decision_id: Optional[str] = None,
        event_id: Optional[str] = None,
        target_drone_id: Optional[str] = None,
    ) -> str:
        """Insert an immutable decision log into SQLite WAL.

        Args:
            agent_id: Identifier of the reporting agent (e.g. 'aviation_agent').
            context_hash: Cryptographic SHA-256 hash of the simulation state.
            recommended_action: Categorical action or maneuver string.
            decision_justification: Natural language / analytical rationale.
            retrieved_policy_sources: Citations used to substantiate recommendation.
            confidence_score: Float between 0.0 and 1.0.
            timestamp: ISO-8601 UTC timestamp string (auto-generated if omitted).
            parent_decision_id: Optional reference linking child agent logs to
                                final coordination decision.
            event_id: Unique event ID (auto-generated if omitted).
            target_drone_id: Optional UAS identifier (e.g. 'UAS_CARGO_DXB_104').

        Returns:
            The event_id of the committed log record.
        """
        if event_id is None:
            event_id = f"evt_{uuid.uuid4().hex}"

        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Normalize retrieved_policy_sources into a JSON string
        if isinstance(retrieved_policy_sources, (list, tuple, dict)):
            policy_sources_str = json.dumps(retrieved_policy_sources, ensure_ascii=False)
        else:
            policy_sources_str = str(retrieved_policy_sources)

        insert_sql = f"""
        INSERT INTO {self.TABLE_NAME} (
            event_id,
            agent_id,
            context_hash,
            recommended_action,
            decision_justification,
            retrieved_policy_sources,
            confidence_score,
            timestamp,
            parent_decision_id,
            target_drone_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """

        params = (
            event_id,
            agent_id,
            context_hash,
            recommended_action,
            decision_justification,
            policy_sources_str,
            float(confidence_score),
            timestamp,
            parent_decision_id,
            target_drone_id,
        )

        with self._get_connection() as conn:
            conn.execute(insert_sql, params)
            conn.commit()

        logger.debug("Logged event %s for agent %s (context=%s)", event_id, agent_id, context_hash[:8])
        return event_id

    def export_to_parquet(
        self,
        output_path: str,
        filter_agent_id: Optional[str] = None,
    ) -> str:
        """Export audit records from SQLite WAL into Apache Parquet format.

        Utilizes Pandas and PyArrow for high-performance columnar persistence
        and downstream safety analytics.

        Args:
            output_path: Target .parquet file path.
            filter_agent_id: Optional agent ID filter.

        Returns:
            Absolute path to the exported Parquet file.
        """
        try:
            import pandas as pd
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Pandas and PyArrow are required for Parquet export. "
                "Install them via: pip install pandas pyarrow"
            ) from exc

        target_file = Path(output_path).resolve()
        target_file.parent.mkdir(parents=True, exist_ok=True)

        query = f"SELECT * FROM {self.TABLE_NAME}"
        params: List[Any] = []
        if filter_agent_id:
            query += " WHERE agent_id = ?"
            params.append(filter_agent_id)
        query += " ORDER BY timestamp ASC;"

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params if params else None)

        if not df.empty:
            # Cast types explicitly for optimal Parquet compression & schema
            df["confidence_score"] = df["confidence_score"].astype("float64")
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        df.to_parquet(str(target_file), engine="pyarrow", index=False)
        logger.info("Successfully exported %d audit records to %s", len(df), target_file)
        return str(target_file)

    def get_log(self, event_id: str) -> Optional[dict]:
        """Fetch a single audit log entry by event_id."""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE event_id = ?;"
        with self._get_connection() as conn:
            cur = conn.execute(query, (event_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_audit_trail_by_context(self, context_hash: str) -> List[dict]:
        """Retrieve all decision records associated with a specific simulation state."""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE context_hash = ? ORDER BY timestamp ASC;"
        with self._get_connection() as conn:
            cur = conn.execute(query, (context_hash,))
            return [dict(row) for row in cur.fetchall()]

    def get_all_logs(self) -> List[dict]:
        """Retrieve all audit logs ordered by timestamp."""
        query = f"SELECT * FROM {self.TABLE_NAME} ORDER BY timestamp ASC;"
        with self._get_connection() as conn:
            cur = conn.execute(query)
            return [dict(row) for row in cur.fetchall()]

