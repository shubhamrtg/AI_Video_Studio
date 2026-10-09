# AI Video Studio

An end-to-end automated platform for generating videos from ideas in an Excel spreadsheet.

## Architecture

* **Backend:** FastAPI, SQLite, FFmpeg (for assembly)
* **Frontend:** React + Vite
* **AI Provider:** Google Gemini API (Veo)

## Features & Supported Lifecycle States

The application orchestrates video projects through the following states:
1. `QUEUED` - Ingested from Excel.
2. `VALIDATING` - Checking requirements.
3. `SCRIPTING` - Generating a text script.
4. `STORYBOARDING` - Breaking the script into individual shots of exact duration.
5. `PREPARING_REFERENCES` (Placeholder)
6. `GENERATING_AUDIO` (Placeholder)
7. `GENERATING_VIDEO` - Sending exact-length prompts to Veo (4-8s each).
8. `ASSEMBLING` - Using FFmpeg to compile and transcode the generated shots.
9. `VALIDATING_OUTPUT` - Verifying final artifact length and format.
10. `READY_FOR_REVIEW` - Available in UI.
11. `COMPLETED` - Approved and finalized.
12. `FAILED` - Errored out at any stage.
13. `CANCELLED`

## Requirements

* Python 3.12+
* Node.js 18+
* FFmpeg (must be installed and in the system `PATH`)

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
3. Put `QUEUED` in the status column.
4. Call `POST /api/orchestration/ingest` (or click Ingest in the UI) to load them.

## Tests

The repository now uses `pytest` with a dedicated, deterministic automated test suite.

* **Unit and Mocked Pipeline Tests:**
  Run the automated test suite without hitting real paid API limits:
  ```powershell
  cd backend
  $env:PYTHONPATH = "d:\Antigravity_Projects\AI_Video_Studio\backend"
  pytest tests/
  ```
  *(These tests use a temporary isolated database and temporary mock Excel sheets.)*

* **Real Provider Integration Test (Optional):**
  If you have an active API key and FFmpeg installed, you can trigger an end-to-end run by starting the backend and hitting the endpoint manually or via the frontend UI.

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
