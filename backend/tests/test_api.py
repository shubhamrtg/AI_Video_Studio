import pytest
from fastapi.testclient import TestClient
import sqlite3
import os
import tempfile
from app.main import app
from app.db.database import get_db, run_migrations
from app.core.config import settings
from app.models.project import ProjectStatus

# test_client fixture is in conftest.py

def test_create_project(test_client):
    response = test_client.post("/api/projects/", json={
        "excel_id": "test_excel_1",
        "video_idea": "A cute cat video",
        "target_duration": 15,
        "aspect_ratio": "16:9"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["excel_id"] == "test_excel_1"
    assert data["video_idea"] == "A cute cat video"
    assert data["target_duration"] == 15
    assert data["status"] == ProjectStatus.QUEUED.value
    project_id = data["id"]
    
    # Get project
    response = test_client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["video_idea"] == "A cute cat video"
    
def test_create_project_no_excel_id(test_client):
    response = test_client.post("/api/projects/", json={
        "video_idea": "A cute dog video",
        "target_duration": 10,
        "aspect_ratio": "16:9"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["video_idea"] == "A cute dog video"
    assert data["excel_id"] == ""
