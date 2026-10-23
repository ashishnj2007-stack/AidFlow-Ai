# AidFlow AI — Hackathon MVP

A local food-rescue coordination dashboard built with React + Vite, FastAPI and SQLite. Dispatch decisions and safety rules are enforced on the backend; no AI key or external service is required.

## Requirements
- Windows 10/11
- Python 3.10+
- Node.js 20+ (npm included)

## Start on Windows
Open two terminals in the `aidflow-ai` folder.

### Terminal 1 — API
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload
```
API: http://127.0.0.1:8000 — interactive API docs: http://127.0.0.1:8000/docs

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal and activate again.

### Terminal 2 — Frontend
```powershell
cd frontend
npm install
npm run dev
```
Open the URL Vite prints, usually http://localhost:5173.

## Live demo flow
1. Click **Reset demo** to load reproducible sample data.
2. Open **Dispatch & Simulation** and run **Smart dispatch**. The backend checks donation expiry, shelter demand/facilities and free rider capacity before creating reservations.
3. Use **Confirm pickup**, then **Confirm delivery** on an assignment. Completion only happens after explicit delivery confirmation.
4. Click **Simulate timeout** to expire a ghost reservation, release its reservation exactly once and attempt safe reassignment.
5. Click **Simulate shelter closure** to set an in-transit destination's demand to zero. The same assignment is rerouted to an eligible shelter when possible; otherwise an operator alert is recorded.
6. In **Donations**, create a raw ration kit and run dispatch. Shelters without clean water/cooking facilities are rejected with a specific reason in the API response/log.
7. In **Shelters**, change demand to zero during an in-transit assignment to test recovery.

## API
- `GET /api/dashboard`, `GET/POST /api/donations`, `GET/POST /api/riders`, `GET/POST /api/shelters`
- `POST /api/dispatch`
- `POST /api/assignments/{id}/claim|pickup|deliver|expire`
- `PATCH /api/shelters/{id}/demand`
- `POST /api/demo/reset`, `POST /api/demo/simulate-ghost`, `POST /api/demo/simulate-shelter-close`

The SQLite database (`backend/aidflow.db`) is created on first run and persists between requests. Reset demo replaces the sample data. Event history is persisted in an `events` table in addition to the four core operational tables.

## Notes
- Travel durations are deterministic demo values in `backend/dispatch.py` (`TRAVEL_MINUTES`). Claim timeout is configurable there (`CLAIM_TIMEOUT_MINUTES`). The prepared-meal demo expiry window is set by `demo_expiry_minutes` in `backend/seed.py` (default 45 minutes).
- Timestamps are stored as naive UTC values and serialized as ISO strings; the UI formats timestamps in the browser's local time. When creating a donation, the browser submits an ISO timestamp.
- This is a hackathon prototype, not a production food-safety or dispatch system. It uses a simple SQLite deployment and a deterministic travel-time estimate, not live routing.
