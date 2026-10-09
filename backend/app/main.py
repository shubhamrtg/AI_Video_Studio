from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.routers import projects, orchestration
from app.db.database import init_db
from app.core.config import settings

app = FastAPI(title="AI Video Studio API")

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

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
