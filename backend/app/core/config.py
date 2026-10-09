import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    VIDEO_MODEL: str = "veo-3.1-generate-preview"
    TEXT_MODEL: str = "gemini-3.5-flash-lite"
    DATA_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../data"))
    EXCEL_WORKBOOK_PATH: str = os.path.join(DATA_DIR, "video_ideas.xlsx")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
