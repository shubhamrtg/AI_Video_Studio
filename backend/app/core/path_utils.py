import os
from pathlib import Path
from app.core.config import settings

def _get_projects_dir() -> Path:
    return Path(settings.DATA_DIR).resolve() / "projects"

def public_url_to_local_path(url: str) -> str:
    if not url or not url.startswith("/projects/"):
        raise ValueError(f"Invalid public URL format: {url}")
        
    relative_path = url[len("/projects/"):]
    projects_dir = _get_projects_dir()
    
    # Resolve the path to clear symlinks and relative components
    candidate_path = (projects_dir / relative_path).resolve()
    
    # Path-aware containment check
    if not candidate_path.is_relative_to(projects_dir):
        raise ValueError("Path traversal detected: URL resolves outside projects root.")
        
    return str(candidate_path)

def local_path_to_public_url(local_path: str) -> str:
    projects_dir = _get_projects_dir()
    candidate_path = Path(local_path).resolve()
    
    # Path-aware containment check
    if not candidate_path.is_relative_to(projects_dir):
        raise ValueError("Path is outside the configured projects data directory.")
        
    # On Windows, relpath uses backslashes, so we convert them to forward slashes for the URL
    relative = candidate_path.relative_to(projects_dir).as_posix()
    return f"/projects/{relative}"

