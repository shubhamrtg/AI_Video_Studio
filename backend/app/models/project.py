from pydantic import BaseModel, Field, validator
from typing import List, Optional
from enum import Enum
from datetime import datetime

class ProjectStatus(str, Enum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    SCRIPTING = "SCRIPTING"
    STORYBOARDING = "STORYBOARDING"
    PREPARING_REFERENCES = "PREPARING_REFERENCES"
    GENERATING_AUDIO = "GENERATING_AUDIO"
    GENERATING_VIDEO = "GENERATING_VIDEO"
    ASSEMBLING = "ASSEMBLING"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ShotStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class AspectRatio(str, Enum):
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"

class AudioPolicy(str, Enum):
    SILENT = "silent"
    PRESERVE = "preserve"

class ProjectCreate(BaseModel):
    excel_id: Optional[str] = None
    video_idea: str = Field(..., min_length=1)
    target_duration: int = Field(..., gt=0)
    aspect_ratio: AspectRatio
    audio_policy: AudioPolicy = AudioPolicy.SILENT
    visual_style: Optional[str] = None
    language: Optional[str] = "English"
    voice_style: Optional[str] = None
    target_platform: Optional[str] = None
    priority: Optional[str] = "Normal"

class ShotBase(BaseModel):
    shot_number: int
    duration: int
    description: str
    camera: str
    subject: str
    action: str
    lighting: str
    style: str
    continuity_notes: str
    negative_prompt: Optional[str] = ""
    audio_requirements: Optional[str] = ""
    narration_text: Optional[str] = ""

class ShotResponse(ShotBase):
    id: str
    project_id: str
    status: ShotStatus
    video_url: Optional[str] = None
    error: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    excel_id: str
    video_idea: str
    target_duration: int
    aspect_ratio: str
    audio_policy: str
    status: ProjectStatus
    script_text: Optional[str] = None
    final_video_url: Optional[str] = None
    error: Optional[str] = None
    sync_status: Optional[str] = "PENDING"
    sync_error: Optional[str] = None
    created_at: str
    shots: List[ShotResponse] = []
