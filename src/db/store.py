"""SQLite persistence for pipeline runs and exceptions (PostgreSQL-ready DSN)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    source_file TEXT,
    started_at TEXT,
    finished_at TEXT,
    input_row_count INTEGER,
    exception_count INTEGER,
    recon_status TEXT,
    recon_json TEXT,
    artifacts_json TEXT
);

CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    row_index INTEGER,
    error_code TEXT,
    field TEXT,
    raw_value TEXT,
    message TEXT,
    severity TEXT,
    description TEXT,
    remediation TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_exceptions_run ON exceptions(run_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_code ON exceptions(error_code);
CREATE INDEX IF NOT EXISTS idx_exceptions_severity ON exceptions(severity);
"""


class DatabaseStore:
    """
    Lightweight store. Default: SQLite file.

    For PostgreSQL, pass a SQLAlchemy-style URL such as
    postgresql://user:pass@localhost:5432/dq — requires `psycopg2` / `psycopg`.
    SQLite is used when the scheme is missing or `sqlite`.
    """

    def __init__(self, db_url: str = "sqlite:///outputs/dq_pipeline.db") -> None:
        self.db_url = db_url
        self._is_sqlite = db_url.startswith("sqlite:") or "://" not in db_url
        if self._is_sqlite:
            path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
            if path == db_url and not db_url.startswith("sqlite"):
                path = db_url
            self._sqlite_path = Path(path)
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self._sqlite_path = None
        self._ensure_schema()

    def _connect(self):
        if self._is_sqlite:
            conn = sqlite3.connect(self._sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn
        # Optional PostgreSQL path
        try:
            import psycopg2  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "PostgreSQL support requires psycopg2. "
                "Install with: pip install psycopg2-binary"
            ) from exc
        parsed = urlparse(self.db_url)
        return psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            dbname=parsed.path.lstrip("/"),
        )

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            if self._is_sqlite:
                conn.executescript(SCHEMA_SQL)
            else:
                cur = conn.cursor()
                for stmt in SCHEMA_SQL.split(";"):
                    s = stmt.strip()
                    if s:
                        # PostgreSQL: AUTOINCREMENT → SERIAL-ish; keep simple via IDENTITY
                        s = s.replace(
                            "id INTEGER PRIMARY KEY AUTOINCREMENT",
                            "id SERIAL PRIMARY KEY",
                        )
                        cur.execute(s)
                conn.commit()

    def save_run(
        self,
        run_id: str,
        source_file: str,
        started_at: datetime,
        finished_at: datetime,
        input_row_count: int,
        exception_count: int,
        recon_summary: dict[str, Any],
        artifacts: dict[str, Any],
        exceptions: pd.DataFrame,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pipeline_runs
                (run_id, source_file, started_at, finished_at, input_row_count,
                 exception_count, recon_status, recon_json, artifacts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source_file,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    input_row_count,
                    exception_count,
                    recon_summary.get("status"),
                    json.dumps(recon_summary),
                    json.dumps({k: str(v) for k, v in artifacts.items()}),
                ),
            )
            conn.execute("DELETE FROM exceptions WHERE run_id = ?", (run_id,))
            if not exceptions.empty:
                cols = [
                    "row_index",
                    "error_code",
                    "field",
                    "raw_value",
                    "message",
                    "severity",
                    "description",
                    "remediation",
                ]
                for _, row in exceptions.iterrows():
                    conn.execute(
                        """
                        INSERT INTO exceptions
                        (run_id, row_index, error_code, field, raw_value, message,
                         severity, description, remediation)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            int(row["row_index"]) if pd.notna(row["row_index"]) else None,
                            row.get("error_code"),
                            row.get("field"),
                            str(row.get("raw_value", "")),
                            row.get("message"),
                            row.get("severity"),
                            row.get("description"),
                            row.get("remediation"),
                        ),
                    )
            conn.commit()

    def list_runs(self, limit: int = 50) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                """
                SELECT run_id, source_file, started_at, finished_at,
                       input_row_count, exception_count, recon_status
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )

    def load_exceptions(self, run_id: str | None = None) -> pd.DataFrame:
        with self._connect() as conn:
            if run_id:
                return pd.read_sql_query(
                    "SELECT * FROM exceptions WHERE run_id = ? ORDER BY id",
                    conn,
                    params=(run_id,),
                )
            return pd.read_sql_query(
                "SELECT * FROM exceptions ORDER BY id DESC LIMIT 5000",
                conn,
            )

    def latest_run_id(self) -> str | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT run_id FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row[0] if row else None
