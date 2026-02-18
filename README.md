# 🛡️ AEGIS — Agentic Identity & Access Management

> **"No agent owns a key; the system lends the capability to act in real-time under surveillance."**

## What is AEGIS?

AEGIS is a **Deterministic Execution Proxy** for AI agents. It ensures that no
autonomous agent directly holds API keys, operates without budgetary guardrails,
or escapes human oversight. Every action is policy-evaluated, economically bounded,
and forensically recorded.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AEGIS Platform                                │
│                                                                      │
│  ┌─────────┐    ┌──────────────────────────────────────────────────┐ │
│  │ Next.js  │───▶│              FastAPI Backend                     │ │
│  │ Frontend │◀───│                                                  │ │
│  └─────────┘    │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │ │
│       ▲  WS     │  │ Proxy    │  │ Trust    │  │ Audit Service │  │ │
│       └─────────│  │ Engine   │  │ Engine   │  │ (Hash Chain)  │  │ │
│                 │  └────┬─────┘  └──────────┘  └───────────────┘  │ │
│                 │       │                                          │ │
│                 │  ┌────▼─────┐  ┌──────────┐  ┌───────────────┐  │ │
│                 │  │ Policy   │  │ Circuit  │  │ HITL Gateway  │  │ │
│                 │  │ (OPA)    │  │ Breaker  │  │               │  │ │
│                 │  └──────────┘  └──────────┘  └───────────────┘  │ │
│                 └──────────────────────────────────────────────────┘ │
│                         │              │                             │
│                    ┌────▼────┐    ┌────▼────┐                        │
│                    │PostgreSQL│    │  Redis  │                        │
│                    └─────────┘    └─────────┘                        │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Description |
|---|---|
| **Proxy Execution** | All agent API calls route through AEGIS with SSRF protection |
| **Trust Engine** | Dynamic trust scoring — agents earn autonomy through behavior |
| **Policy Evaluation** | OPA-based policies with JIT secret injection |
| **Economic Guardrails** | Per-agent wallets with daily/monthly spending limits |
| **Audit Chain** | Immutable, hash-chained audit log with CSV export |
| **Human-in-the-Loop** | High-risk actions require sponsor approval |
| **Circuit Breaker** | Auto-suspends agents on anomaly detection |
| **Real-time Events** | WebSocket notifications for HITL, anomalies, alerts |

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy (async), PostgreSQL, Redis
- **Frontend:** Next.js 14, TypeScript, Tailwind CSS
- **Policy Engine:** Open Policy Agent (OPA)
- **Infrastructure:** Docker Compose

## Quick Start

```bash
# 1. Clone and setup environment
cp .env.example .env    # Edit with your secrets

# 2. Start all services
docker compose up -d

# 3. Access the application
#    Frontend:  http://localhost:3000
#    Backend:   http://localhost:8000
#    API Docs:  http://localhost:8000/docs
```

### Local Development (without Docker)

```bash
# Backend
cd backend
python -m venv venv && venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Project Structure

```
AEGIS/
├── backend/
│   ├── app/
│   │   ├── api/           # Route handlers (auth, agents, proxy, dashboard, websocket)
│   │   ├── models/        # SQLAlchemy entities + database config
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── services/      # Business logic (trust, audit, identity, policy)
│   │   ├── middleware/    # Auth middleware + ASGI telemetry
│   │   ├── utils/         # Crypto, Redis, metrics, caching, SSRF guard
│   │   ├── config.py      # Settings from .env
│   │   └── main.py        # Application entrypoint
│   ├── test/              # Pytest suite
│   └── docker-compose.yml
└── frontend/
    └── src/
        ├── app/           # Next.js pages (login, dashboard, agents)
        ├── components/    # Reusable UI components
        ├── hooks/         # Custom hooks (WebSocket)
        ├── lib/           # API client + TypeScript types
        └── context/       # Auth context provider
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | User registration |
| POST | `/auth/login` | Login, returns JWT |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/agents/` | Register a new agent |
| GET | `/agents/` | List sponsor's agents |
| POST | `/proxy/execute` | Proxy an agent action |
| GET | `/dashboard/stats` | Aggregated dashboard data |
| GET | `/audit/` | Query audit log |
| WS | `/ws?token=...` | Real-time event stream |

## Running Tests

```bash
cd backend
python -m pytest test/ -v
```

## License

MIT
