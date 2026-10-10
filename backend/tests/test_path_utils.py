import os
import pytest
from pathlib import Path
from app.core.path_utils import public_url_to_local_path, local_path_to_public_url
from app.core.config import settings

def test_valid_nested_path(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    # Setup projects dir
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    
    url = "/projects/my_project/shots/shot1.mp4"
    local = public_url_to_local_path(url)
    assert str(projects_dir / "my_project" / "shots" / "shot1.mp4") == local
    
    assert local_path_to_public_url(local) == url
    
def test_sibling_prefix_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    
    # Create sibling projects-evil
    evil_dir = tmp_path / "projects-evil"
    evil_dir.mkdir(parents=True, exist_ok=True)
    evil_file = evil_dir / "foo.mp4"
    evil_file.touch()
    
    # If the system uses string prefix matching, this would pass.
    # We expect a ValueError.
    with pytest.raises(ValueError, match="outside the configured projects"):
        local_path_to_public_url(str(evil_file))
        
def test_dot_dot_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    
    # URL pointing to a parent dir via ..
    with pytest.raises(ValueError, match="Path traversal detected"):
        public_url_to_local_path("/projects/../secrets.txt")

def test_absolute_path_outside_root(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate an absolute path in the tmp_path root (outside projects)
    outside_file = tmp_path / "foo.mp4"
    outside_file.touch()
    
    with pytest.raises(ValueError, match="outside the configured projects"):
        local_path_to_public_url(str(outside_file))
        
def test_symlink_escape(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    
    target_dir = tmp_path / "outside_target"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    link_path = projects_dir / "symlink_dir"
    try:
        os.symlink(target_dir, link_path)
    except OSError:
        pytest.skip("Symlinks not supported on this OS/user privileges.")
        
    url = "/projects/symlink_dir/foo.mp4"
    # Even if they request a file inside the symlink, it resolves to outside_target!
    # The .resolve() in path_utils will resolve it and detect it is not relative to projects_dir.
    with pytest.raises(ValueError, match="Path traversal detected"):
        public_url_to_local_path(url)
        
def test_spaces_and_unicode(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    
    url = "/projects/pro ject/shots/shot 1.mp4"
    local = public_url_to_local_path(url)
    assert "pro ject" in local
    assert "shots" in local
    
    assert local_path_to_public_url(local) == url
    
def test_invalid_url_format(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="Invalid public URL format"):
        public_url_to_local_path("invalid/url")
