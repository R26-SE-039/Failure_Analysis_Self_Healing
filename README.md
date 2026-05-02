# 🔬 NEXTGEN QA — Intelligent Failure Analysis & Self-Healing Framework

> **A microservice-based CI/CD intelligent testing platform** that automatically classifies test failures using machine learning, generates self-healing recommendations, detects flaky tests, and routes developer alerts — all orchestrated through a modern Next.js dashboard.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Microservices](#microservices)
- [ML Pipeline](#ml-pipeline)
- [API Reference](#api-reference)
- [Frontend Dashboard](#frontend-dashboard)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Tech Stack](#tech-stack)
- [Research & Dataset](#research--dataset)

---

## Overview

NEXTGEN QA is a research-grade intelligent QA platform designed to reduce manual effort in CI/CD pipelines by:

1. **Automatically classifying** test failures into root causes (e.g., locator issues, synchronization, network errors, application defects)
2. **Generating self-healing suggestions** with specific code fixes for each failure type
3. **Detecting flaky tests** using a rule-based + heuristic instability scoring system
4. **Routing smart alerts** to the right stakeholder (developer, DevOps, manager) based on failure root cause
5. **Visualizing trends** through a real-time analytics dashboard

The entire analysis pipeline runs in **< 1 second** per failure using a pre-trained ensemble ML model, then persists results to PostgreSQL for trend analysis.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend (3000)                  │
│  Dashboard │ Failures │ Healing │ Analytics │ Model │ Notify    │
└────────────────────────────┬────────────────────────────────────┘
                             │  REST
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   API Gateway / FastAPI (8000)                  │
│  POST /analyze  →  Full Pipeline Orchestrator                   │
│  GET  /failures │ /healing │ /analytics │ /dashboard │ /analyze │
└──────────┬──────────┬──────────┬──────────┬────────────────────┘
           │          │          │          │
           ▼          ▼          ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
    │ML Service│ │ Healing  │ │Analytics │ │  Notification    │
    │  :8001   │ │ Service  │ │ Service  │ │    Service       │
    │          │ │  :8002   │ │  :8003   │ │     :8004        │
    │Classifier│ │Healing   │ │Flaky Test│ │Alert Routing     │
    │Retrain   │ │Engine    │ │Detector  │ │(Dev/DevOps/Mgr)  │
    └──────────┘ └──────────┘ └──────────┘ └──────────────────┘
                             │
                             ▼
                   ┌─────────────────┐
                   │  PostgreSQL DB  │
                   │    :5432        │
                   │ failure_analysis│
                   └─────────────────┘
```

### Analysis Pipeline (POST /analyze)

Each test failure flows through 5 sequential steps:

```
Step 1: ML Classification  →  root_cause + confidence score
Step 2: Self-Healing       →  repair_type + old_value + new_value + recommendation
Step 3: Flaky Detection    →  is_flaky + flaky_probability + risk_level
Step 4: Notification       →  alert routed to developer / devops (if needed)
Step 5: Persist to DB      →  all results saved for dashboard/trend analysis
```

---

## Project Structure

```
failure-analysis-self-healing/
│
├── docker-compose.yml              # Orchestrates all 7 services
│
├── backend/                        # API Gateway (FastAPI, port 8000)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                 # FastAPI app + CORS + router registration
│       ├── database.py             # SQLAlchemy engine + session
│       ├── models/
│       │   ├── failure.py          # Failure ORM model
│       │   ├── healing.py          # HealingAction ORM model
│       │   ├── flaky_test.py       # FlakyTest ORM model
│       │   └── notification.py     # Notification ORM model
│       ├── routers/
│       │   ├── analyze.py          # POST /analyze — full pipeline orchestrator
│       │   ├── dashboard.py        # GET /dashboard/summary
│       │   ├── failures.py         # CRUD for failure records
│       │   ├── healing.py          # CRUD for healing actions
│       │   ├── analytics.py        # Analytics + flaky tests
│       │   └── notifications.py    # Notification management
│       └── services/
│           └── gateway_client.py   # HTTP client for all 4 microservices
│
├── services/
│   ├── ml-service/                 # ML Classifier (FastAPI, port 8001)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── models/                 # Trained model artifacts (*.pkl, metrics.json)
│   │   └── app/
│   │       ├── main.py             # /classify, /retrain, /metrics, /health
│   │       ├── classifier.py       # Model loading + predict() function
│   │       └── schemas.py          # Pydantic request/response schemas
│   │
│   ├── healing-service/            # Self-Healing Engine (FastAPI, port 8002)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── main.py             # POST /heal, GET /health
│   │       ├── healing_engine.py   # Rule-based repair strategy engine
│   │       └── schemas.py
│   │
│   ├── analytics-service/          # Predictive Analytics (FastAPI, port 8003)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── main.py             # POST /check-flaky, GET /health
│   │       ├── flaky_detector.py   # Heuristic instability scoring
│   │       └── schemas.py
│   │
│   └── notification-service/       # Alert Routing (FastAPI, port 8004)
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app/
│           ├── main.py             # POST /notify, GET /health
│           ├── alert_router.py     # Root cause → stakeholder routing
│           └── schemas.py
│
├── frontend/                       # Next.js Dashboard (port 3000)
│   ├── Dockerfile
│   ├── package.json
│   ├── app/
│   │   └── (app-dashboard)/
│   │       ├── page.tsx            # Main dashboard with stats + charts
│   │       ├── layout.tsx          # Sidebar + topbar layout
│   │       ├── failures/           # Failure list + detail pages
│   │       ├── healing/            # Self-healing actions page
│   │       ├── analytics/          # Flaky test analytics
│   │       ├── model/              # ML model metrics page
│   │       ├── notifications/      # Alert management page
│   │       └── submit/             # Manual failure submission form
│   └── components/
│       ├── sidebar.tsx             # Navigation sidebar
│       ├── topbar.tsx              # Top navigation bar
│       ├── stat-card.tsx           # Summary metric card
│       ├── status-badge.tsx        # Colored status indicator
│       ├── failure-trend-chart.tsx # Recharts failure trend line chart
│       └── flaky-risk-chart.tsx    # Recharts flaky risk distribution chart
│
└── research/                       # ML Research & Training
    ├── data/
    │   └── final_training_dataset.csv   # Synthetic labeled training dataset
    ├── models/                          # Saved model artifacts
    ├── outputs/                         # Training reports
    └── scripts/
        ├── generate_synthetic_dataset.py # Dataset generation script
        ├── train_model.py               # Full ML training pipeline
        ├── 01_dataset_understanding.py  # EDA script
        ├── 02_baseline_text_classification.py
        └── 03_random_forest_structured.py
```

---

## Microservices

### 1. 🤖 ML Classifier Service — Port `8001`

Loads pre-trained scikit-learn model artifacts and classifies test failures into root causes.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service readiness + loaded model name |
| `/classify` | POST | Classify a failure → root_cause + confidence |
| `/retrain` | POST | Trigger background model retraining |
| `/retrain/status` | GET | Check retraining progress |
| `/metrics` | GET | Return full model performance metrics |

**Root Cause Classes:**
| Class | Description |
|-------|-------------|
| `locator_issue` | Fragile CSS/XPath selectors that break on DOM change |
| `synchronization_issue` | Race conditions, timing failures, hard sleeps |
| `test_data_issue` | Stale/missing test data, pre-condition failures |
| `environment_failure` | Infrastructure down (DB, Docker, Grid) |
| `network_api_error` | API timeouts, connection refused, HTTP 5xx |
| `application_defect` | Genuine code bugs requiring developer fix |

**Feature Vector (per request):**
```
TF-IDF(error_message) [500]  +  TF-IDF(stack_trace) [200]
+ OrdinalEncoded(failure_stage, severity, failure_type) [3]
+ Numeric(retry_count, test_duration_sec, cpu_usage_pct, memory_usage_mb, is_flaky_test) [5]
= 708 total features
```

---

### 2. 🔧 Self-Healing Service — Port `8002`

Rule-based engine that generates targeted repair strategies for each root cause.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/heal` | POST | Generate repair suggestion for a failure |

**Healing Strategies:**

| Root Cause | Repair Type | Auto-Status |
|------------|-------------|-------------|
| `locator_issue` | Replace fragile selector with `[data-testid='...']` | `Suggested` |
| `synchronization_issue` | Upgrade `time.sleep()` → `WebDriverWait(...).until(EC...)` | `Suggested` |
| `test_data_issue` | Re-seed DB with `@BeforeEach` test data factory | `Pending` |
| `environment_failure` | Retry after environment health check | `Pending` |
| `network_api_error` | Exponential backoff retry (max 3 attempts) | `Pending` |
| `application_defect` | Developer alert — no auto-repair possible | `Rejected` |

---

### 3. 📊 Analytics Service — Port `8003`

Computes a heuristic **instability score** (0.0–1.0) to predict flaky test risk.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/check-flaky` | POST | Compute flaky risk for a test |

**Instability Score Factors:**
```
retry_count contribution   →  up to 0.40
failure_type (Timeout etc) →  up to 0.20
failure_stage = "test"     →  +0.10
severity (LOW = riskier)   →  up to 0.15
test_duration > 120s       →  +0.10
─────────────────────────────────────────
Score ≥ 0.65 = High Risk
Score ≥ 0.40 = Medium Risk
Score <  0.40 = Low Risk
```

---

### 4. 🔔 Notification Service — Port `8004`

Routes failure alerts to the appropriate stakeholder based on root cause.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/notify` | POST | Create and route an alert notification |

**Auto-Routing Table:**

| Root Cause | Routed To |
|------------|-----------|
| `application_defect` | 👨‍💻 Software Developer |
| `test_data_issue` | 👨‍💻 Software Developer |
| `locator_issue` | 👨‍💻 Software Developer |
| `synchronization_issue` | 👨‍💻 Software Developer |
| `environment_failure` | ⚙️ DevOps Engineer |
| `network_api_error` | ⚙️ DevOps Engineer |

---

### 5. 🚪 API Gateway — Port `8000`

FastAPI gateway that orchestrates the full analysis pipeline and exposes CRUD endpoints.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /analyze` | POST | **Full pipeline**: ML → Heal → Flaky → Notify → Save |
| `GET /analyze/health` | GET | Health check of all 4 microservices |
| `GET /analyze/metrics` | GET | Proxy ML model metrics |
| `POST /analyze/retrain` | POST | Trigger model retraining |
| `GET /analyze/retrain/status` | GET | Poll retraining status |
| `GET /dashboard/summary` | GET | Aggregate stats for dashboard |
| `GET /failures` | GET | List all failure records |
| `GET /failures/{id}` | GET | Get single failure detail |
| `GET /healing` | GET | List all healing actions |
| `GET /analytics` | GET | Flaky test list |
| `GET /notifications` | GET | List all notifications |

---

## ML Pipeline

### Training Script: `research/scripts/train_model.py`

The training pipeline runs 7 steps:

```
[1/7] Load Dataset          →  research/data/final_training_dataset.csv
[2/7] Feature Engineering   →  TF-IDF + OrdinalEncoder + Numeric
[3/7] Label Encoding        →  6 root cause classes
[4/7] Train/Test Split      →  80% train / 20% test (stratified)
      + SMOTE               →  Balance minority classes
[5/7] Train 3 Models        →  Random Forest | Gradient Boosting | Voting Ensemble
[6/7] Evaluate              →  Accuracy, Macro F1, per-class metrics
[7/7] Save Artifacts        →  research/models/ + services/ml-service/models/
```

**Model Artifacts Saved:**
| File | Contents |
|------|----------|
| `classifier.pkl` | Best trained model (RF / GB / Ensemble) |
| `vectorizer_msg.pkl` | TF-IDF vectorizer for error_message |
| `vectorizer_trace.pkl` | TF-IDF vectorizer for stack_trace |
| `cat_encoder.pkl` | OrdinalEncoder for categorical features |
| `label_encoder.pkl` | LabelEncoder for root cause classes |
| `metrics.json` | Full evaluation metrics (accuracy, F1, per-class) |

### Run Training Manually

```bash
# From project root
cd research
pip install scikit-learn imbalanced-learn pandas numpy joblib
python scripts/train_model.py
```

> Artifacts are automatically copied to `services/ml-service/models/` after training.

---

## API Reference

### POST `/analyze` — Full Analysis Pipeline

**Request:**
```json
{
  "test_name": "LoginTest_checkPasswordField",
  "pipeline": "CI/CD Pipeline #42",
  "error_message": "Element not found: #password-field",
  "stack_trace": "NoSuchElementException at LoginPage.java:87",
  "failure_stage": "test",
  "failure_type": "Test Failure",
  "severity": "HIGH",
  "retry_count": 2,
  "test_duration_sec": 45.3,
  "cpu_usage_pct": 72.5,
  "memory_usage_mb": 1280,
  "is_flaky_test": 0,
  "old_locator": "#password-field"
}
```

**Response:**
```json
{
  "test_id": "TEST-A3F7B2D1",
  "status": "FAIL",
  "pipeline": {
    "classification": {
      "root_cause": "locator_issue",
      "confidence": 0.8721,
      "all_probabilities": { "locator_issue": 0.8721, "synchronization_issue": 0.05, ... },
      "model_used": "Ensemble"
    },
    "healing": {
      "healing_id": "H-C4E1A2B3",
      "repair_type": "Locator Repair",
      "old_value": "#password-field",
      "new_value": "[data-testid='password-field']",
      "recommendation": "Update the failing element locator to use a stable data-testid...",
      "status": "Suggested",
      "developer_alert": false
    },
    "flaky_analysis": {
      "test_id": "TEST-A3F7B2D1",
      "is_flaky": true,
      "flaky_probability": 0.55,
      "risk_level": "Medium",
      "instability_score": "55%",
      "recent_pattern": "FAIL, PASS, FAIL, PASS, FAIL"
    },
    "notification": null
  },
  "saved_to_db": true
}
```

---

## Frontend Dashboard

Built with **Next.js 16 + React 19 + TypeScript + Tailwind CSS v4**.

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/` | Summary cards + failure trend chart + flaky risk chart + recent failures |
| **Failures** | `/failures` | All failure records with root cause, confidence, healing status |
| **Failure Detail** | `/failures/[id]` | Full detail: classification + healing + flaky + notification |
| **Self-Healing** | `/healing` | All healing actions with old/new values |
| **Analytics** | `/analytics` | Flaky test list with risk levels + instability scores |
| **Model Metrics** | `/model` | ML model accuracy, F1 scores, per-class metrics, retrain button |
| **Notifications** | `/notifications` | Developer/DevOps alert log |
| **Submit Failure** | `/submit` | Manual failure submission form |

### Key Frontend Components

| Component | File | Purpose |
|-----------|------|---------|
| `Sidebar` | `components/sidebar.tsx` | Navigation with active state highlighting |
| `StatCard` | `components/stat-card.tsx` | Metric summary cards (failures, healing, flaky, alerts) |
| `StatusBadge` | `components/status-badge.tsx` | Color-coded status pills |
| `FailureTrendChart` | `components/failure-trend-chart.tsx` | Recharts line chart for failure trends |
| `FlakyRiskChart` | `components/flaky-risk-chart.tsx` | Recharts distribution chart for flaky risk |

---

## Getting Started

### Prerequisites

- Docker Desktop (with Docker Compose v2)
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### 1. Clone & Train the Model

```bash
git clone <repo-url>
cd failure-analysis-self-healing

# Install Python dependencies for training
pip install scikit-learn imbalanced-learn pandas numpy joblib

# Train the ML model (required before first run)
python research/scripts/train_model.py
```

### 2. Launch All Services with Docker Compose

```bash
docker compose up --build
```

This starts 7 containers:

| Container | Service | Port |
|-----------|---------|------|
| `nextgenqa-db` | PostgreSQL 16 | 5432 |
| `nextgenqa-ml` | ML Classifier | 8001 |
| `nextgenqa-healing` | Self-Healing Engine | 8002 |
| `nextgenqa-analytics` | Analytics / Flaky | 8003 |
| `nextgenqa-notification` | Notification Router | 8004 |
| `nextgenqa-gateway` | API Gateway | 8000 |
| `nextgenqa-frontend` | Next.js Dashboard | 3000 |

### 3. Access the Application

| Interface | URL |
|-----------|-----|
| **Dashboard** | http://localhost:3000 |
| **API Gateway** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **ML Service Docs** | http://localhost:8001/docs |
| **Healing Service Docs** | http://localhost:8002/docs |
| **Analytics Service Docs** | http://localhost:8003/docs |
| **Notification Service Docs** | http://localhost:8004/docs |

### 4. Local Development (Frontend)

```bash
cd frontend
npm install
npm run dev     # → http://localhost:3000
```

### 5. Local Development (Backend Gateway)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 6. Trigger Model Retraining via API

```bash
curl -X POST http://localhost:8000/analyze/retrain

# Poll retraining status
curl http://localhost:8000/analyze/retrain/status
```

---

## Environment Variables

### API Gateway (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:Shani@localhost:5432/failure_analysis_db` |
| `ML_SERVICE_URL` | ML classifier base URL | `http://ml-service:8001` |
| `HEALING_SERVICE_URL` | Self-healing service URL | `http://healing-service:8002` |
| `ANALYTICS_SERVICE_URL` | Analytics service URL | `http://analytics-service:8003` |
| `NOTIFICATION_SERVICE_URL` | Notification service URL | `http://notification-service:8004` |

### Frontend (`frontend/.env.local`)

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | API Gateway URL for browser requests | `http://localhost:8000` |

---

## Tech Stack

### Backend & Microservices
| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.11 | Runtime for all services |
| FastAPI | 0.115–0.128 | REST API framework |
| SQLAlchemy | 2.0 | ORM for PostgreSQL |
| Pydantic | 2.x | Request/response validation |
| psycopg2 | 2.9 | PostgreSQL driver |
| uvicorn | 0.30–0.39 | ASGI server |
| httpx | 0.27 | Async HTTP client (gateway → services) |

### Machine Learning
| Technology | Version | Purpose |
|------------|---------|---------|
| scikit-learn | 1.6.1 | ML models (RF, GB, Ensemble, TF-IDF) |
| imbalanced-learn | latest | SMOTE oversampling for class imbalance |
| numpy | 2.0.2 | Numerical feature processing |
| joblib | 1.5.3 | Model serialization |
| scipy | latest | Sparse matrix operations |
| pandas | latest | Dataset manipulation |

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 16.2.3 | React framework + SSR |
| React | 19.2.4 | UI library |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 4.x | Utility-first styling |
| Recharts | 3.8.1 | Data visualization charts |
| Lucide React | 1.8.0 | Icon library |

### Infrastructure
| Technology | Version | Purpose |
|------------|---------|---------|
| PostgreSQL | 16 (Alpine) | Primary database |
| Docker | 24+ | Containerization |
| Docker Compose | v2 | Multi-service orchestration |

---

## Research & Dataset

### Synthetic Dataset

The training dataset (`research/data/final_training_dataset.csv`) is synthetically generated to simulate real CI/CD failure scenarios across all 6 root cause classes. It includes:

- `error_message` — Realistic error text (NoSuchElementException, TimeoutException, etc.)
- `stack_trace` — Simulated stack traces with framework-specific patterns
- `failure_stage` — `build`, `test`, `deploy`
- `failure_type` — `Test Failure`, `Timeout`, `Network Error`, `Build Error`, `Deploy Error`
- `severity` — `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `retry_count` — Number of retry attempts (0–5)
- `test_duration_sec` — Test execution time in seconds
- `cpu_usage_pct` — CPU utilization at time of failure
- `memory_usage_mb` — Memory usage at time of failure
- `is_flaky_test` — Boolean flaky test indicator
- `root_cause` — **Target label** (one of 6 classes)

### Research Scripts

| Script | Purpose |
|--------|---------|
| `generate_synthetic_dataset.py` | Generates balanced labeled training data |
| `01_dataset_understanding.py` | Exploratory data analysis |
| `02_baseline_text_classification.py` | Text-only TF-IDF baseline |
| `03_random_forest_structured.py` | Structured feature Random Forest |
| `train_model.py` | Full production training pipeline |

---

## Database Schema

### Tables

**`failures`** — Core failure records
```
id, test_id, test_name, pipeline, status, root_cause, confidence, 
healing, logs, stack_trace, recommendation, developer_alert, created_at
```

**`healing_actions`** — Repair suggestions
```
id, healing_id, failure_test_id, test_name, repair_type, 
old_value, new_value, status, created_at
```

**`flaky_tests`** — Flaky test records
```
id, test_code, test_name, instability_score, recent_pattern, 
risk_level, created_at
```

**`notifications`** — Alert records
```
id, failure_test_id, test_name, root_cause, message, target, created_at
```

---

## Healthcheck Endpoints

All services expose `GET /health` — Docker Compose uses these for dependency management:

```bash
curl http://localhost:8000/         # Gateway root
curl http://localhost:8001/health   # ML Service
curl http://localhost:8002/health   # Healing Service
curl http://localhost:8003/health   # Analytics Service
curl http://localhost:8004/health   # Notification Service
```

---

## License

This project was developed as part of a 4th-year undergraduate research project at **SLIIT (Sri Lanka Institute of Information Technology)**.

---

<div align="center">
  <sub>Built with ❤️ for intelligent QA automation research</sub>
</div>
