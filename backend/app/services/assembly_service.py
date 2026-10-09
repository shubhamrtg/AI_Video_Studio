import os
import json
import subprocess
from typing import List
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AssemblyService:
    def assemble_shots(
        self, 
        project_id: str, 
        shot_paths: List[str], 
        target_duration: int, 
        aspect_ratio: str = "16:9", 
        audio_mode: str = "silent",
        output_filename: str = "final.mp4"
    ) -> str:
        project_dir = os.path.join(settings.DATA_DIR, "projects", project_id, "final")
        os.makedirs(project_dir, exist_ok=True)
        
        final_path = os.path.join(project_dir, output_filename)
        temp_path = os.path.join(project_dir, f"temp_{output_filename}")
        
        # Verify inputs exist
        for path in shot_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing input clip: {path}")

        # Aspect ratio handling
        if aspect_ratio == "9:16":
            width, height = 1080, 1920
        else:
            width, height = 1920, 1080
            
        # Audio policy validation
        valid_audio_modes = ["silent", "preserve"]
        if audio_mode not in valid_audio_modes:
            raise ValueError(f"Invalid audio mode: {audio_mode}. Must be one of {valid_audio_modes}")
            
        filter_complex = ""
        for i in range(len(shot_paths)):
            filter_complex += f"[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]; "
            
        concat_str = "".join([f"[v{i}]" for i in range(len(shot_paths))])
        
        if audio_mode == "preserve":
            # Attempt to concat video and audio. Note: this requires all inputs to have audio.
            # For robustness in mixed media, we generate silent audio for each clip if it lacks it, 
            # but for this strict policy, if preserve is requested and a clip lacks audio, concat will fail 
            # naturally (which fulfills "fail clearly if expected audio is missing").
            for i in range(len(shot_paths)):
                concat_str += f"[{i}:a:0]"
            filter_complex += f"{concat_str}concat=n={len(shot_paths)}:v=1:a=1[outv][outa]"
        else:
            filter_complex += f"{concat_str}concat=n={len(shot_paths)}:v=1:a=0[outv]"
        
        cmd = ["ffmpeg", "-y"]
        for path in shot_paths:
            cmd.extend(["-i", path])
            
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]"
        ])
        
        if audio_mode == "preserve":
            cmd.extend(["-map", "[outa]", "-c:a", "aac"])
            
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-t", str(target_duration),  # Strict trimming to target duration
            temp_path
        ])
        
        try:
            # Check ffmpeg availability
            try:
                subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
            except FileNotFoundError:
                raise RuntimeError("FFmpeg is not installed or not in PATH.")

            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Validation step - ensure file was actually written and > 0 bytes
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError("FFmpeg completed but output file is empty or missing.")
                
            # ffprobe validation
            probe_cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", temp_path
            ]
            probe_result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
            probe_data = json.loads(probe_result.stdout)
            
            streams = probe_data.get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
            
            if not video_streams:
                raise RuntimeError("ffprobe found no video streams in the generated file.")
                
            if audio_mode == "preserve" and not audio_streams:
                raise RuntimeError("Audio preserve mode requested but output contains no audio stream.")
            elif audio_mode == "silent" and audio_streams:
                raise RuntimeError("Silent mode requested but output contains an audio stream.")
                
            v_stream = video_streams[0]
            out_w = int(v_stream.get("width", 0))
            out_h = int(v_stream.get("height", 0))
            if out_w != width or out_h != height:
                raise RuntimeError(f"Output resolution {out_w}x{out_h} does not match requested {width}x{height}.")
                
            actual_duration = float(probe_data.get("format", {}).get("duration", 0))
            tolerance = 1.0 # 1 second tolerance for codec framing
            if abs(actual_duration - target_duration) > tolerance:
                raise RuntimeError(f"Actual duration {actual_duration}s deviates from target {target_duration}s by more than {tolerance}s tolerance despite strict trimming.")
                
            # Publish artifact atomically
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(temp_path, final_path)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg/ffprobe stderr: {e.stderr}")
            if "Stream specifier" in e.stderr and audio_mode == "preserve":
                raise RuntimeError("Audio preservation failed. One or more input clips missing an audio stream.")
            raise RuntimeError("Media processing failed. See logs for details.")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
        return f"/projects/{project_id}/final/{output_filename}"

assembly_service = AssemblyService()
