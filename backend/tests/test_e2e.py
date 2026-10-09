import os
import sqlite3
import pytest
from fastapi.testclient import TestClient
import openpyxl

from app.main import app
from app.services.excel_service import excel_service

def test_full_e2e_workflow(test_client, tmp_path, monkeypatch):
    import subprocess
    from app.services.orchestration_service import orchestration_service
    from app.core.config import settings
    
    # 1. Setup mock excel
    temp_excel = tmp_path / "video_ideas.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VideoIdeas"
    headers = ["id", "video_idea", "target_duration_seconds", "aspect_ratio", "status", "project_id"]
    ws.append(headers)
    ws.append(["EX-E2E", "A fully end-to-end test", 6, "16:9", "QUEUED", ""])
    wb.save(temp_excel)
    
    monkeypatch.setattr(settings, "EXCEL_WORKBOOK_PATH", str(temp_excel))
    
    # Setup mock subprocess for ffmpeg/ffprobe
    def mock_run(cmd, *args, **kwargs):
        class MockResult:
            stdout = '{"streams": [{"codec_type": "video", "width": 1920, "height": 1080}], "format": {"duration": "6.0"}}'
        
        if cmd[0] == "ffmpeg" and "-version" in cmd:
            return MockResult()
        if cmd[0] == "ffmpeg" and "-y" in cmd:
            out_file = cmd[-1]
            with open(out_file, "w") as f:
                f.write("mock video content")
            return MockResult()
        if cmd[0] == "ffprobe":
            return MockResult()
        raise ValueError(f"Unexpected command: {cmd}")
        
    monkeypatch.setattr(subprocess, "run", mock_run)

    # Ingest (triggers background thread usually, but here we can wait)
    # To avoid background thread race conditions during test, we mock `trigger_pipeline`
    # and just call `run_pipeline_sync` ourselves.
    
    triggered_projects = []
    def mock_trigger(pid):
        triggered_projects.append(pid)
        
    monkeypatch.setattr(orchestration_service, "trigger_pipeline", mock_trigger)
    
    # Ingest
    excel_service.read_and_ingest()
    
    # Verify it queued
    assert len(triggered_projects) == 1
    project_id = triggered_projects[0]
    
    # Run the pipeline synchronously to completion
    orchestration_service.run_pipeline_sync(project_id)
    
    # Verify final status
    from app.db.database import get_db
    with get_db() as db:
        proj = db.execute("SELECT status, final_video_url FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert proj["status"] == "COMPLETED"
        assert proj["final_video_url"] is not None
        assert proj["final_video_url"].endswith(".mp4")
    
    # Check excel writeback
    wb_read = openpyxl.load_workbook(temp_excel)
    ws_read = wb_read["VideoIdeas"]
    assert ws_read.cell(row=2, column=5).value == "COMPLETED"
