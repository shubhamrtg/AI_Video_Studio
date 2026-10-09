from pydantic import BaseModel
from typing import Optional
from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class JobCreate(BaseModel):
    prompt: str
    duration: Optional[int] = 5

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    video_url: Optional[str] = None
    error: Optional[str] = None
