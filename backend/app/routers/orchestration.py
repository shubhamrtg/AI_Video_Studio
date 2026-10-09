from fastapi import APIRouter, HTTPException
from typing import List
from app.db.database import get_db
from app.models.project import ProjectResponse
from app.services.excel_service import excel_service

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])

@router.post("/ingest")
def ingest_excel():
    """Manually triggers Excel ingestion."""
    excel_service.read_and_ingest()
    return {"message": "Ingestion completed"}

@router.get("/queue")
def get_queue():
    """Gets all projects currently tracked in the database."""
    with get_db() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        projects = []
        for row in rows:
            project_dict = dict(row)
            # Add basic shots list (can be expanded later)
            project_dict["shots"] = []
            projects.append(project_dict)
            
        return projects
