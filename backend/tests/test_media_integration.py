import os
import subprocess
import pytest
from app.services.assembly_service import assembly_service
from app.core.config import settings

def test_genuine_media_assembly(tmp_path, monkeypatch):
    """
    Tests actual assembly using real ffmpeg, generating synthetic 1-second colored clips.
    """
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("FFmpeg is not installed or not in PATH. Skipping genuine media test.")
        
    project_id = "proj-media-test"
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    shots_dir = tmp_path / "projects" / project_id / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    
    clip1 = shots_dir / "shot1.mp4"
    clip2 = shots_dir / "shot2.mp4"
    
    # Generate 4-second blue clip
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:d=4", 
        "-c:v", "libx264", str(clip1)
    ], check=True, capture_output=True)
    
    # Generate 4-second red clip
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=1920x1080:d=4", 
        "-c:v", "libx264", str(clip2)
    ], check=True, capture_output=True)
    
    # Assemble to a target duration of 7 seconds (requires strict trimming from 8s)
    # Testing Audio Policy: 'silent' mode
    final_url = assembly_service.assemble_shots(
        project_id=project_id,
        shot_paths=[str(clip1), str(clip2)],
        target_duration=7,
        aspect_ratio="16:9",
        audio_mode="silent",
        output_filename="final_genuine.mp4"
    )
    
    final_path = tmp_path / "projects" / project_id / "final" / "final_genuine.mp4"
    assert final_path.exists()
    assert final_path.stat().st_size > 0
    
    # Verify strict trimming with ffprobe
    probe_result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(final_path)
    ], check=True, capture_output=True, text=True)
    
    import json
    probe_data = json.loads(probe_result.stdout)
    
    actual_duration = float(probe_data.get("format", {}).get("duration", 0))
    # Check if within 1.0s tolerance of 7s
    assert abs(actual_duration - 7.0) <= 1.0
    
    # Verify silent mode means no audio stream
    streams = probe_data.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    assert len(audio_streams) == 0
    
def test_genuine_media_assembly_preserve_audio(tmp_path, monkeypatch):
    """
    Tests assembly with audio_mode="preserve" using synthetic audio/video clips.
    """
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("FFmpeg is not installed or not in PATH. Skipping genuine media test.")
        
    project_id = "proj-media-test-audio"
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    
    shots_dir = tmp_path / "projects" / project_id / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    
    clip1 = shots_dir / "shot1_audio.mp4"
    
    # Generate 4-second blue clip WITH 440Hz tone audio
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:d=4", 
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:v", "libx264", "-c:a", "aac", str(clip1)
    ], check=True, capture_output=True)
    
    # Assemble to a target duration of 4 seconds
    final_url = assembly_service.assemble_shots(
        project_id=project_id,
        shot_paths=[str(clip1)],
        target_duration=4,
        aspect_ratio="16:9",
        audio_mode="preserve",
        output_filename="final_genuine_audio.mp4"
    )
    
    final_path = tmp_path / "projects" / project_id / "final" / "final_genuine_audio.mp4"
    assert final_path.exists()
    
    probe_result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(final_path)
    ], check=True, capture_output=True, text=True)
    
    import json
    probe_data = json.loads(probe_result.stdout)
    
    streams = probe_data.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    assert len(audio_streams) == 1, "Audio preserve mode must result in audio stream output"
