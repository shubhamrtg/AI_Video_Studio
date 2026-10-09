import os
import subprocess
from typing import List
from app.core.config import settings

class AssemblyService:
    def assemble_shots(self, project_id: str, shot_paths: List[str], output_filename: str = "final.mp4") -> str:
        project_dir = os.path.join(settings.DATA_DIR, "projects", project_id)
        os.makedirs(project_dir, exist_ok=True)
        
        final_path = os.path.join(project_dir, output_filename)
        list_file_path = os.path.join(project_dir, "shots_list.txt")
        
        # Create the concat list for FFmpeg
        with open(list_file_path, "w") as f:
            for path in shot_paths:
                # Ensure paths are safe and absolute
                abs_path = os.path.abspath(path)
                f.write(f"file '{abs_path}'\n")
        
        # Run ffmpeg concat demuxer (direct concatenation, no re-encoding)
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy",
            final_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg assembly failed: {e.stderr}")
            
        return f"/projects/{project_id}/{output_filename}"

assembly_service = AssemblyService()
