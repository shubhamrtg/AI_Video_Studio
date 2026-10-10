import os
from app.core.config import settings

def public_url_to_local_path(url: str) -> str:
    if not url or not url.startswith("/projects/"):
        raise ValueError(f"Invalid public URL format: {url}")
        
    relative_path = url[len("/projects/"):]
    relative_path = relative_path.replace("/", os.sep)
    
    if ".." in relative_path or relative_path.startswith(os.sep):
        raise ValueError("Invalid path sequence detected in URL.")
        
    return os.path.normpath(os.path.join(settings.DATA_DIR, "projects", relative_path))

def local_path_to_public_url(local_path: str) -> str:
    projects_dir = os.path.normpath(os.path.join(settings.DATA_DIR, "projects"))
    norm_path = os.path.normpath(local_path)
    
    if not norm_path.startswith(projects_dir):
        raise ValueError("Path is outside the configured projects data directory.")
        
    relative = os.path.relpath(norm_path, projects_dir)
    return "/projects/" + relative.replace("\\", "/")

