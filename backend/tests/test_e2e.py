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

def test_atomic_claim_concurrency(test_client, monkeypatch):
    """
    Tests that if two threads attempt to run the pipeline for the same project, 
    only one acquires the claim.
    """
    import threading
    from app.services.orchestration_service import orchestration_service
    from app.db.database import get_db
    import uuid
    
    project_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (id, video_idea, target_duration, aspect_ratio, status) VALUES (?, ?, ?, ?, ?)",
            (project_id, "Concurrency test", 10, "16:9", "QUEUED")
        )
        db.commit()
        
    execution_count = [0]
    lock = threading.Lock()
    
    # We patch run_pipeline_sync just at the point where it does actual work,
    # or we can mock generate_storyboard. Let's mock generate_storyboard.
    from app.services.storyboard_service import storyboard_service
    original_generate = storyboard_service.generate_storyboard
    
    def mock_generate(*args, **kwargs):
        with lock:
            execution_count[0] += 1
        return original_generate(*args, **kwargs)
        
    monkeypatch.setattr(storyboard_service, "generate_storyboard", mock_generate)
    
    # Mock video_provider and assembly_service to avoid real FFmpeg
    from app.services.video_provider import video_provider
    from app.services.assembly_service import assembly_service
    monkeypatch.setattr(video_provider, "generate_video_sync", lambda *args, **kwargs: "/mock.mp4")
    monkeypatch.setattr(assembly_service, "assemble_shots", lambda *args, **kwargs: "/final.mp4")

    # Run 5 threads trying to execute the pipeline for the same project
    threads = []
    for _ in range(5):
        t = threading.Thread(target=orchestration_service.run_pipeline_sync, args=(project_id,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # Only 1 execution should have happened!
    assert execution_count[0] == 1
