import sqlite3
import os
from contextlib import contextmanager
from app.core.config import settings

DB_PATH = os.path.join(settings.DATA_DIR, "app.db")

def init_db():
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # We will drop the old tables for this pivot
        cursor.execute("DROP TABLE IF EXISTS shots")
        cursor.execute("DROP TABLE IF EXISTS projects")
        cursor.execute("DROP TABLE IF EXISTS jobs")
        
        cursor.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                excel_id TEXT UNIQUE,
                video_idea TEXT,
                target_duration INTEGER,
                aspect_ratio TEXT,
                visual_style TEXT,
                language TEXT,
                voice_style TEXT,
                target_platform TEXT,
                priority TEXT,
                status TEXT,
                script_text TEXT,
                final_video_url TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE shots (
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
                audio_requirements TEXT,
                narration_text TEXT,
                status TEXT,
                video_url TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        """)
        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
