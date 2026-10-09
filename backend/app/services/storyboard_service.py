import json
from typing import List
from google import genai
from google.genai import types
from app.core.config import settings
from app.models.project import ShotBase

class StoryboardService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.TEXT_MODEL

    def generate_storyboard(self, master_prompt: str, target_duration: int) -> List[ShotBase]:
        # Google's Omni/Veo model prefers shots around 5 seconds.
        # We'll ask the LLM to generate enough 5s shots to reach target_duration.
        estimated_shots = max(1, target_duration // 5)
        
        system_instruction = f"""
        You are an expert AI Video Director.
        Create a detailed storyboard for a {target_duration}-second video based on the user's master prompt.
        Break the video down into exactly {estimated_shots} shots, each lasting exactly 5 seconds.
        Maintain strict visual continuity between shots (same characters, same environment, same lighting).
        Return the storyboard as a JSON array of shot objects.
        """
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=[system_instruction, f"Master Prompt: {master_prompt}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[ShotBase],
                temperature=0.7
            )
        )
        
        try:
            # `response.text` contains the JSON string
            shots_data = json.loads(response.text)
            shots = [ShotBase(**shot) for shot in shots_data]
            return shots
        except Exception as e:
            raise ValueError(f"Failed to parse storyboard JSON: {str(e)}\nResponse: {response.text}")

storyboard_service = StoryboardService()
