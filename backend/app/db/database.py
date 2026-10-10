import sqlite3
import os
from contextlib import contextmanager
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def get_db_path():
    return os.path.join(settings.DATA_DIR, "app.db")

def run_migrations(conn):
    cursor = conn.cursor()
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY
        )
    """)
    
    version_row = cursor.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    current_version = version_row[0] if version_row and version_row[0] is not None else 0

    if current_version < 1:
        try:
            logger.info("Applying migration 1")
            cursor.execute("BEGIN TRANSACTION")
            # Ensure base tables exist (might be from old non-versioned DB)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    master_prompt TEXT,
                    target_duration INTEGER,
                    aspect_ratio TEXT,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    shot_number INTEGER,
                    duration INTEGER,
                    description TEXT,
                    camera TEXT,
                    subject TEXT,
                    action TEXT,
                    lighting TEXT,
                    style TEXT,
                    continuity_notes TEXT,
                    negative_prompt TEXT,
                    status TEXT,
                    video_url TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
            """)
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (1)")
            conn.commit()
            current_version = 1
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration 1 failed: {e}")
            raise

    if current_version < 2:
        try:
            logger.info("Applying migration 2: Evolve schema")
            cursor.execute("BEGIN TRANSACTION")
            
            # Create a backup of legacy tables just in case, or rather just leave jobs intact
            # Add new columns to projects if they don't exist
            # SQLite ALTER TABLE ADD COLUMN
            project_columns = [row[1] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
            
            if "excel_id" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN excel_id TEXT")
            if "video_idea" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN video_idea TEXT")
                # Migrate data
                if "master_prompt" in project_columns:
                    cursor.execute("UPDATE projects SET video_idea = master_prompt")
            if "visual_style" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN visual_style TEXT")
            if "language" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN language TEXT")
            if "voice_style" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN voice_style TEXT")
            if "target_platform" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN target_platform TEXT")
            if "priority" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN priority TEXT")
            if "script_text" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN script_text TEXT")
            if "final_video_url" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN final_video_url TEXT")
            if "error" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN error TEXT")

            shot_columns = [row[1] for row in cursor.execute("PRAGMA table_info(shots)").fetchall()]
            if "audio_requirements" not in shot_columns:
                cursor.execute("ALTER TABLE shots ADD COLUMN audio_requirements TEXT")
            if "narration_text" not in shot_columns:
                cursor.execute("ALTER TABLE shots ADD COLUMN narration_text TEXT")
                
            # Removed destructive DROP TABLE IF EXISTS jobs
            
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (2)")
            conn.commit()
            current_version = 2
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration 2 failed: {e}")
            raise

    if current_version < 3:
        try:
            logger.info("Applying migration 3: Add audio_policy")
            cursor.execute("BEGIN TRANSACTION")
            
            project_columns = [row[1] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
            if "audio_policy" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN audio_policy TEXT DEFAULT 'silent'")
                
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (3)")
            conn.commit()
            current_version = 3
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration 3 failed: {e}")
            raise

    if current_version < 4:
        try:
            logger.info("Applying migration 4: Add sync tracking")
            cursor.execute("BEGIN TRANSACTION")
            project_columns = [row[1] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
            if "sync_status" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN sync_status TEXT DEFAULT 'PENDING'")
            if "sync_error" not in project_columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN sync_error TEXT")
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (4)")
            conn.commit()
            current_version = 4
        except Exception as e:
            conn.rollback()
            logger.error(f"Migration 4 failed: {e}")
            raise

def init_db():
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    with sqlite3.connect(get_db_path()) as conn:
        run_migrations(conn)

@contextmanager
def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
