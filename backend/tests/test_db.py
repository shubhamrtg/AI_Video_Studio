import os
import sqlite3
import pytest
from app.db.database import run_migrations

def test_data_preservation_and_migrations(tmp_path):
    db_path = tmp_path / "test.db"
    
    # 1. Run migrations initially
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn)
        conn.execute("INSERT INTO projects (id, excel_id, video_idea, target_duration, aspect_ratio, status) VALUES ('p1', 'e1', 'idea1', 60, '16:9', 'QUEUED')")
        conn.commit()

    # 2. Close and reinitialize
    with sqlite3.connect(db_path) as conn:
        run_migrations(conn)
        
    # 3. Confirm records still exist
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT video_idea FROM projects WHERE id = 'p1'").fetchone()
        assert row is not None
        assert row[0] == "idea1"
