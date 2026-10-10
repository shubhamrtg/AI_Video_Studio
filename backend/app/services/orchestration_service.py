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

import threading

logger = logging.getLogger(__name__)

class OrchestrationService:
    def __init__(self):
        self.max_workers = 3
        self.max_queue = 10
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Explicit admission control variables
        self._queue_lock = threading.Lock()
        self._active_and_queued_jobs = 0

    def claim_state_transition(self, project_id: str, target_state: str, allowed_prior_states: list) -> bool:
        """Atomically claim and transition a project to a target state."""
        with get_db() as db:
            placeholders = ",".join("?" * len(allowed_prior_states))
            params = [target_state, project_id] + allowed_prior_states
            cursor = db.execute(f"""
                UPDATE projects 
                SET status = ? 
                WHERE id = ? AND status IN ({placeholders})
            """, tuple(params))
            
            db.commit()
            return cursor.rowcount > 0

    def trigger_pipeline(self, project_id: str):
        """Asynchronously start the pipeline. Rejects if queue is full."""
        with self._queue_lock:
            if self._active_and_queued_jobs >= self.max_queue:
                raise RuntimeError(f"Orchestration queue is at capacity ({self.max_queue}). Try again later.")
            self._active_and_queued_jobs += 1
            
        self.executor.submit(self._run_pipeline_wrapper, project_id)
        
    def _run_pipeline_wrapper(self, project_id: str):
        """Wraps the actual pipeline to ensure capacity is released."""
        try:
            self.run_pipeline_sync(project_id)
        finally:
            with self._queue_lock:
                self._active_and_queued_jobs -= 1

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
            # Atomic Claim
            if not self.claim_state_transition(project_id, ProjectStatus.STORYBOARDING.value, [ProjectStatus.QUEUED.value, ProjectStatus.FAILED.value]):
                logger.warning(f"Project {project_id} could not be claimed (already running, completed, or not found).")
                return
            
            with get_db() as db:
                project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
                
                excel_id = project["excel_id"]
                video_idea = project["video_idea"]
                target_dur = project["target_duration"]
                aspect = project["aspect_ratio"]
                audio_policy = project["audio_policy"] if "audio_policy" in project.keys() else "silent"

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
                
            final_url = assembly_service.assemble_shots(
                project_id=project_id,
                shot_paths=shot_paths,
                target_duration=target_dur,
                aspect_ratio=aspect,
                audio_mode=audio_policy
            )
            
            # 5. Validation and Review
            with get_db() as db:
                db.execute("UPDATE projects SET status = ?, final_video_url = ? WHERE id = ?", (ProjectStatus.VALIDATING_OUTPUT.value, final_url, project_id))
                db.commit()
                # (Validation happened during assembly_shots successfully)
                db.execute("UPDATE projects SET status = ? WHERE id = ?", (ProjectStatus.READY_FOR_REVIEW.value, project_id))
                db.commit()
            
            # Sync READY_FOR_REVIEW
            if excel_id:
                try:
                    excel_service.update_excel_status(excel_id, ProjectStatus.READY_FOR_REVIEW.value, final_url)
                    with get_db() as db:
                        db.execute("UPDATE projects SET sync_status = 'SUCCESS', sync_error = NULL WHERE id = ?", (project_id,))
                        db.commit()
                except Exception as sync_e:
                    logger.error(f"Media succeeded but Excel sync failed: {sync_e}")
                    with get_db() as db:
                        db.execute("UPDATE projects SET sync_status = 'FAILED', sync_error = ? WHERE id = ?", (str(sync_e), project_id))
                        db.commit()
                    # Do NOT fail the project since media generation succeeded.

        except Exception as e:
            logger.error(f"Pipeline failed for {project_id}: {str(e)}")
            with get_db() as db:
                db.execute("UPDATE projects SET status = ?, error = ? WHERE id = ?", (ProjectStatus.FAILED.value, str(e), project_id))
                db.commit()
                project = db.execute("SELECT excel_id FROM projects WHERE id = ?", (project_id,)).fetchone()
                
            if project and project["excel_id"]:
                excel_service.update_excel_status(project["excel_id"], ProjectStatus.FAILED.value, error=str(e))

orchestration_service = OrchestrationService()
