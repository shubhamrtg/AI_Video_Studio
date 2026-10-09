from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import uuid
from typing import List
import os
from app.models.project import ProjectCreate, ProjectResponse, ProjectStatus, ShotResponse, ShotStatus
from app.db.database import get_db
from app.services.video_provider import video_provider
from app.core.config import settings

router = APIRouter()

def get_project_shots(db, project_id: str) -> List[ShotResponse]:
    rows = db.execute("SELECT * FROM shots WHERE project_id = ? ORDER BY shot_number ASC", (project_id,)).fetchall()
    return [
        ShotResponse(
            id=row["id"],
            project_id=row["project_id"],
            shot_number=row["shot_number"],
            duration=row["duration"],
            description=row["description"],
            camera=row["camera"],
            subject=row["subject"],
            action=row["action"],
            lighting=row["lighting"],
            style=row["style"],
            continuity_notes=row["continuity_notes"],
            negative_prompt=row["negative_prompt"],
            audio_requirements=row["audio_requirements"] if "audio_requirements" in row.keys() else "",
            narration_text=row["narration_text"] if "narration_text" in row.keys() else "",
            status=ShotStatus(row["status"]),
            video_url=row["video_url"],
            error=row["error"]
        ) for row in rows
    ]

@router.post("/", response_model=ProjectResponse)
def create_project(project_in: ProjectCreate):
    project_id = str(uuid.uuid4())
    
    with get_db() as db:
        db.execute(
            """INSERT INTO projects (id, excel_id, video_idea, target_duration, aspect_ratio, audio_policy, visual_style, language, voice_style, target_platform, priority, status) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, project_in.excel_id, project_in.video_idea, project_in.target_duration, project_in.aspect_ratio.value, project_in.audio_policy.value, project_in.visual_style, project_in.language, project_in.voice_style, project_in.target_platform, project_in.priority, ProjectStatus.QUEUED.value)
        )
        db.commit()
    
    from app.services.orchestration_service import orchestration_service
    try:
        orchestration_service.trigger_pipeline(project_id)
    except RuntimeError as e:
        with get_db() as db:
            db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, str(e), project_id))
            db.commit()
        raise HTTPException(status_code=429, detail=str(e))
    
    return ProjectResponse(
        id=project_id,
        excel_id=project_in.excel_id or "",
        video_idea=project_in.video_idea,
        target_duration=project_in.target_duration,
        aspect_ratio=project_in.aspect_ratio.value,
        audio_policy=project_in.audio_policy.value,
        status=ProjectStatus.QUEUED,
        created_at=datetime.now(timezone.utc).isoformat(),
        shots=[]
    )

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    with get_db() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
            
        shots = get_project_shots(db, project_id)
        
        return ProjectResponse(
            id=row["id"],
            excel_id=row["excel_id"] or "",
            video_idea=row["video_idea"],
            target_duration=row["target_duration"],
            aspect_ratio=row["aspect_ratio"],
            audio_policy=row["audio_policy"] if "audio_policy" in row.keys() else "silent",
            status=ProjectStatus(row["status"]),
            script_text=row["script_text"],
            final_video_url=row["final_video_url"],
            error=row["error"],
            created_at=row["created_at"],
            shots=shots
        )

@router.post("/{project_id}/shots/{shot_id}/generate")
def generate_shot(project_id: str, shot_id: str):
    with get_db() as db:
        shot = db.execute("SELECT * FROM shots WHERE id = ? AND project_id = ?", (shot_id, project_id)).fetchone()
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        project = db.execute("SELECT aspect_ratio FROM projects WHERE id = ?", (project_id,)).fetchone()
        
        db.execute("UPDATE shots SET status = ? WHERE id = ?", (ShotStatus.QUEUED.value, shot_id))
        db.commit()
    
    prompt = f"Description: {shot['description']}. Action: {shot['action']}. Camera: {shot['camera']}. Style: {shot['style']}. Lighting: {shot['lighting']}."
    aspect_ratio = project["aspect_ratio"]

    video_provider.generate_video_async(project_id, shot_id, prompt, shot["duration"], aspect_ratio)
    
    return {"status": "QUEUED"}

@router.post("/{project_id}/assemble")
def assemble_project(project_id: str):
    with get_db() as db:
        project = db.execute("SELECT status, target_duration, aspect_ratio FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.ASSEMBLING.value, project_id))
        db.commit()

        shots = db.execute("SELECT video_url, status FROM shots WHERE project_id = ? ORDER BY shot_number ASC", (project_id,)).fetchall()
        if not shots:
            db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, "No shots found to assemble", project_id))
            db.commit()
            raise HTTPException(status_code=400, detail="Cannot assemble project with zero shots.")
            
        shot_paths = []
        for shot in shots:
            if shot["status"] != ShotStatus.COMPLETED.value:
                db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, "Not all shots completed", project_id))
                db.commit()
                raise HTTPException(status_code=400, detail="All shots must be COMPLETED before assembly")
            
            # Use safe local path parsing
            filename = shot["video_url"].split("/")[-1]
            local_path = os.path.join(settings.DATA_DIR, "projects", project_id, "shots", filename)
            if not os.path.exists(local_path):
                db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, f"Missing shot file {filename}", project_id))
                db.commit()
                raise HTTPException(status_code=500, detail=f"Missing shot file: {filename}")
            shot_paths.append(local_path)
            
        from app.services.assembly_service import assembly_service
        try:
            target_dur = project["target_duration"]
            aspect = project["aspect_ratio"]
            final_url = assembly_service.assemble_shots(project_id, shot_paths, target_dur, aspect)
            db.execute("UPDATE projects SET status = ?, final_video_url = ? WHERE id = ?", (ProjectStatus.COMPLETED.value, final_url, project_id))
            db.commit()
            
            # Also update excel if we have it
            from app.services.excel_service import excel_service
            proj_full = db.execute("SELECT excel_id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj_full and proj_full["excel_id"]:
                excel_service.update_excel_status(proj_full["excel_id"], "COMPLETED", final_url)
                
            return {"status": "COMPLETED", "final_video_url": final_url}
        except Exception as e:
            db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, str(e), project_id))
            db.commit()
            
            proj_full = db.execute("SELECT excel_id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj_full and proj_full["excel_id"]:
                from app.services.excel_service import excel_service
                excel_service.update_excel_status(proj_full["excel_id"], "FAILED", error=str(e))
                
            raise HTTPException(status_code=500, detail=str(e))
