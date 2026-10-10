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
    
    # Now test the auto-repair logic
    os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO schema_migrations (version) VALUES (4)")
    
    # Fill in v1 and v2 and v3 columns, but miss v4 columns (sync_status, sync_error)
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, excel_id TEXT, video_idea TEXT, visual_style TEXT, language TEXT, voice_style TEXT, target_platform TEXT, priority TEXT, script_text TEXT, final_video_url TEXT, error TEXT, audio_policy TEXT)")
    conn.execute("CREATE TABLE shots (id TEXT PRIMARY KEY, audio_requirements TEXT, narration_text TEXT)")
    
    run_migrations(conn) # Should auto-repair v4 columns
    
    # Verify sync_status exists now
    project_columns = [row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
    assert "sync_status" in project_columns
    assert "sync_error" in project_columns
    conn.close()
