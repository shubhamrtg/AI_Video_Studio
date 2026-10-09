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
    yield

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

# Serve generated videos statically
projects_dir = os.path.join(settings.DATA_DIR, "projects")
os.makedirs(projects_dir, exist_ok=True)
app.mount("/projects", StaticFiles(directory=projects_dir), name="projects")
app.mount("/videos", StaticFiles(directory=os.path.join(projects_dir, "default", "shots")), name="videos")

@app.get("/")
def root():
    return {"status": "ok"}
