# AI Video Studio

An end-to-end automated platform for generating videos from ideas in an Excel spreadsheet.

## Architecture

* **Backend:** FastAPI, SQLite, FFmpeg (for assembly)
* **Frontend:** React + Vite
* **AI Provider:** Google Gemini API (Veo)
* **Job Execution:** Bounded concurrent execution using `ThreadPoolExecutor` within the backend process.

## Features & Supported Lifecycle States

The application orchestrates video projects through the following states:
1. `QUEUED` - Ingested from Excel.
2. `VALIDATING` - Checking requirements.
3. `SCRIPTING` - (Placeholder - not yet implemented natively)
4. `STORYBOARDING` - Breaking the script into individual shots of exact duration.
5. `PREPARING_REFERENCES` (Placeholder)
6. `GENERATING_AUDIO` (Placeholder)
7. `GENERATING_VIDEO` - Sending exact-length prompts to Veo (4-8s each).
8. `ASSEMBLING` - Using FFmpeg to compile and transcode the generated shots perfectly matching `target_duration`.
9. `VALIDATING_OUTPUT` - Verifying final artifact length, presence of audio, and format.
10. `READY_FOR_REVIEW` - Available in UI.
11. `COMPLETED` - Approved and finalized (Excel writeback occurs).
12. `FAILED` - Errored out at any stage.
13. `CANCELLED`

## Requirements

* Python 3.12+
* Node.js 18+
* FFmpeg & ffprobe (must be installed and in the system `PATH`)

## Setup

1. **Clone and Setup Backend Environment:**
   ```powershell
   cd backend
   python -m venv venv
   .\venv\Scripts\Activate
   pip install -r requirements.txt
   ```

2. **Configuration:**
   Copy `backend/.env.example` to `backend/.env` and update it:
   ```env
   GEMINI_API_KEY=your_key_here
   DATA_DIR=../data
   VIDEO_MODEL=veo-3.1-generate-preview
   EXCEL_WORKBOOK_PATH=../video_ideas.xlsx
   ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
   ```
   *Note: If you don't have a Veo-enabled Google Cloud billing account, leave the API key as is. The application provides graceful mocked fallback tests.*

3. **Database Migrations:**
   The database schema is initialized and migrated automatically upon starting the FastAPI application.

## Excel Workflow

1. Create a `video_ideas.xlsx` workbook in the root folder.
2. Ensure there is a sheet named `VideoIdeas` with columns: `id`, `video_idea`, `target_duration_seconds`, `aspect_ratio`, `status`, `project_id`.
3. Supported orientations: `16:9` (Landscape) and `9:16` (Portrait).
4. Put `QUEUED` in the status column.
5. Call `POST /api/orchestration/ingest` (or click Ingest in the UI) to load them.
6. Processing occurs in the background via a bounded `ThreadPoolExecutor` (Max 3 concurrent jobs).
7. Videos transition through `READY_FOR_REVIEW` and once explicitly approved, they transition to `COMPLETED`.
8. Final MP4 output paths and final statuses (`COMPLETED`, `FAILED`) are written directly back to the Excel file. Excel sync is decoupled from media pipeline, ensuring a media generation success is never discarded due to a locked spreadsheet.

## Audio Policy

The application strictly enforces an explicit audio policy:
- **`silent` (Default):** The generated video is forced to have no audio streams. If clips possess audio, they are dropped during FFmpeg assembly.
- **`preserve`:** The generated video preserves the audio of the source clips. A strict validation will fail the job if a source clip lacks audio when `preserve` mode is activated.

*Note: AI Narration and Music Mixing are not yet fully implemented.*

## Output Locations

Outputs are reliably deposited into the configured `DATA_DIR` directory:
- Temporary assembly artifacts: `DATA_DIR/projects/<id>/final/temp_<uuid>_final.mp4`
- Validated Final Videos: `DATA_DIR/projects/<id>/final/final.mp4`
- Raw Generated Shots: `DATA_DIR/projects/<id>/shots/shotX.mp4`

## Tests

The repository now uses `pytest` with a dedicated, deterministic automated test suite.

* **Offline Unit and Mocked API Pipeline Tests:**
  Run the automated test suite without hitting real paid API limits:
  ```powershell
  cd backend
  $env:PYTHONPATH = "d:\Antigravity_Projects\AI_Video_Studio\backend"
  pytest tests/
  ```

* **Genuine Media Integration Tests:**
  The suite includes `tests/test_media_integration.py` which synthetically generates exact 4-second `.mp4` chunks directly with local FFmpeg without consuming paid APIs, then assemblies and probes them to prove FFmpeg pipeline reliability. Includes frequency analysis of synthetic signals to guarantee correct clip alignment and silence policies.

## Known Limitations

- **Narration Provider:** The AI Script Generation (`SCRIPTING`) and Audio Speech (`GENERATING_AUDIO`) integrations are modeled but lack integrated backend provider wrappers in this release.
- **Shot Chunk limits:** External provider bounds dictate shots must be strictly between 4.0 and 8.0 seconds.

## Running the Application

**Start Backend:**
```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

**Start Frontend:**
```powershell
cd frontend
npm install
npm run dev
```
