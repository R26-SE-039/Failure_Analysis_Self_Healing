# NEXTGEN QA - Intelligent Failure Analysis & Self-Healing Framework

> **A microservice-based CI/CD intelligent testing platform** that automatically classifies test failures using machine learning, generates self-healing recommendations, detects flaky tests, and routes developer alerts. The backend and repair-agent live in this repository; the active Vite React frontend is maintained separately in `failure-analysis-self-healing-frontend`.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Microservices](#microservices)
- [ML Pipeline](#ml-pipeline)
- [API Reference](#api-reference)
- [Frontend Application](#frontend-application)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Tech Stack](#tech-stack)
- [Research & Dataset](#research--dataset)

---

## Overview

NEXTGEN QA is a research-grade intelligent QA platform designed to reduce manual effort in CI/CD pipelines by:

1. **Automatically classifying** test failures into root causes such as locator issues, synchronization, network errors, and application defects.
2. **Generating self-healing suggestions** with specific code-fix guidance for each failure type.
3. **Detecting flaky tests** using a rule-based and heuristic instability scoring system.
4. **Routing smart alerts** to the right stakeholder based on failure root cause.
5. **Powering dashboard views** through API endpoints consumed by the separate frontend repository.

The analysis pipeline runs through the FastAPI backend, persists results to the configured backend database, and delegates controlled repair planning/publishing to the repair-agent service. Neon PostgreSQL can be used as the hosted primary database, while the existing local SQLite database remains available for local development and fallback startup mode.

---

## Architecture

```text
+----------------------------------------------------------------+
| Active Frontend: Vite React project in sibling repository       |
| failure-analysis-self-healing-frontend                         |
| Dashboard | Submit Failure | Failures | Healing | Analytics     |
+-------------------------------+--------------------------------+
                                | REST
                                v
+----------------------------------------------------------------+
| FastAPI Backend / API Gateway (8000)                           |
| POST /analyze/ | /failures | /healing | /analytics | /dashboard |
| /api/repairs/:attempt_id/plan | /publish | /history             |
+---------------+----------------+-------------------------------+
                |                |
                v                v
+-----------------------------+  +-------------------------------+
| PostgreSQL application DB   |  | Repair Agent Service (8010)   |
| failures, healing, flaky,   |  | read-only repair plans and    |
| notifications, repair audit |  | controlled draft PR publishing|
+-----------------------------+  +-------------------------------+
```

### Analysis Pipeline (POST /analyze/)

```text
Step 1: ML Classification       -> root_cause + confidence score
Step 2: Action Policy           -> selected action and routing decision
Step 3: Healing / Audit         -> repair guidance or safe notification audit
Step 4: Flaky Detection         -> instability score + risk level
Step 5: Persist to DB           -> dashboard and history read models
Step 6: Controlled Repair Flow  -> optional plan/publish via repair-agent
```

---

## Project Structure

```text
failure-analysis-self-healing/
|
|-- backend/                        # FastAPI API gateway and application services
|   |-- requirements.txt
|   `-- app/
|       |-- main.py                 # FastAPI app, CORS, router registration
|       |-- database.py             # SQLAlchemy engine/session
|       |-- models/                 # Failure, healing, flaky, notification, repair audit ORM models
|       |-- routers/                # analyze, dashboard, failures, healing, analytics, repairs, notifications
|       `-- services/               # classifier, GitHub Actions, repair, redaction, orchestration services
|
|-- repair-agent/                   # Repair planning and controlled publishing service
|   |-- requirements.txt
|   |-- repair_agent/               # FastAPI app, planner, publisher, MCP brokers, provider clients
|   `-- tests/
|
|-- docs/                           # Architecture diagrams and project notes
|
|-- research/                       # ML data, model artifacts, and training scripts
|
`-- README.md
```

The old in-repository `frontend/` folder has been removed. Use the sibling repository `failure-analysis-self-healing-frontend` for the active Vite React frontend.

---

## Microservices

| Service | Location | Default Port | Purpose |
|---------|----------|--------------|---------|
| Backend API | `backend/` | 8000 | API gateway, failure analysis, persistence, repair history |
| Repair Agent | `repair-agent/` | 8010 | Read-only repair planning and controlled branch/PR publishing |
| Frontend | `../failure-analysis-self-healing-frontend` | 5173 | Vite React dashboard consuming backend APIs |

---

## ML Pipeline

The classifier model artifact is stored under `research/models/`. Training utilities live under `research/scripts/` and can be run independently from the backend service.

---

## API Reference

Common backend endpoints:

| Endpoint | Purpose |
|----------|---------|
| `POST /analyze/` | Analyze a CI/CD failure payload |
| `GET /dashboard/summary` | Dashboard summary metrics |
| `GET /dashboard/trend` | Failure trend chart data |
| `GET /failures/` | Paginated failure records |
| `GET /failures/{test_id}` | Failure detail |
| `GET /healing/` | Healing action records |
| `GET /analytics/flaky-tests` | Flaky-test analytics |
| `POST /api/repairs/{attempt_id}/plan` | Request a read-only repair plan |
| `POST /api/repairs/{attempt_id}/publish` | Publish a controlled repair branch/draft PR |
| `GET /api/repairs/history` | Safe repair history projection |

---

## Frontend Application

The active frontend is not stored in this repository. It lives in the sibling project:

```text
../failure-analysis-self-healing-frontend
```

That project is a Vite React TypeScript app and should call this backend at `http://127.0.0.1:8000` or through its Vite dev proxy. Repair-agent operations should normally be initiated through backend `/api/repairs/...` endpoints so server-side tokens and repair-agent credentials are never exposed to browser code.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Neon PostgreSQL for hosted persistence, or local SQLite through `LOCAL_DATABASE_URL`
- Node.js 20+ only when running the separate frontend repository

### 1. Train or Verify the Model

```bash
pip install scikit-learn imbalanced-learn pandas numpy joblib
python research/scripts/train_model.py
```

### 2. Run the Backend Gateway

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Run the Repair Agent

```bash
cd repair-agent
pip install -r requirements.txt
uvicorn repair_agent.api:app --reload --port 8010
```

### 4. Run the Separate Frontend

```bash
cd ../failure-analysis-self-healing-frontend
pnpm install
pnpm dev
```

### 5. Access the Application

| Interface | URL |
|-----------|-----|
| Frontend dashboard | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Backend Swagger docs | http://localhost:8000/docs |
| Repair Agent API | http://localhost:8010 |

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_MODE` | Database selection mode: `neon`, `local`, or `auto` | `local` |
| `DATABASE_URL` | Neon PostgreSQL connection string. Keep SSL settings in the URL when required. | Required for `neon`; optional for `auto` |
| `LOCAL_DATABASE_URL` | Local SQLite SQLAlchemy URL used for local mode and auto fallback | `sqlite:///./app.db` |
| `API_GATEWAY_URL` | API Gateway base URL used by Component 3 to load the selected project Git configuration with the user JWT | Required for user-triggered GitHub Actions analysis |
| `GITHUB_ALLOWED_REPOSITORIES` | Optional defense-in-depth allowlist for controlled repair/publish repositories | Optional |
| `REPAIR_AGENT_URL` | Repair-agent base URL used by backend repair client | `http://127.0.0.1:8010` |

`DATABASE_MODE=neon` fails startup if Neon cannot be reached. `DATABASE_MODE=local` uses the local SQLite database. `DATABASE_MODE=auto` tries Neon once during startup and falls back to SQLite only if the initial Neon connection fails. The selected database does not change during normal API requests.

For private repositories, configure the repository URL and PAT on the Project Details -> Git Configuration screen. Component 3 reuses the logged-in user JWT to load that project configuration through the API Gateway for user-triggered GitHub Actions analysis. The PAT is kept in backend memory only for the GitHub request and is not stored by Component 3. Unattended/background jobs without a user JWT require a future server-to-server credential contract from auth-service.

### Separate Frontend (`../failure-analysis-self-healing-frontend/.env`)

Use the environment examples in the frontend repository. In local development it can call this backend through its Vite dev proxy or directly at `http://127.0.0.1:8000` when CORS allows the frontend origin.

---

## Tech Stack

### Backend and Repair Services

| Technology | Purpose |
|------------|---------|
| Python 3.11 | Runtime |
| FastAPI | REST APIs |
| SQLAlchemy | ORM for PostgreSQL |
| Pydantic | Request/response validation |
| httpx | Async HTTP clients |
| scikit-learn / joblib | Root-cause model inference |

### Frontend

| Technology | Purpose |
|------------|---------|
| Vite React TypeScript | Separate dashboard project |
| Tailwind CSS | Styling |
| Recharts | Dashboard charts |
| Lucide React | Icons |

---

## Research & Dataset

Research data, training scripts, and model artifacts are kept in `research/`. These files are independent of the removed frontend folder.
