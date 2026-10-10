from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.routers import projects, orchestration
from app.db.database import init_db
from app.core.config import settings

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    
    # Crash recovery: Mark any actively running jobs as FAILED due to interruption
    from app.db.database import get_db
    from app.models.project import ProjectStatus
    with get_db() as db:
        interrupted_states = [
            ProjectStatus.STORYBOARDING.value,
            ProjectStatus.GENERATING_VIDEO.value,
            ProjectStatus.ASSEMBLING.value,
            ProjectStatus.VALIDATING_OUTPUT.value
        ]
        placeholders = ",".join("?" * len(interrupted_states))
        cursor = db.execute(f"""
            UPDATE projects 
            SET status = ?, error = 'Job interrupted due to server shutdown/crash. Requires retry.' 
            WHERE status IN ({placeholders})
        """, [ProjectStatus.FAILED.value] + interrupted_states)
        db.commit()
        if cursor.rowcount > 0:
            print(f"Crash recovery: Marked {cursor.rowcount} interrupted projects as FAILED.")
            
    yield

def create_app() -> FastAPI:
    app = FastAPI(title="AI Video Studio API", lifespan=lifespan)

    ALLOWED_ORIGINS = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(projects.router, prefix="/api/projects")
    app.include_router(orchestration.router)

    # Serve generated videos statically based on current configuration
    projects_dir = os.path.join(settings.DATA_DIR, "projects")
    os.makedirs(projects_dir, exist_ok=True)
    os.makedirs(os.path.join(projects_dir, "default", "shots"), exist_ok=True)
    app.mount("/projects", StaticFiles(directory=projects_dir), name="projects")
    app.mount("/videos", StaticFiles(directory=os.path.join(projects_dir, "default", "shots")), name="videos")

    @app.get("/")
    def root():
        return {"status": "ok"}
        
    return app

app = create_app()
