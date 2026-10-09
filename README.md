# AI Video Studio

AI Video Generation Application using Google's Gemini/Veo API.

## Current Progress

- **Stage 1 (Core Veo Pipeline):** Verified working! We can securely queue, generate, and fetch videos asynchronously.
- **Stage 2 (Shot Generation):** We've built the backend routing to generate specific shots asynchronously via Veo.
- **Stage 3 (Storyboard Generation):** We successfully use structured LLM outputs to automatically parse a master prompt into `N` individual shots mapping to Veo's generation duration limitations while maintaining visual continuity rules.
- **Stage 4 (Regeneration):** The backend supports regenerating individual shots individually.
- **Stage 5 (Interactive React UI):** Created a beautiful, fully functional React frontend using Vite, TailwindCSS (v4), and Lucide Icons that interfaces with the FastAPI backend.
- **Stage 6 (Video Assembly):** We've integrated FFmpeg to losslessly concatenate approved shots into a single continuous sequence `final.mp4`.

## Architecture

- **Backend:** Python + FastAPI + SQLite
- **Frontend:** React + TypeScript (Vite + TailwindCSS)
- **AI Model:** `gemini-omni-1.1-flash` (Video) and `gemini-2.5-flash-lite` (Storyboard) via `google-genai` SDK.

## Setup & Running

### 1. Backend
```bash
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 3. Usage
Navigate to `http://localhost:5173/` in your browser.
Enter your Master Prompt, select a Target Duration, and click **Generate Storyboard**.
The AI will generate the storyboard shots. You can then **Generate** or **Regenerate** individual shots.
Once all shots are COMPLETED, click **Assemble Final Video**.

## Known Limitations
- The Veo API generation queue is often heavily loaded, which may result in longer queue times for individual shots.
- `gemini-3.5` models are currently experiencing high quota demand; `gemini-2.5-flash-lite` is actively used for storyboard generation as a fallback.
