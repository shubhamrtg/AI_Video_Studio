from fastapi import APIRouter, HTTPException, BackgroundTasks
import uuid
from typing import List
from app.models.project import ProjectCreate, ProjectResponse, ProjectStatus, ShotResponse, ShotStatus
from app.db.database import get_db
from app.services.storyboard_service import storyboard_service
from app.services.video_provider import video_provider

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
            status=ShotStatus(row["status"]),
            video_url=row["video_url"],
            error=row["error"]
        ) for row in rows
    ]

@router.post("/", response_model=ProjectResponse)
def create_project(project_in: ProjectCreate, background_tasks: BackgroundTasks):
    project_id = str(uuid.uuid4())
    
    with get_db() as db:
        db.execute(
            "INSERT INTO projects (id, master_prompt, target_duration, aspect_ratio, status) VALUES (?, ?, ?, ?, ?)",
            (project_id, project_in.master_prompt, project_in.target_duration, project_in.aspect_ratio, ProjectStatus.DRAFT.value)
        )
        db.commit()
    
    def generate_storyboard_task(pid: str, prompt: str, duration: int):
        try:
            shots = storyboard_service.generate_storyboard(prompt, duration)
            with get_db() as db:
                for shot in shots:
                    shot_id = str(uuid.uuid4())
                    db.execute(
                        """INSERT INTO shots 
                        (id, project_id, shot_number, duration, description, camera, subject, action, lighting, style, continuity_notes, negative_prompt, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (shot_id, pid, shot.shot_number, shot.duration, shot.description, shot.camera, shot.subject, shot.action, shot.lighting, shot.style, shot.continuity_notes, shot.negative_prompt, ShotStatus.PENDING.value)
                    )
                db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.STORYBOARD_READY.value, pid))
                db.commit()
        except Exception as e:
            with get_db() as db:
                db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.FAILED.value, pid))
                db.commit()
            print(f"Storyboard generation failed: {e}")

    background_tasks.add_task(generate_storyboard_task, project_id, project_in.master_prompt, project_in.target_duration)
    
    return ProjectResponse(
        id=project_id,
        master_prompt=project_in.master_prompt,
        target_duration=project_in.target_duration,
        aspect_ratio=project_in.aspect_ratio,
        status=ProjectStatus.DRAFT,
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
            master_prompt=row["master_prompt"],
            target_duration=row["target_duration"],
            aspect_ratio=row["aspect_ratio"],
            status=ProjectStatus(row["status"]),
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
    
    # Construct a full prompt for Veo
    prompt = f"Description: {shot['description']}. Action: {shot['action']}. Camera: {shot['camera']}. Style: {shot['style']}. Lighting: {shot['lighting']}."
    
    # We will modify video_provider to accept shot_id instead of job_id, or just use job_id = shot_id
    video_provider.generate_video_async(shot_id, prompt, shot["duration"])
    
    return {"status": "QUEUED"}

import os
from app.core.config import settings

@router.post("/{project_id}/assemble")
def assemble_project(project_id: str):
    with get_db() as db:
        shots = db.execute("SELECT video_url, status FROM shots WHERE project_id = ? ORDER BY shot_number ASC", (project_id,)).fetchall()
        
        shot_paths = []
        for shot in shots:
            if shot["status"] != ShotStatus.COMPLETED.value:
                raise HTTPException(status_code=400, detail="All shots must be COMPLETED before assembly")
            filename = shot["video_url"].split("/")[-1]
            local_path = os.path.join(settings.DATA_DIR, "projects", "default", "shots", filename)
            shot_paths.append(local_path)
            
        from app.services.assembly_service import assembly_service
        try:
            final_url = assembly_service.assemble_shots(project_id, shot_paths)
            db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.COMPLETED.value, project_id))
            db.commit()
            return {"status": "COMPLETED", "final_video_url": final_url}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
