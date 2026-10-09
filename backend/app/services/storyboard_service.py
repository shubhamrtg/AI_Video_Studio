import json
from typing import List
from google import genai
from google.genai import types
from app.core.config import settings
from app.models.project import ShotBase
import logging

logger = logging.getLogger(__name__)

class StoryboardService:
    def __init__(self):
        # Allow running tests without crashing on missing API key
        api_key = settings.GEMINI_API_KEY if settings.GEMINI_API_KEY else "dummy_key"
        self.client = genai.Client(api_key=api_key)
        self.model = settings.TEXT_MODEL

    def generate_storyboard(self, video_idea: str, target_duration: int) -> List[ShotBase]:
        if target_duration <= 0:
            raise ValueError("Target duration must be positive.")
            
        system_instruction = f"""
        You are an expert AI Video Director.
        Create a detailed storyboard for a video based on the user's idea.
        The EXACT total duration of the video MUST be {target_duration} seconds.
        
        CRITICAL TIMING RULES:
        1. Our video generation provider only supports individual shots between 4 and 8 seconds long.
        2. You must break the video down into shots of varying lengths (4, 5, 6, 7, or 8 seconds).
        3. The sum of all shot durations must equal exactly {target_duration}.
        4. If {target_duration} is less than 4, output exactly one 4-second shot (it will be trimmed later).
        
        Maintain strict visual continuity between shots (same characters, same environment, same lighting).
        Provide clear continuity notes.
        Return the storyboard as a JSON array of shot objects.
        """
        
        if settings.GEMINI_API_KEY == "" or settings.GEMINI_API_KEY == "dummy_key":
            logger.warning("GEMINI_API_KEY is not configured. Returning dummy storyboard for testing.")
            return [
                ShotBase(
                    shot_number=1,
                    duration=target_duration,
                    description="Dummy shot",
                    camera="Static",
                    subject="Dummy subject",
                    action="Dummy action",
                    lighting="Bright",
                    style="Cinematic",
                    continuity_notes="None"
                )
            ]
            
        response = self.client.models.generate_content(
            model=self.model,
            contents=[system_instruction, f"Video Idea: {video_idea}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[ShotBase],
                temperature=0.7
            )
        )
        
        try:
            shots_data = json.loads(response.text)
            shots = [ShotBase(**shot) for shot in shots_data]
            
            # Validation
            total_duration = sum(s.duration for s in shots)
            if target_duration >= 4 and total_duration != target_duration:
                logger.warning(f"LLM returned storyboard with total duration {total_duration}s instead of {target_duration}s")
                # We could retry here, but we will accept the LLM's best effort to avoid infinite loops
                
            return shots
        except Exception as e:
            raise ValueError(f"Failed to parse storyboard JSON: {str(e)}\nResponse: {response.text}")

storyboard_service = StoryboardService()
