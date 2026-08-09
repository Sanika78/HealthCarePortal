# Healthcare Analytics & Disease Prediction System

A full-stack, MongoDB-first healthcare operations and analytics platform. It includes JWT-style authentication, role access, patient/doctor/appointment CRUD, pharmacy inventory, lab reports, ETL uploads, research-only risk estimates, dashboard analytics, audit logging, and exports.

## Run locally

1. Start MongoDB: `docker compose up mongo -d` (or set `MONGODB_URL`).
2. API: `cd backend && python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000`
3. UI: `cd frontend && npm install && npm run dev`

The frontend runs on `http://localhost:5173`, API docs are at `http://localhost:8000/docs`.

### Demo accounts

All demo accounts use password `Demo@123`:

| Role | Email |
|---|---|
| Admin | admin@carepulse.demo |
| Doctor | doctor@carepulse.demo |
| Receptionist | reception@carepulse.demo |
| Lab Technician | lab@carepulse.demo |
| Pharmacist | pharmacy@carepulse.demo |

Predictions are educational/research risk estimates only—not diagnoses or medical advice.
