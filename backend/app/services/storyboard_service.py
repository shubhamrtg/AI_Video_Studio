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
            return self._generate_dummy_storyboard(target_duration)
            
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            response = self.client.models.generate_content(
                model=self.model,
                contents=[system_instruction, f"Video Idea: {video_idea}"],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=list[ShotBase],
                    temperature=0.7 + (attempt * 0.1) # Increase temp slightly on retries
                )
            )
            
            try:
                shots_data = json.loads(response.text)
                shots = [ShotBase(**shot) for shot in shots_data]
                
                # Validation
                if not shots:
                    raise ValueError("Storyboard must contain at least one shot.")
                
                total_duration = sum(s.duration for s in shots)
                
                # Check individual lengths
                for i, s in enumerate(shots):
                    s.shot_number = i + 1
                    if s.duration < 4 or s.duration > 8:
                        raise ValueError(f"Shot {s.shot_number} has invalid duration {s.duration}s. Must be 4-8s.")
                
                # Check total
                if target_duration >= 4 and total_duration != target_duration:
                    raise ValueError(f"Total duration {total_duration}s does not match target {target_duration}s.")
                    
                return shots
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                last_error = e
                
        raise ValueError(f"Failed to generate valid storyboard after {max_retries} attempts. Last error: {str(last_error)}")

    def _generate_dummy_storyboard(self, target_duration: int) -> List[ShotBase]:
        shots = []
        remaining = max(4, target_duration)
        shot_num = 1
        
        while remaining > 0:
            if remaining > 8:
                if remaining - 8 >= 4:
                    duration = 8
                else:
                    duration = remaining - 4
            else:
                duration = remaining
                
            # Failsafe for unrepresentable combinations (e.g. 11 = 6 + 5) handled greedily.
            # If duration < 4 here, we have a math issue, but dummy is simple:
            if duration < 4:
                # Steal from previous if possible (e.g. remaining=2, previous=8 -> 5 and 5)
                if shots and shots[-1].duration > 4:
                    needed = 4 - duration
                    shots[-1].duration -= needed
                    duration = 4
                else:
                    duration = 4
                    
            shots.append(
                ShotBase(
                    shot_number=shot_num,
                    duration=duration,
                    description=f"Dummy shot {shot_num}",
                    camera="Static",
                    subject="Dummy subject",
                    action="Dummy action",
                    lighting="Bright",
                    style="Cinematic",
                    continuity_notes="None"
                )
            )
            remaining -= duration
            shot_num += 1
            
        return shots

storyboard_service = StoryboardService()
