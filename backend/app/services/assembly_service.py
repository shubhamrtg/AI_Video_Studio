import os
import json
import subprocess
from typing import List
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AssemblyService:
    def _probe_clip(self, path: str) -> dict:
        try:
            probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
            probe_result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
            return json.loads(probe_result.stdout)
        except FileNotFoundError:
            raise RuntimeError("ffprobe is not installed or not in PATH.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffprobe failed for {path}: {e.stderr}")

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
        if not shot_paths:
            raise ValueError("No shot paths provided for assembly.")

        for path in shot_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing input clip: {path}")

        # Check ffmpeg availability early
        try:
            subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        except FileNotFoundError:
            raise RuntimeError("FFmpeg is not installed or not in PATH.")

        if aspect_ratio == "9:16":
            width, height = 1080, 1920
        else:
            width, height = 1920, 1080
            
        valid_audio_modes = ["silent", "preserve"]
        if audio_mode not in valid_audio_modes:
            raise ValueError(f"Invalid audio mode: {audio_mode}. Must be one of {valid_audio_modes}")
            
        # Probe all clips to determine presence of audio and duration
        clip_infos = []
        for path in shot_paths:
            info = self._probe_clip(path)
            streams = info.get("streams", [])
            has_video = any(s.get("codec_type") == "video" for s in streams)
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            duration = float(info.get("format", {}).get("duration", 0))
            if not has_video:
                raise RuntimeError(f"Clip {path} has no video stream.")
            clip_infos.append({"path": path, "has_audio": has_audio, "duration": duration})

        filter_complex = ""
        concat_inputs = ""
        
        for i, info in enumerate(clip_infos):
            # Format video stream
            filter_complex += f"[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]; "
            
            if audio_mode == "preserve":
                if info["has_audio"]:
                    # Ensure audio is resampled to a common rate (48000) and stereo for reliable concat
                    filter_complex += f"[{i}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]; "
                else:
                    # Generate silence of the exact clip duration
                    dur = info["duration"]
                    # If duration is 0 for some reason, provide a tiny amount to prevent concat hang
                    if dur <= 0:
                        dur = 0.1
                    filter_complex += f"anullsrc=r=48000:cl=stereo,atrim=duration={dur}[a{i}]; "
        
        # Build concat string
        for i in range(len(clip_infos)):
            concat_inputs += f"[v{i}]"
            if audio_mode == "preserve":
                concat_inputs += f"[a{i}]"
                
        if audio_mode == "preserve":
            filter_complex += f"{concat_inputs}concat=n={len(clip_infos)}:v=1:a=1[outv][outa]"
        else:
            filter_complex += f"{concat_inputs}concat=n={len(clip_infos)}:v=1:a=0[outv]"
        
        cmd = ["ffmpeg", "-y"]
        for info in clip_infos:
            cmd.extend(["-i", info["path"]])
            
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]"
        ])
        
        if audio_mode == "preserve":
            cmd.extend(["-map", "[outa]", "-c:a", "aac"])
            
        # Target duration validation
        # According to the prompt: "Define a clear duration policy... Avoid integer-division errors and invalid zero-duration shots"
        if target_duration <= 0:
            raise ValueError(f"Target duration must be > 0. Got {target_duration}.")
            
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-t", str(target_duration),  # Strict trimming to target duration
            temp_path
        ])
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError("FFmpeg completed but output file is empty or missing.")
                
            # Post-assembly validation
            probe_data = self._probe_clip(temp_path)
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
            # Tolerance rule: 1/fps (1/30 = ~0.033s) + small epsilon for container padding
            tolerance = 0.1 
            if abs(actual_duration - target_duration) > tolerance:
                raise RuntimeError(f"Actual duration {actual_duration:.3f}s deviates from target {target_duration}s by more than {tolerance}s tolerance despite strict trimming.")
                
            # Atomic replace
            if os.path.exists(final_path):
                # On Windows, os.replace replaces atomically, but we can just use os.replace directly.
                pass
            os.replace(temp_path, final_path)
            
        except subprocess.TimeoutExpired as e:
            logger.error("FFmpeg assembly timed out.")
            raise RuntimeError("FFmpeg assembly timed out after 300s.")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg/ffprobe stderr: {e.stderr}")
            raise RuntimeError("Media processing failed. See logs for details.")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            
        return f"/projects/{project_id}/final/{output_filename}"

assembly_service = AssemblyService()
