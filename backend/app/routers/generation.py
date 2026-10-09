from fastapi import APIRouter, HTTPException
import uuid
from app.models.job import JobCreate, JobResponse, JobStatus
from app.db.database import get_db
from app.services.video_provider import video_provider

router = APIRouter()

@router.post("/jobs", response_model=JobResponse)
def create_job(job: JobCreate):
    job_id = str(uuid.uuid4())
    
    with get_db() as db:
        db.execute(
            "INSERT INTO jobs (id, prompt, status) VALUES (?, ?, ?)",
            (job_id, job.prompt, JobStatus.QUEUED.value)
        )
        db.commit()
        
    video_provider.generate_video_async(job_id, job.prompt, job.duration)
    
    return JobResponse(job_id=job_id, status=JobStatus.QUEUED)

@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    with get_db() as db:
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
            
        return JobResponse(
            job_id=row["id"],
            status=JobStatus(row["status"]),
            video_url=row["video_url"],
            error=row["error"]
        )
