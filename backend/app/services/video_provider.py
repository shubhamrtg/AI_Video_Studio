import uuid
import threading
import urllib.request
import os
from google import genai
from google.genai import types
from app.models.job import JobStatus
from app.db.database import get_db
from app.core.config import settings

def update_job_status(job_id: str, status: JobStatus, video_url: str = None, error: str = None):
    with get_db() as db:
        db.execute(
            "UPDATE shots SET status = ?, video_url = ?, error = ? WHERE id = ?",
            (status.value, video_url, error, job_id)
        )
        # also update jobs table for backwards compatibility in Stage 1 test
        db.execute(
            "UPDATE jobs SET status = ?, video_url = ?, error = ? WHERE id = ?",
            (status.value, video_url, error, job_id)
        )
        db.commit()

class GoogleVeoProvider:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY, http_options={"timeout": 600000})
        self.model = settings.VIDEO_MODEL

    def generate_video_async(self, job_id: str, prompt: str, duration: int = 5):
        def task():
            try:
                update_job_status(job_id, JobStatus.GENERATING)
                
                print(f"[{job_id}] Calling Veo API with models.generate_videos...")
                import time
                
                operation = self.client.models.generate_videos(
                    model=self.model,
                    source=types.GenerateVideosSource(prompt=prompt),
                    config=types.GenerateVideosConfig(
                        number_of_videos=1,
                        duration_seconds=4,
                        aspect_ratio="16:9"
                    )
                )
                
                print(f"[{job_id}] Operation started: {operation.name}. Polling...")
                
                while not operation.done:
                    time.sleep(10)
                    operation = self.client.operations.get(operation=operation.name)
                    print(f"[{job_id}] Polling... done={operation.done}")
                
                print(f"[{job_id}] Operation complete.")
                
                if operation.error:
                    raise RuntimeError(f"Operation failed: {operation.error.message}")
                    
                if not operation.response or not operation.response.generated_videos:
                    raise RuntimeError("No videos returned in response")
                    
                video = operation.response.generated_videos[0].video
                
                # Download the video
                project_dir = os.path.join(settings.DATA_DIR, "projects", "default", "shots")
                os.makedirs(project_dir, exist_ok=True)
                local_path = os.path.join(project_dir, f"{job_id}.mp4")
                
                if video.video_bytes:
                    print(f"[{job_id}] Writing bytes to {local_path}...")
                    with open(local_path, "wb") as f:
                        f.write(video.video_bytes)
                elif video.uri:
                    print(f"[{job_id}] Downloading URI {video.uri} to {local_path}...")
                    urllib.request.urlretrieve(video.uri, local_path)
                else:
                    raise RuntimeError("No video bytes or URI returned")
                
                video_url = f"/videos/{job_id}.mp4"
                update_job_status(job_id, JobStatus.COMPLETED, video_url=video_url)
                
            except Exception as e:
                print(f"[{job_id}] Error: {str(e)}")
                update_job_status(job_id, JobStatus.FAILED, error=str(e))
                
        thread = threading.Thread(target=task)
        thread.start()

video_provider = GoogleVeoProvider()
