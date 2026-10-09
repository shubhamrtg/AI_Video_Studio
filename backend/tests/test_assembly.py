import os
import pytest
import subprocess
from app.services.assembly_service import assembly_service

def test_assembly_service_validates_inputs(tmp_path):
    project_id = "proj-test"
    with pytest.raises(FileNotFoundError):
        assembly_service.assemble_shots(project_id, ["missing_clip.mp4"], 10)

def test_assembly_service_mocks_ffprobe(tmp_path, monkeypatch):
    project_id = "proj-test"
    
    # Create fake clips
    clip1 = tmp_path / "clip1.mp4"
    clip1.touch()
    
    def mock_run(cmd, *args, **kwargs):
        class MockResult:
            stdout = '{"streams": [{"codec_type": "video", "width": 1920, "height": 1080}], "format": {"duration": "10.0"}}'
        
        if cmd[0] == "ffmpeg" and "-version" in cmd:
            return MockResult()
            
        if cmd[0] == "ffmpeg" and "-y" in cmd:
            # Simulate generating the output file
            out_file = cmd[-1]
            with open(out_file, "w") as f:
                f.write("mock video content")
            return MockResult()
            
        if cmd[0] == "ffprobe":
            return MockResult()
            
        raise ValueError(f"Unexpected command: {cmd}")
        
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    # Run
    final_url = assembly_service.assemble_shots(project_id, [str(clip1)], target_duration=10, aspect_ratio="16:9")
    assert "final.mp4" in final_url
    
    # Verify the output file was moved
    final_path = tmp_path / "projects" / project_id / "final" / "final.mp4"
    assert final_path.exists()
    
def test_assembly_service_rejects_wrong_duration(tmp_path, monkeypatch):
    project_id = "proj-test2"
    clip1 = tmp_path / "clip2.mp4"
    clip1.touch()
    
    def mock_run(cmd, *args, **kwargs):
        class MockResult:
            stdout = '{"streams": [{"codec_type": "video", "width": 1920, "height": 1080}], "format": {"duration": "5.0"}}'
        
        if cmd[0] == "ffmpeg" and "-version" in cmd:
            return MockResult()
        if cmd[0] == "ffmpeg" and "-y" in cmd:
            out_file = cmd[-1]
            with open(out_file, "w") as f:
                f.write("mock video content")
            return MockResult()
        if cmd[0] == "ffprobe":
            # return 5s instead of target 10s
            return MockResult()
        return MockResult()
        
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    with pytest.raises(RuntimeError, match="deviates from target"):
        assembly_service.assemble_shots(project_id, [str(clip1)], target_duration=10, aspect_ratio="16:9")

