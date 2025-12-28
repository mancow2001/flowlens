# FlowLens

**Application Dependency Mapping Platform**

FlowLens is an open-source platform that ingests network flow data (NetFlow, sFlow, IPFIX) and automatically discovers application dependencies, maps network topology, and provides real-time visibility into your infrastructure.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-blue.svg)](https://www.typescriptlang.org/)

---

## Features

### Core Capabilities

- **Flow Collection** - Ingests NetFlow v5/v9, sFlow, and IPFIX from network devices
- **Asset Discovery** - Automatically discovers network assets from flow data
- **Dependency Mapping** - Builds directed graphs of application-to-application communication
- **Gateway Detection** - Identifies routers and NAT devices in communication paths
- **Behavioral Classification** - Auto-classifies assets based on traffic patterns
- **CIDR Classification** - Rule-based classification by IP ranges for environment, datacenter, and location
- **Impact Analysis** - Calculate blast radius and identify single points of failure (SPOFs)
- **Change Tracking** - Audit trail of all asset and dependency changes
- **Alerting** - Configurable alert rules with real-time WebSocket notifications
- **Topology Visualization** - Interactive D3-based network graph

### Technical Highlights

- Async Python backend with FastAPI and SQLAlchemy 2.0
- PostgreSQL with table partitioning for high-volume flow data
- React + TypeScript frontend with Vite
- Real-time updates via WebSocket
- Prometheus metrics and structured JSON logging
- Docker Compose deployment

---

## Architecture

```
                                  ┌─────────────────┐
                                  │  Network Flows  │
                                  │  (NetFlow/sFlow)│
                                  └────────┬────────┘
                                           │ UDP 2055/6343
                                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         FlowLens Backend                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐              │
│  │  Ingestion   │──▶│  Enrichment  │──▶│  Resolution  │              │
│  │   Service    │   │   Service    │   │   Service    │              │
│  │              │   │  (DNS/GeoIP) │   │ (Aggregation)│              │
│  └──────────────┘   └──────────────┘   └──────┬───────┘              │
│                                               │                      │
│  ┌──────────────┐                    ┌────────▼───────┐              │
│  │Classification│◀───────────────────│    REST API    │              │
│  │   Service    │                    │   (FastAPI)    │              │
│  └──────────────┘                    └────────┬───────┘              │
│                                               │                      │
└───────────────────────────────────────────────┼──────────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────┐
                    │                           │                   │
                    ▼                           ▼                   ▼
             ┌────────────┐             ┌────────────┐      ┌────────────┐
             │ PostgreSQL │             │  Frontend  │      │ Prometheus │
             │     15     │             │  (React)   │      │  Metrics   │
             └────────────┘             └────────────┘      └────────────┘
```

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/flowlens/flowlens.git
   cd flowlens
   ```

2. **Start the services**

   ```bash
   docker compose up -d
   ```

3. **Run database migrations**

   ```bash
   docker compose exec api alembic upgrade head
   ```

4. **Access the UI**

   Open [http://localhost:3000](http://localhost:3000) in your browser.

### Configure Flow Sources

Point your network devices to send flows to FlowLens:

| Protocol | Port |
|----------|------|
| NetFlow v5/v9 | UDP 2055 |
| sFlow | UDP 6343 |
| IPFIX | UDP 2055 |

---

## Development Setup

### Backend

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=flowlens
export POSTGRES_PASSWORD=flowlens
export POSTGRES_DATABASE=flowlens

# Run migrations
alembic upgrade head

# Start the API server
uvicorn flowlens.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Running All Services

For local development with all services:

```bash
# Start PostgreSQL
docker compose up -d postgres

# In separate terminals:
python -m flowlens.ingestion.main      # Flow ingestion
python -m flowlens.enrichment.main     # DNS/GeoIP enrichment
python -m flowlens.resolution.main     # Dependency resolution
python -m flowlens.classification.main # Asset classification
uvicorn flowlens.api.main:app --reload # API server
```

---

## Configuration

FlowLens is configured via environment variables. Key settings:

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | localhost | PostgreSQL host |
| `POSTGRES_PORT` | 5432 | PostgreSQL port |
| `POSTGRES_USER` | flowlens | Database user |
| `POSTGRES_PASSWORD` | flowlens | Database password |
| `POSTGRES_DATABASE` | flowlens | Database name |
| `POSTGRES_POOL_SIZE` | 20 | Connection pool size |

### Ingestion

| Variable | Default | Description |
|----------|---------|-------------|
| `INGESTION_BIND_ADDRESS` | 0.0.0.0 | Listen address |
| `INGESTION_NETFLOW_PORT` | 2055 | NetFlow/IPFIX port |
| `INGESTION_SFLOW_PORT` | 6343 | sFlow port |
| `INGESTION_BATCH_SIZE` | 1000 | Batch size for DB writes |
| `INGESTION_QUEUE_MAX_SIZE` | 100000 | Max queue size before backpressure |

### API

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | 0.0.0.0 | API listen address |
| `API_PORT` | 8000 | API port |
| `API_CORS_ORIGINS` | * | Allowed CORS origins |
| `API_RATE_LIMIT_REQUESTS` | 100 | Rate limit per window |
| `API_RATE_LIMIT_WINDOW_SECONDS` | 60 | Rate limit window |
| `API_TOPOLOGY_MAX_NODES` | 5000 | Max nodes in topology response |
| `API_TOPOLOGY_MAX_EDGES` | 10000 | Max edges in topology response |

### Classification

| Variable | Default | Description |
|----------|---------|-------------|
| `CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD` | 0.70 | Confidence threshold for auto-classification |
| `CLASSIFICATION_MIN_OBSERVATION_HOURS` | 12 | Minimum observation time |
| `CLASSIFICATION_MIN_FLOWS_REQUIRED` | 100 | Minimum flows for classification |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | true | Enable authentication |
| `AUTH_SECRET_KEY` | change-me | JWT secret key (change in production!) |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | Token expiration |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | Log level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | json | Log format (json or console) |

See [Configuration Reference](#configuration-reference) for the complete list.

---

## API Reference

The REST API is available at `http://localhost:8000/api/v1`.

### Key Endpoints

#### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/assets` | List assets with filtering |
| GET | `/assets/{id}` | Get asset details |
| POST | `/assets` | Create asset |
| PATCH | `/assets/{id}` | Update asset |
| DELETE | `/assets/{id}` | Delete asset |
| GET | `/assets/{id}/dependencies` | Get asset dependencies |

#### Dependencies

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dependencies` | List dependencies |
| GET | `/dependencies/{id}` | Get dependency details |

#### Topology

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/topology` | Get network topology graph |
| POST | `/topology/subgraph` | Query filtered subgraph |

#### Classification

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/classification-rules` | List CIDR rules |
| POST | `/classification-rules` | Create rule |
| PATCH | `/classification-rules/{id}` | Update rule |
| DELETE | `/classification-rules/{id}` | Delete rule |
| GET | `/classification-rules/classify/{ip}` | Test IP classification |

#### Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/analysis/blast-radius/{id}` | Calculate blast radius |
| GET | `/analysis/spof` | Find single points of failure |
| GET | `/analysis/impact/{id}` | Impact analysis |

#### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | List alerts |
| GET | `/alert-rules` | List alert rules |
| POST | `/alert-rules` | Create alert rule |

#### Background Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tasks` | List background tasks |
| GET | `/tasks/{id}` | Get task status |
| POST | `/tasks/{id}/cancel` | Cancel running task |

#### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/health/live` | Liveness probe |
| GET | `/admin/health/ready` | Readiness probe |
| GET | `/admin/metrics` | Prometheus metrics |

### WebSocket

Connect to `/api/v1/ws` for real-time events:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.type, data.data);
};
```

Event types: `alert`, `asset_change`, `dependency_change`, `topology_update`

---

## Data Model

### Core Entities

**Asset** - Network endpoint (server, workstation, database, etc.)
- IP address (unique identifier)
- Asset type (server, database, load_balancer, router, etc.)
- Environment, datacenter, location
- Owner and team
- Traffic statistics (bytes in/out, connections)

**Service** - Port/protocol listening on an asset
- Port and protocol (TCP/UDP)
- Service type (http, https, mysql, ssh, etc.)
- Traffic statistics

**Dependency** - Directed edge between assets
- Source and target asset
- Target port and protocol
- Traffic volume and flow counts
- Temporal validity (first_seen, last_seen, valid_from, valid_to)

**Classification Rule** - CIDR-based asset classification
- CIDR range (e.g., 10.0.0.0/8)
- Environment, datacenter, location assignments
- Priority for overlapping ranges

### Asset Types

| Type | Description |
|------|-------------|
| `server` | Application server |
| `workstation` | End-user workstation |
| `database` | Database server |
| `load_balancer` | Load balancer |
| `firewall` | Firewall device |
| `router` | Router/gateway |
| `switch` | Network switch |
| `storage` | Storage system |
| `container` | Container instance |
| `virtual_machine` | Virtual machine |
| `cloud_service` | Cloud service endpoint |
| `unknown` | Unclassified (default) |

### Environment Values

| Value | Description |
|-------|-------------|
| `prod` | Production |
| `uat` | User Acceptance Testing |
| `qa` | Quality Assurance |
| `test` | Test environment |
| `dev` | Development |

---

## Classification

FlowLens provides two classification methods:

### CIDR-Based Classification

Define rules to automatically classify assets by IP range:

```json
{
  "name": "Production Servers",
  "cidr": "10.1.0.0/16",
  "environment": "prod",
  "datacenter": "US-East-1",
  "location": "New York",
  "is_internal": true,
  "priority": 100
}
```

Rules are applied:
- When assets are discovered
- When rules are created or updated
- More specific CIDRs (longer prefix) take priority
- For equal prefix lengths, lower priority value wins

### Behavioral Classification

Assets are automatically classified based on traffic patterns:

| Indicator | Classification |
|-----------|---------------|
| High fan-in, low fan-out | Server |
| High fan-out, low fan-in | Workstation |
| Database ports (3306, 5432, 1433, etc.) | Database |
| HTTP/HTTPS with many clients | Load Balancer |
| Routing between subnets | Router |

Classification confidence is tracked; assets are only auto-updated when confidence exceeds the threshold (default: 70%).

---

## Deployment

### Docker Compose (Recommended)

```bash
# Minimal deployment (PostgreSQL + all services)
docker compose up -d

# Full deployment (includes Kafka, Redis, monitoring)
docker compose -f docker-compose.full.yml up -d
```

### Environment Variables

Create a `.env` file:

```env
# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=flowlens
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DATABASE=flowlens

# API
API_PORT=8000
API_CORS_ORIGINS=http://localhost:3000

# Authentication (change in production!)
AUTH_SECRET_KEY=your-very-secure-secret-key

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Production Considerations

1. **Database**
   - Use a managed PostgreSQL instance or configure proper backups
   - Enable connection pooling (PgBouncer recommended for high load)
   - Configure appropriate `POSTGRES_POOL_SIZE`

2. **Security**
   - Change `AUTH_SECRET_KEY` to a strong random value
   - Configure `API_CORS_ORIGINS` to your frontend domain
   - Use HTTPS in production (reverse proxy with nginx/traefik)

3. **Scaling**
   - Enable Kafka for high-volume flow ingestion (>10k flows/sec)
   - Enable Redis for caching and session storage
   - Run multiple API workers (`API_WORKERS`)

4. **Monitoring**
   - Prometheus metrics at `/admin/metrics`
   - Health checks at `/admin/health/live` and `/admin/health/ready`
   - Structured JSON logs for log aggregation

### Data Retention

FlowLens automatically manages data retention:

| Data Type | Retention |
|-----------|-----------|
| Raw flow records | 7 days |
| 5-minute aggregates | 90 days |
| Hourly aggregates | 2 years |
| Daily aggregates | 2 years |
| Dependency stats | 2 years |

---

## Project Structure

```
flowlens/
├── src/flowlens/           # Backend Python code
│   ├── api/                # REST API (FastAPI)
│   │   ├── main.py         # Application factory
│   │   ├── routers/        # API endpoints
│   │   └── middleware.py   # Rate limiting, CORS
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── ingestion/          # Flow packet reception
│   │   └── parsers/        # NetFlow, sFlow, IPFIX parsers
│   ├── enrichment/         # DNS, GeoIP enrichment
│   ├── resolution/         # Dependency detection
│   ├── classification/     # Asset classification
│   ├── graph/              # Graph analysis algorithms
│   ├── tasks/              # Background task execution
│   └── common/             # Shared utilities
│       ├── config.py       # Configuration settings
│       ├── database.py     # Database connection
│       └── logging.py      # Structured logging
├── frontend/               # React frontend
│   ├── src/
│   │   ├── pages/          # Route pages
│   │   ├── components/     # React components
│   │   ├── services/       # API client
│   │   └── types/          # TypeScript types
│   └── package.json
├── migrations/             # Alembic database migrations
├── docker-compose.yml      # Docker deployment
├── pyproject.toml          # Python project config
└── README.md
```

---

## Technology Stack

### Backend

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.109+ |
| ORM | SQLAlchemy 2.0+ (async) |
| Database | PostgreSQL 15 |
| Validation | Pydantic 2.5+ |
| Migrations | Alembic 1.13+ |
| Logging | structlog 24.1+ |
| Metrics | prometheus-client |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | React 18 |
| Language | TypeScript 5.4 |
| Build Tool | Vite 5.3 |
| Styling | Tailwind CSS 3.4 |
| State | Zustand 4.5 |
| Data Fetching | TanStack Query 5.50 |
| Visualization | D3 7.9, Recharts 2.12 |

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 for Python code
- Use type hints throughout
- Write docstrings for public functions
- Add tests for new features
- Update documentation as needed

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/flowlens/flowlens/issues)
- **Discussions**: [GitHub Discussions](https://github.com/flowlens/flowlens/discussions)

---

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL toolkit and ORM
- [React](https://reactjs.org/) - JavaScript library for building user interfaces
- [D3.js](https://d3js.org/) - Data visualization library
- [Tailwind CSS](https://tailwindcss.com/) - Utility-first CSS framework
