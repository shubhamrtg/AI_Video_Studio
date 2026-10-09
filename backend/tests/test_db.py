import os
import sqlite3
import pytest
from app.db.database import run_migrations

def test_data_preservation_and_migrations(tmp_path):
    db_path = tmp_path / "test.db"
    
    # Simulate an old v1 database BEFORE migrations framework was robustly applied
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                master_prompt TEXT,
                target_duration INTEGER,
                aspect_ratio TEXT,
                status TEXT,
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
                status TEXT,
                video_url TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY
            )
        """)
        # Insert legacy data
        cursor.execute("INSERT INTO projects (id, master_prompt, target_duration, aspect_ratio, status) VALUES ('p1', 'Legacy idea', 30, '16:9', 'QUEUED')")
        cursor.execute("INSERT INTO jobs (id) VALUES ('j1')")
        conn.commit()

    # 1. Run migrations
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn)

    # 2. Confirm records exist and mapped correctly
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT video_idea FROM projects WHERE id = 'p1'").fetchone()
        assert row is not None
        assert row["video_idea"] == "Legacy idea"
        
        # New columns should exist and be NULL or empty
        project_columns = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        assert "excel_id" in project_columns
        
        shot_columns = [r[1] for r in conn.execute("PRAGMA table_info(shots)").fetchall()]
        assert "audio_requirements" in shot_columns
        
        # Verify jobs table was retained (not dropped)
        jobs_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
        assert jobs_table is not None

    # 3. Close and reinitialize (Idempotency)
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn)
        
    # 4. Check schema version
    with sqlite3.connect(db_path) as conn:
        version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert version == 2
