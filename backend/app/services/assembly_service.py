import os
import subprocess
from typing import List
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class AssemblyService:
    def assemble_shots(self, project_id: str, shot_paths: List[str], output_filename: str = "final.mp4") -> str:
        project_dir = os.path.join(settings.DATA_DIR, "projects", project_id, "final")
        os.makedirs(project_dir, exist_ok=True)
        
        final_path = os.path.join(project_dir, output_filename)
        temp_path = os.path.join(project_dir, f"temp_{output_filename}")
        list_file_path = os.path.join(project_dir, "shots_list.txt")
        
        # Verify inputs exist
        for path in shot_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing input clip: {path}")

        # Create the concat list for FFmpeg
        with open(list_file_path, "w") as f:
            for path in shot_paths:
                # Use absolute paths and escape single quotes for FFmpeg
                abs_path = os.path.abspath(path).replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")
        
        # Run ffmpeg with re-encoding to normalize all clips (e.g., if one was 9:16 and another 16:9, or varying fps)
        # We enforce standard 1080p, 30fps, libx264, aac to guarantee assembly succeeds safely.
        # Note: If complex scaling/padding is needed, a complex filtergraph is required, 
        # but for simple safe re-encoding concat, we can use the concat filter or just let ffmpeg auto-scale.
        # Since we might have varying resolutions, using `-filter_complex` is safest.
        
        filter_complex = ""
        for i in range(len(shot_paths)):
            filter_complex += f"[{i}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]; "
            
        concat_str = "".join([f"[v{i}]" for i in range(len(shot_paths))])
        filter_complex += f"{concat_str}concat=n={len(shot_paths)}:v=1:a=0[outv]"
        
        cmd = ["ffmpeg", "-y"]
        for path in shot_paths:
            cmd.extend(["-i", path])
            
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            temp_path
        ])
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Validation step - ensure file was actually written and > 0 bytes
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError("FFmpeg completed but output file is empty or missing.")
                
            # Publish artifact
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(temp_path, final_path)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg stderr: {e.stderr}")
            raise RuntimeError("FFmpeg assembly failed. See logs for details.")
        finally:
            if os.path.exists(list_file_path):
                os.remove(list_file_path)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
        return f"/projects/{project_id}/final/{output_filename}"

assembly_service = AssemblyService()
