# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FlowLens is an Application Dependency Mapping platform that ingests network flow data (NetFlow v5/v9, sFlow, IPFIX) and automatically discovers application dependencies, maps network topology, and provides real-time visibility into infrastructure.

- **Backend**: Python 3.11+ with FastAPI, SQLAlchemy 2.0 (async), PostgreSQL
- **Frontend**: React 18 + TypeScript, Vite, Tailwind CSS, D3.js for visualization

## Build & Development Commands

### Backend

```bash
# Install dependencies (from repo root)
pip install -e ".[dev]"

# Run linting
ruff check src/ tests/
ruff check --fix src/ tests/   # auto-fix

# Run type checking (strict mode enabled)
mypy src/

# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/unit -v

# Run a single test file
pytest tests/unit/test_netflow_v5_parser.py -v

# Run a single test function
pytest tests/unit/test_netflow_v5_parser.py::test_parse_netflow_v5 -v

# Run with coverage
pytest --cov=src/flowlens --cov-report=html tests/

# Run database migrations
alembic upgrade head

# Start API server (dev mode)
uvicorn flowlens.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

npm install
npm run dev      # Dev server on http://localhost:3000
npm run build    # Production build
npm run lint     # ESLint
```

### Docker

```bash
docker compose up -d --build              # Minimal (PostgreSQL + services)
docker compose -f docker-compose.full.yml up -d --build  # Full stack with Kafka/Redis
```

## Architecture

The system consists of 5 services that process flows through a pipeline:

```
Network Devices → UDP 2055/6343
       ↓
1. INGESTION SERVICE (src/flowlens/ingestion/)
   - UDP listener parsing NetFlow/sFlow/IPFIX
   - Queue with backpressure handling
       ↓
2. ENRICHMENT SERVICE (src/flowlens/enrichment/)
   - DNS reverse lookups, GeoIP
   - Multi-worker with caching
       ↓
3. RESOLUTION SERVICE (src/flowlens/resolution/)
   - Flow aggregation (5-min windows)
   - Dependency graph building
   - Gateway/NAT detection
       ↓
4. CLASSIFICATION SERVICE (src/flowlens/classification/)
   - Heuristic-based asset type classification
   - CIDR rule matching
       ↓
5. API SERVICE (src/flowlens/api/)
   - FastAPI REST endpoints + WebSocket
   - Graph analysis (blast radius, SPOF, paths)
       ↓
Frontend (frontend/src/)
   - React SPA with D3 topology visualization
   - Zustand state, TanStack Query for data fetching
```

## Key Directories

- `src/flowlens/api/routers/` - REST API endpoint modules
- `src/flowlens/models/` - SQLAlchemy ORM models
- `src/flowlens/schemas/` - Pydantic request/response schemas
- `src/flowlens/ingestion/parsers/` - NetFlow v5/v9, sFlow, IPFIX parsers
- `src/flowlens/graph/` - Blast radius, SPOF, impact analysis algorithms
- `src/flowlens/common/config.py` - All settings via Pydantic BaseSettings
- `frontend/src/pages/` - React route pages
- `frontend/src/stores/` - Zustand state stores
- `migrations/versions/` - Alembic database migrations

## Testing

- Tests use pytest with `asyncio_mode = "auto"`
- `tests/conftest.py` provides async database fixtures and test client
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- Coverage minimum: 80%

## Code Style

**Backend**:
- Ruff for linting/formatting (line length: 100)
- MyPy strict mode with SQLAlchemy and Pydantic plugins
- Type hints required on all function signatures

**Frontend**:
- TypeScript strict mode
- ESLint with React hooks rules
- Path alias: `@/*` → `src/*`

## Configuration

All configuration via environment variables (see `.env.example`). Key settings in `src/flowlens/common/config.py` using Pydantic BaseSettings with nested models for each service.
