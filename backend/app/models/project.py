from pydantic import BaseModel
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

class ProjectCreate(BaseModel):
    excel_id: str
    video_idea: str
    target_duration: int
    aspect_ratio: str
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
    status: ProjectStatus
    script_text: Optional[str] = None
    final_video_url: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    shots: List[ShotResponse] = []
