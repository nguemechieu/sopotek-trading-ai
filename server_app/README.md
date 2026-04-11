# Sopotek Trading AI Server

This folder contains the full web-platform stack that was added for the SaaS and control-plane side of Sopotek Trading AI.

## Structure

- `backend/`: FastAPI API, JWT auth, WebSockets, Kafka bridge, async SQLAlchemy models
- `backend/`: FastAPI API, JWT auth, license/subscription system, WebSockets, Kafka bridge, async SQLAlchemy models
- `frontend/`: Next.js trading dashboard
- `kafka/`: topic definitions
- `docker/`: deployment files and environment example
- `docs/`: platform architecture notes

## Quick Start

```powershell
cd server_app\backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```powershell
cd server_app\frontend
npm install
npm run dev
```

```powershell
cd server_app\docker
docker compose -f docker-compose.platform.yml up --build
```

When you run the platform in Docker, the frontend uses `SOPOTEK_API_BASE_URL=http://backend:8000` for server-rendered auth and dashboard requests, while the browser keeps using `NEXT_PUBLIC_SOPOTEK_API_BASE_URL=http://localhost:8000`.

## Licensing

The backend now includes desktop and web licensing support:

- formatted keys like `SOPOTEK-ABCD-EFGH-IJKL`
- plan entitlements for `free`, `pro`, and `elite`
- hashed key storage and hashed device binding
- Stripe Checkout + webhook activation/suspension flows
- a desktop validation example in `backend/examples/desktop_license_validation.py`
