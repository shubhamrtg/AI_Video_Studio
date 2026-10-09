import logging
import os
import concurrent.futures
from app.db.database import get_db
from app.models.project import ProjectStatus, ShotStatus
from app.services.storyboard_service import storyboard_service
from app.services.video_provider import video_provider
from app.services.assembly_service import assembly_service
from app.services.excel_service import excel_service
from app.core.config import settings

logger = logging.getLogger(__name__)

class OrchestrationService:
    def __init__(self):
        # Bound concurrent generation jobs
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    def trigger_pipeline(self, project_id: str):
        """Asynchronously start the pipeline."""
        self.executor.submit(self.run_pipeline_sync, project_id)

    def run_pipeline_sync(self, project_id: str):
        """
        End-to-End sequence:
        1. validate/init
        2. storyboard
        3. video shots
        4. wait for shots
        5. assemble (w/ audio handling)
        6. excel writeback
        """
        try:
            with get_db() as db:
                project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
                if not project:
                    return
                
                # Protect against duplicate running
                if project["status"] in [ProjectStatus.STORYBOARDING.value, ProjectStatus.GENERATING_VIDEO.value, ProjectStatus.ASSEMBLING.value]:
                    logger.warning(f"Project {project_id} is already in progress.")
                    return
                    
                excel_id = project["excel_id"]
                video_idea = project["video_idea"]
                target_dur = project["target_duration"]
                aspect = project["aspect_ratio"]

                db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.STORYBOARDING.value, project_id))
                db.commit()

            # 2. Storyboarding
            shots = storyboard_service.generate_storyboard(video_idea, target_dur)
            
            with get_db() as db:
                # Save shots
                for shot in shots:
                    shot_id = f"{project_id}_s{shot.shot_number}"
                    db.execute("""
                        INSERT OR IGNORE INTO shots 
                        (id, project_id, shot_number, duration, description, camera, subject, action, lighting, style, continuity_notes, negative_prompt, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        shot_id, project_id, shot.shot_number, shot.duration, shot.description, 
                        shot.camera, shot.subject, shot.action, shot.lighting, shot.style, 
                        shot.continuity_notes, "none", ShotStatus.QUEUED.value
                    ))
                db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.GENERATING_VIDEO.value, project_id))
                db.commit()
                
            # 3. Generating Shots (sync sequentially for the bounds of this background task, but we could use threads. We'll do it sequentially in this worker to preserve API bounds).
            shot_paths = []
            for shot in shots:
                shot_id = f"{project_id}_s{shot.shot_number}"
                # Generate synchronously within this background worker to maintain job control
                video_url = video_provider.generate_video_sync(project_id, shot_id, shot.description, shot.duration, aspect)
                
                filename = video_url.split("/")[-1]
                local_path = os.path.join(settings.DATA_DIR, "projects", project_id, "shots", filename)
                shot_paths.append(local_path)
                
            # 4. Assemble
            with get_db() as db:
                db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.ASSEMBLING.value, project_id))
                db.commit()
                
            # Assume audio_mode = "silent" unless audio_requirements exists in project (not in schema yet, hardcoding silent for now as default safe mode)
            final_url = assembly_service.assemble_shots(
                project_id=project_id,
                shot_paths=shot_paths,
                target_duration=target_dur,
                aspect_ratio=aspect,
                audio_mode="silent" # Audio policy defined explicitly
            )
            
            # 5. Complete
            with get_db() as db:
                db.execute("UPDATE projects SET status = ?, final_video_url = ? WHERE id = ?", (ProjectStatus.COMPLETED.value, final_url, project_id))
                db.commit()
                
            if excel_id:
                excel_service.update_excel_status(excel_id, ProjectStatus.COMPLETED.value, final_url)

        except Exception as e:
            logger.error(f"Pipeline failed for {project_id}: {str(e)}")
            with get_db() as db:
                db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, str(e), project_id))
                db.commit()
                project = db.execute("SELECT excel_id FROM projects WHERE id = ?", (project_id,)).fetchone()
                
            if project and project["excel_id"]:
                excel_service.update_excel_status(project["excel_id"], ProjectStatus.FAILED.value, error=str(e))

orchestration_service = OrchestrationService()
