from fastapi import APIRouter, HTTPException, BackgroundTasks
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
            sync_status=row["sync_status"] if "sync_status" in row.keys() else "PENDING",
            sync_error=row["sync_error"] if "sync_error" in row.keys() else None,
            created_at=row["created_at"],
            shots=shots
        )

@router.post("/{project_id}/shots/{shot_id}/generate")
def generate_shot(project_id: str, shot_id: str, background_tasks: BackgroundTasks):
    with get_db() as db:
        shot = db.execute("SELECT * FROM shots WHERE id = ? AND project_id = ?", (shot_id, project_id)).fetchone()
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        project = db.execute("SELECT aspect_ratio FROM projects WHERE id = ?", (project_id,)).fetchone()
        
        # Atomic claim for manual shot generation
        cursor = db.execute("""
            UPDATE shots 
            SET status = ? 
            WHERE id = ? AND status IN (?, ?)
        """, (ShotStatus.QUEUED.value, shot_id, ShotStatus.QUEUED.value, ShotStatus.FAILED.value))
        
        # Also allow generating if it was somehow left PENDING, but usually shots are QUEUED or FAILED
        if cursor.rowcount == 0:
            # Check if it was PENDING
            cursor = db.execute("""
                UPDATE shots 
                SET status = ? 
                WHERE id = ? AND status = ?
            """, (ShotStatus.QUEUED.value, shot_id, ShotStatus.PENDING.value))
            
            if cursor.rowcount == 0:
                # If it's already completed or currently generating
                db.rollback()
                raise HTTPException(status_code=409, detail="Shot is already generating or completed.")
        db.commit()
    
    prompt = f"Description: {shot['description']}. Action: {shot['action']}. Camera: {shot['camera']}. Style: {shot['style']}. Lighting: {shot['lighting']}."
    aspect_ratio = project["aspect_ratio"]

    def background_generate():
        try:
            from app.services.video_provider import video_provider
            video_provider.generate_video_sync(project_id, shot_id, prompt, shot["duration"], aspect_ratio)
        except Exception as e:
            # Generate video sync handles db updates on failure, but we log here just in case
            print(f"Background shot generation failed: {e}")

    background_tasks.add_task(background_generate)
    
    return {"status": "QUEUED"}

@router.post("/{project_id}/assemble")
def assemble_project(project_id: str):
    with get_db() as db:
        project = db.execute("SELECT status, target_duration, aspect_ratio FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        from app.services.orchestration_service import orchestration_service
        if not orchestration_service.claim_state_transition(project_id, ProjectStatus.ASSEMBLING.value, [ProjectStatus.FAILED.value, ProjectStatus.QUEUED.value]):
            raise HTTPException(status_code=409, detail="Project is actively processing or already completed.")

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
            
            from app.core.path_utils import public_url_to_local_path
            try:
                local_path = public_url_to_local_path(shot["video_url"])
            except ValueError as ve:
                db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, f"Invalid shot URL: {ve}", project_id))
                db.commit()
                raise HTTPException(status_code=500, detail=f"Invalid shot URL: {ve}")
                
            if not os.path.exists(local_path):
                db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, f"Missing shot file {local_path}", project_id))
                db.commit()
                raise HTTPException(status_code=500, detail=f"Missing shot file: {local_path}")
            shot_paths.append(local_path)
            
        from app.services.assembly_service import assembly_service
        try:
            target_dur = project["target_duration"]
            aspect = project["aspect_ratio"]
            
            # (Note: we don't have audio policy in the small SELECT earlier, let's grab it)
            proj_full = db.execute("SELECT excel_id, audio_policy FROM projects WHERE id = ?", (project_id,)).fetchone()
            audio_policy = proj_full["audio_policy"] if proj_full and "audio_policy" in proj_full.keys() else "silent"
            
            final_url = assembly_service.assemble_shots(project_id, shot_paths, target_dur, aspect, audio_policy)
            
            # Validation success
            db.execute("UPDATE projects SET status = ?, final_video_url = ? WHERE id = ?", (ProjectStatus.VALIDATING_OUTPUT.value, final_url, project_id))
            db.commit()
            
            db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.READY_FOR_REVIEW.value, project_id))
            db.commit()
            
            # Sync READY_FOR_REVIEW
            if proj_full and proj_full["excel_id"]:
                try:
                    excel_service.update_excel_status(proj_full["excel_id"], ProjectStatus.READY_FOR_REVIEW.value, final_url)
                    db.execute("UPDATE projects SET sync_status = 'SUCCESS', sync_error = NULL WHERE id = ?", (project_id,))
                    db.commit()
                except Exception as sync_e:
                    db.execute("UPDATE projects SET sync_status = 'FAILED', sync_error = ? WHERE id = ?", (str(sync_e), project_id))
                    db.commit()
                
            return {"status": ProjectStatus.READY_FOR_REVIEW.value, "final_video_url": final_url}
        except Exception as e:
            db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, str(e), project_id))
            db.commit()
            
            proj_full = db.execute("SELECT excel_id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj_full and proj_full["excel_id"]:
                from app.services.excel_service import excel_service
                try:
                    excel_service.update_excel_status(proj_full["excel_id"], "FAILED", error=str(e))
                    db.execute("UPDATE projects SET sync_status = 'SUCCESS', sync_error = NULL WHERE id = ?", (project_id,))
                    db.commit()
                except Exception as sync_e:
                    db.execute("UPDATE projects SET sync_status = 'FAILED', sync_error = ? WHERE id = ?", (str(sync_e), project_id))
                    db.commit()
                
            raise HTTPException(status_code=500, detail="Assembly or validation failed.")

@router.post("/{project_id}/approve")
def approve_project(project_id: str):
    from app.services.orchestration_service import orchestration_service
    from app.services.excel_service import excel_service
    
    if not orchestration_service.claim_state_transition(project_id, ProjectStatus.COMPLETED.value, [ProjectStatus.READY_FOR_REVIEW.value]):
        raise HTTPException(status_code=409, detail="Project is not READY_FOR_REVIEW")
        
    with get_db() as db:
        project = db.execute("SELECT excel_id, final_video_url FROM projects WHERE id = ?", (project_id,)).fetchone()
        
        if project and project["excel_id"]:
            try:
                excel_service.update_excel_status(project["excel_id"], ProjectStatus.COMPLETED.value, project["final_video_url"])
                db.execute("UPDATE projects SET sync_status = 'SUCCESS', sync_error = NULL WHERE id = ?", (project_id,))
                db.commit()
            except Exception as sync_e:
                db.execute("UPDATE projects SET sync_status = 'FAILED', sync_error = ? WHERE id = ?", (str(sync_e), project_id))
                db.commit()
                
    return {"status": "COMPLETED"}

@router.post("/{project_id}/retry-sync")
def retry_excel_sync(project_id: str):
    from app.services.excel_service import excel_service
    with get_db() as db:
        project = db.execute("SELECT excel_id, status, final_video_url, error, sync_status FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        if not project["excel_id"]:
            raise HTTPException(status_code=400, detail="Project has no Excel ID")
            
        if project["sync_status"] == "SUCCESS":
            return {"status": "SUCCESS", "message": "Already synced"}
            
        try:
            excel_service.update_excel_status(project["excel_id"], project["status"], project["final_video_url"], error=project["error"])
            db.execute("UPDATE projects SET sync_status = 'SUCCESS', sync_error = NULL WHERE id = ?", (project_id,))
            db.commit()
            return {"status": "SUCCESS", "message": "Sync successful"}
        except Exception as e:
            db.execute("UPDATE projects SET sync_status = 'FAILED', sync_error = ? WHERE id = ?", (str(e), project_id))
            db.commit()
            raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@router.post("/{project_id}/retry")
def retry_project(project_id: str):
    """
    Retries a FAILED project from where it left off, recovering it and enqueuing it.
    """
    from app.services.orchestration_service import orchestration_service
    
    with get_db() as db:
        project = db.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        status = project["status"]
        if status in [ProjectStatus.READY_FOR_REVIEW.value, ProjectStatus.COMPLETED.value]:
            raise HTTPException(status_code=409, detail="Project is already completed or pending review.")
            
    # Atomic transition to QUEUED to claim the retry
    if not orchestration_service.claim_state_transition(project_id, ProjectStatus.QUEUED.value, [ProjectStatus.FAILED.value]):
        raise HTTPException(status_code=409, detail="Project is currently processing or already claimed by another request.")
            
    try:
        orchestration_service.trigger_pipeline(project_id)
        return {"status": "QUEUED", "message": "Project recovery triggered."}
    except Exception as e:
        # Only revert if it is still QUEUED (executor rejected it synchronously)
        with get_db() as db:
            cursor = db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ? AND status = ?", 
                                (ProjectStatus.FAILED.value, str(e), project_id, ProjectStatus.QUEUED.value))
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))

