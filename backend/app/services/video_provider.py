import threading
import urllib.request
import os
from google import genai
from google.genai import types
from app.models.project import ShotStatus
from app.db.database import get_db
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def update_shot_status(shot_id: str, status: ShotStatus, video_url: str = None, error: str = None):
    with get_db() as db:
        db.execute(
            "UPDATE shots SET status = ?, video_url = ?, error = ? WHERE id = ?",
            (status.value, video_url, error, shot_id)
        )
        db.commit()

class GoogleVeoProvider:
    def __init__(self):
        # Allow running tests without crashing on missing API key
        api_key = settings.GEMINI_API_KEY if settings.GEMINI_API_KEY else "dummy_key"
        self.client = genai.Client(api_key=api_key, http_options={"timeout": 600000})
        self.model = settings.VIDEO_MODEL

    def generate_video_async(self, project_id: str, shot_id: str, prompt: str, duration: int, aspect_ratio: str = "16:9"):
        def task():
            try:
                update_shot_status(shot_id, ShotStatus.GENERATING)
                
                logger.info(f"[{shot_id}] Calling Veo API with models.generate_videos...")
                import time
                
                # Veo requires duration_seconds between 4 and 8 inclusive.
                veo_duration = max(4, min(duration, 8))
                
                # Veo only explicitly supports "16:9" or "9:16", default 16:9
                veo_ar = aspect_ratio if aspect_ratio in ["16:9", "9:16"] else "16:9"

                if settings.GEMINI_API_KEY == "" or settings.GEMINI_API_KEY == "dummy_key":
                    raise ValueError("GEMINI_API_KEY is not configured.")

                operation = self.client.models.generate_videos(
                    model=self.model,
                    source=types.GenerateVideosSource(prompt=prompt),
                    config=types.GenerateVideosConfig(
                        number_of_videos=1,
                        duration_seconds=veo_duration,
                        aspect_ratio=veo_ar
                    )
                )
                
                logger.info(f"[{shot_id}] Operation started: {operation.name}. Polling...")
                
                start_time = time.time()
                timeout = 3600 # 1 hour timeout
                
                while not operation.done:
                    if time.time() - start_time > timeout:
                        raise RuntimeError("Polling timed out after 1 hour.")
                    time.sleep(10)
                    operation = self.client.operations.get(operation=operation.name)
                    logger.info(f"[{shot_id}] Polling... done={operation.done}")
                
                logger.info(f"[{shot_id}] Operation complete.")
                
                if operation.error:
                    raise RuntimeError(f"Operation failed: {operation.error.message}")
                    
                if not operation.response or not operation.response.generated_videos:
                    raise RuntimeError("No videos returned in response")
                    
                video = operation.response.generated_videos[0].video
                
                project_dir = os.path.join(settings.DATA_DIR, "projects", project_id, "shots")
                os.makedirs(project_dir, exist_ok=True)
                local_path = os.path.join(project_dir, f"{shot_id}.mp4")
                
                if video.video_bytes:
                    with open(local_path, "wb") as f:
                        f.write(video.video_bytes)
                elif video.uri:
                    urllib.request.urlretrieve(video.uri, local_path)
                else:
                    raise RuntimeError("No video bytes or URI returned")
                
                video_url = f"/projects/{project_id}/shots/{shot_id}.mp4"
                update_shot_status(shot_id, ShotStatus.COMPLETED, video_url=video_url)
                
            except Exception as e:
                logger.error(f"[{shot_id}] Error: {str(e)}")
                update_shot_status(shot_id, ShotStatus.FAILED, error=str(e))
                
        thread = threading.Thread(target=task)
        thread.start()

video_provider = GoogleVeoProvider()
