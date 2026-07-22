import sqlite3
from typing import Optional, Dict, Any
from config import logger

DB_PATH = "tasks.db"

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                url TEXT,
                filename TEXT,
                status TEXT,
                description TEXT,
                start_time TEXT,
                end_time TEXT,
                timescale TEXT,
                ffmpeg_postprocessor_args TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}
        if "ffmpeg_postprocessor_args" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN ffmpeg_postprocessor_args TEXT DEFAULT ''")
        conn.commit()
    logger.info("SQLite database initialized successfully.")

def update_task_db(task_id: str, status: str, description: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = ?, description = ? WHERE id = ?",
            (status, description, task_id)
        )
        conn.commit()

def get_task_db(task_id: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT status, description FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None