import pytest
import sqlite3
import os
from app.db.database import get_db, run_migrations
from app.core.config import settings

def test_migration_consistency_detection(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    # Create an inconsistent database
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO schema_migrations (version) VALUES (4)")
    
    # Missing tables
    with pytest.raises(RuntimeError, match="claims version 4 but base tables are missing"):
        run_migrations(conn)
        
    # Create base tables but missing columns
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE shots (id TEXT PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="claims version >= 2 but is missing columns"):
        run_migrations(conn)

    conn.close()
    
    # Now test the auto-repair logic with the specific required scenario
    os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO schema_migrations (version) VALUES (4)")
    
    # Fill in v1 and v2 columns, but MISS v3 (audio_policy) AND v4 columns (sync_status, sync_error)
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, excel_id TEXT, video_idea TEXT, visual_style TEXT, language TEXT, voice_style TEXT, target_platform TEXT, priority TEXT, script_text TEXT, final_video_url TEXT, error TEXT)")
    conn.execute("CREATE TABLE shots (id TEXT PRIMARY KEY, audio_requirements TEXT, narration_text TEXT)")
    
    # Insert some data to ensure it survives
    conn.execute("INSERT INTO projects (id, video_idea) VALUES ('P1', 'Test Idea')")
    
    run_migrations(conn) # Should auto-repair v3 and v4 columns
    
    # Verify columns exist now
    project_columns = [row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
    assert "audio_policy" in project_columns
    assert "sync_status" in project_columns
    assert "sync_error" in project_columns
    
    # Verify data survived
    proj = conn.execute("SELECT * FROM projects WHERE id = 'P1'").fetchone()
    assert proj is not None
    
    # Ensure idempotency
    run_migrations(conn)
    
    conn.close()
