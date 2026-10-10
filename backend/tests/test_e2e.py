import os
import sqlite3
import pytest
from fastapi.testclient import TestClient
import openpyxl

from app.main import app
from app.services.excel_service import excel_service

def test_full_e2e_workflow(test_client, monkeypatch):
    import subprocess
    from app.services.orchestration_service import orchestration_service
    from app.services.video_provider import video_provider
    from app.core.config import settings
    
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("FFmpeg is not installed or not in PATH. Skipping genuine E2E test.")
    
    # 1. Setup mock excel
    temp_excel = os.path.join(settings.DATA_DIR, "video_ideas.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VideoIdeas"
    headers = ["id", "video_idea", "target_duration_seconds", "aspect_ratio", "status", "project_id", "output_path", "error_message"]
    ws.append(headers)
    ws.append(["EX-E2E", "A fully end-to-end test", 6, "16:9", "QUEUED", "", "", ""])
    wb.save(temp_excel)
    
    monkeypatch.setattr(settings, "EXCEL_WORKBOOK_PATH", str(temp_excel))
    
    # Setup deterministic video provider that runs real ffmpeg
    def mock_generate_video(project_id, shot_id, prompt, duration, aspect_ratio):
        shots_dir = os.path.join(settings.DATA_DIR, "projects", project_id, "shots")
        os.makedirs(shots_dir, exist_ok=True)
        out_file = os.path.join(shots_dir, f"{shot_id}.mp4")
        
        # Real ffmpeg call for a deterministic synthetic clip
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=1920x1080:d={duration}", 
            "-c:v", "libx264", out_file
        ], check=True, capture_output=True)
        
        from app.db.database import get_db
        from app.models.project import ShotStatus
        from app.core.path_utils import local_path_to_public_url
        
        pub_url = local_path_to_public_url(out_file)
        
        with get_db() as db:
            db.execute("UPDATE shots SET status = ?, video_url = ? WHERE id = ?", 
                       (ShotStatus.COMPLETED.value, pub_url, shot_id))
            db.commit()
            
        return pub_url
        
    monkeypatch.setattr(video_provider, "generate_video_sync", mock_generate_video)

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
        proj = db.execute("SELECT status, final_video_url, sync_status FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert proj["status"] == "READY_FOR_REVIEW"
        assert proj["final_video_url"] is not None
        assert proj["final_video_url"].startswith("/projects/")
        assert proj["final_video_url"].endswith(".mp4")
        
        from app.core.path_utils import public_url_to_local_path
        local_final = public_url_to_local_path(proj["final_video_url"])
        assert os.path.exists(local_final)
        
        assert proj["sync_status"] == "SUCCESS"
    
    # Check excel writeback
    wb_read = openpyxl.load_workbook(temp_excel)
    ws_read = wb_read["VideoIdeas"]
    assert ws_read.cell(row=2, column=5).value == "READY_FOR_REVIEW"
    excel_url = ws_read.cell(row=2, column=7).value
    assert excel_url == proj["final_video_url"]
    
    # Resolve the output reference using the application's real URL/path conversion function
    from app.core.path_utils import public_url_to_local_path
    excel_local_path = public_url_to_local_path(excel_url)
    assert os.path.exists(excel_local_path)
    assert os.path.getsize(excel_local_path) > 0
    
    # Run ffprobe on the resolved path
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", excel_local_path
    ], check=True, capture_output=True, text=True)
    assert float(probe.stdout.strip()) > 0

    # Now approve it
    response = test_client.post(f"/api/projects/{project_id}/approve")
    assert response.status_code == 200
    
    # Check it's COMPLETED in DB and Excel
    with get_db() as db:
        proj = db.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert proj["status"] == "COMPLETED"
        
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
    monkeypatch.setattr(video_provider, "generate_video_sync", lambda *args, **kwargs: "/projects/mock/shots/mock.mp4")
    monkeypatch.setattr(assembly_service, "assemble_shots", lambda *args, **kwargs: "/projects/mock/final/mock.mp4")

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
def test_retry_recovery(test_client, monkeypatch):
    import uuid
    from app.db.database import get_db
    from app.models.project import ProjectStatus
    
    project_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (id, video_idea, target_duration, aspect_ratio, status) VALUES (?, ?, ?, ?, ?)",
            (project_id, "Retry test", 10, "16:9", ProjectStatus.FAILED.value)
        )
        db.commit()
        
    # Trigger retry
    resp = test_client.post(f"/api/projects/{project_id}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "QUEUED"
    
    # DB state should be QUEUED before the thread starts executing
    # (assuming thread hasn't picked it up immediately or even if it did, it would be STORYBOARDING, but we mocked trigger_pipeline if we want)
def test_concurrent_api_retries(test_client, monkeypatch):
    import threading
    import uuid
    from app.db.database import get_db
    from app.models.project import ProjectStatus
    
    project_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (id, video_idea, target_duration, aspect_ratio, status) VALUES (?, ?, ?, ?, ?)",
            (project_id, "Concurrency retry API test", 10, "16:9", ProjectStatus.FAILED.value)
        )
        db.commit()
        
    # We want to mock `trigger_pipeline` so we can simulate both hitting the API
    from app.services.orchestration_service import orchestration_service
    trigger_calls = [0]
    
    def mock_trigger(pid):
        trigger_calls[0] += 1
        
    monkeypatch.setattr(orchestration_service, "trigger_pipeline", mock_trigger)
    
    # We want both threads to run the API simultaneously
    responses = []
    
    def hit_retry_api():
        resp = test_client.post(f"/api/projects/{project_id}/retry")
        responses.append(resp.status_code)
        
    t1 = threading.Thread(target=hit_retry_api)
    t2 = threading.Thread(target=hit_retry_api)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    assert responses.count(200) == 1
    assert responses.count(409) == 1
    assert trigger_calls[0] == 1
    
    with get_db() as db:
        proj = db.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert proj["status"] == ProjectStatus.QUEUED.value

def test_executor_rejection(test_client, monkeypatch):
    import uuid
    from app.db.database import get_db
    from app.models.project import ProjectStatus
    
    project_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (id, video_idea, target_duration, aspect_ratio, status) VALUES (?, ?, ?, ?, ?)",
            (project_id, "Rejection test", 10, "16:9", ProjectStatus.FAILED.value)
        )
        db.commit()
        
    from app.services.orchestration_service import orchestration_service
    
    # Force full queue
    orchestration_service._active_and_queued_jobs = orchestration_service.max_queue
    
    resp = test_client.post(f"/api/projects/{project_id}/retry")
    assert resp.status_code == 500
    assert "Orchestration queue is at capacity" in resp.json()["detail"]
    
    # Project should be back to FAILED
    with get_db() as db:
        proj = db.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert proj["status"] == ProjectStatus.FAILED.value
        
    # Reset queue, should work
    orchestration_service._active_and_queued_jobs = 0
    resp = test_client.post(f"/api/projects/{project_id}/retry")
    assert resp.status_code == 200
@pytest.mark.anyio
async def test_startup_recovery_rejection(test_client, monkeypatch):
    import uuid
    from app.db.database import get_db
    from app.models.project import ProjectStatus
    from app.services.orchestration_service import orchestration_service
    from app.main import lifespan
    from fastapi import FastAPI
    
    project_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (id, video_idea, target_duration, aspect_ratio, status) VALUES (?, ?, ?, ?, ?)",
            (project_id, "Startup rejection test", 10, "16:9", ProjectStatus.QUEUED.value)
        )
        db.commit()
        
    # Force full queue so startup trigger_pipeline fails
    orchestration_service._active_and_queued_jobs = orchestration_service.max_queue
    
    app = FastAPI()
    async with lifespan(app):
        pass # run startup
        
    # Check DB, should be FAILED now
    with get_db() as db:
        proj = db.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        assert proj["status"] == ProjectStatus.FAILED.value
        
    # Reset queue
    orchestration_service._active_and_queued_jobs = 0
