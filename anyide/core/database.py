"""Database initialization and management."""

import aiosqlite
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from anyide.logging_config import get_logger

logger = get_logger(__name__)


# Configure SQLite datetime adapters for Python 3.12+
def adapt_datetime_iso(val):
    """Adapt datetime.datetime to timezone-aware ISO 8601 date."""
    return val.isoformat()

def convert_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.fromisoformat(val.decode())

sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("timestamp", convert_datetime)


class Database:
    """Database manager for SQLite."""
    
    def __init__(self, db_path: str = "/data/hostbridge.db"):
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        
        # Ensure data directory exists (only if not in-memory)
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def connect(self):
        """Connect to database and initialize schema."""
        self._connection = await aiosqlite.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        self._connection.row_factory = aiosqlite.Row
        
        # Enable WAL mode for better concurrency
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        
        await self._init_schema()
        logger.info("database_connected", path=self.db_path)
    
    async def close(self):
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            logger.info("database_closed")
    
    async def _init_schema(self):
        """Initialize database schema."""
        # Audit log table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tool_name TEXT NOT NULL,
                tool_category TEXT NOT NULL,
                protocol TEXT NOT NULL,
                request_params TEXT NOT NULL,
                response_body TEXT,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                error_message TEXT,
                hitl_request_id TEXT,
                container_logs TEXT,
                workspace_dir TEXT,
                client_info TEXT
            )
        """)
        
        # Index for common queries
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
            ON audit_log(timestamp DESC)
        """)
        
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_tool 
            ON audit_log(tool_name, tool_category)
        """)
        
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_status 
            ON audit_log(status)
        """)
        
        # Memory graph tables
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'concept',
                tags TEXT NOT NULL DEFAULT '[]',
                metadata TEXT NOT NULL DEFAULT '{}',
                source TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await self._connection.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_nodes_fts USING fts5(
                name, content, tags,
                content='memory_nodes', content_rowid='rowid'
            )
        """)

        await self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_nodes_ai
            AFTER INSERT ON memory_nodes BEGIN
                INSERT INTO memory_nodes_fts(rowid, name, content, tags)
                VALUES (new.rowid, new.name, new.content, new.tags);
            END
        """)

        await self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_nodes_ad
            AFTER DELETE ON memory_nodes BEGIN
                INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, name, content, tags)
                VALUES ('delete', old.rowid, old.name, old.content, old.tags);
            END
        """)

        await self._connection.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_nodes_au
            AFTER UPDATE ON memory_nodes BEGIN
                INSERT INTO memory_nodes_fts(memory_nodes_fts, rowid, name, content, tags)
                VALUES ('delete', old.rowid, old.name, old.content, old.tags);
                INSERT INTO memory_nodes_fts(rowid, name, content, tags)
                VALUES (new.rowid, new.name, new.content, new.tags);
            END
        """)

        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS memory_edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES memory_nodes(id) ON DELETE CASCADE,
                relation TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                valid_from TEXT,
                valid_until TEXT,
                UNIQUE(source_id, target_id, relation)
            )
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_edges_source
            ON memory_edges(source_id)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_edges_target
            ON memory_edges(target_id)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_edges_relation
            ON memory_edges(relation)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_nodes_type
            ON memory_nodes(entity_type)
        """)

        # Plan tables
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS plan_plans (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                on_failure TEXT NOT NULL DEFAULT 'stop',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                started_at TEXT,
                completed_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_plan_plans_status
            ON plan_plans(status)
        """)

        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS plan_tasks (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL REFERENCES plan_plans(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                tool_category TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                depends_on TEXT NOT NULL DEFAULT '[]',
                on_failure TEXT,
                require_hitl INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                output TEXT,
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                execution_level INTEGER NOT NULL DEFAULT 0
            )
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_plan_tasks_plan_id
            ON plan_tasks(plan_id)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_plan_tasks_status
            ON plan_tasks(plan_id, status)
        """)

        # Language module indexing tables
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS language_index_files (
                workspace_dir TEXT NOT NULL,
                path TEXT NOT NULL,
                language TEXT NOT NULL,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (workspace_dir, path)
            )
        """)

        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS language_index_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_dir TEXT NOT NULL,
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                signature TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                parent_name TEXT
            )
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_lang_files_workspace
            ON language_index_files(workspace_dir, path)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_lang_symbols_lookup
            ON language_index_symbols(workspace_dir, name, kind, language)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_lang_symbols_file
            ON language_index_symbols(workspace_dir, file_path)
        """)

        await self._connection.commit()
        logger.info("database_schema_initialized")
    
    @property
    def connection(self) -> aiosqlite.Connection:
        """Get database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        return self._connection
