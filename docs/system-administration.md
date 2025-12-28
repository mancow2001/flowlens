# FlowLens System Administration Guide

This guide provides comprehensive instructions for deploying, configuring, and maintaining FlowLens in production environments.

---

## Table of Contents

1. [Deployment Overview](#deployment-overview)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Manual Deployment](#manual-deployment)
4. [Configuration Reference](#configuration-reference)
5. [Scaling Guidelines](#scaling-guidelines)
6. [Scaling with Redis and Kafka](#scaling-with-redis-and-kafka)
7. [Monitoring and Health Checks](#monitoring-and-health-checks)
8. [Backup and Recovery](#backup-and-recovery)
9. [Security Considerations](#security-considerations)
10. [Troubleshooting](#troubleshooting)
11. [Maintenance Tasks](#maintenance-tasks)

---

## Deployment Overview

### System Requirements

#### Minimum (< 1,000 flows/sec)
| Resource | Requirement |
|----------|-------------|
| CPU | 2 cores |
| Memory | 4 GB |
| Disk | 50 GB SSD |
| Network | 100 Mbps |

#### Recommended (1,000 - 10,000 flows/sec)
| Resource | Requirement |
|----------|-------------|
| CPU | 4 cores |
| Memory | 8 GB |
| Disk | 200 GB SSD |
| Network | 1 Gbps |

#### High Volume (> 10,000 flows/sec)
| Resource | Requirement |
|----------|-------------|
| CPU | 8+ cores |
| Memory | 16+ GB |
| Disk | 500+ GB NVMe SSD |
| Network | 10 Gbps |

### Architecture Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Load Balancer                             │
│                      (nginx/traefik)                            │
└─────────────────────────┬───────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   Frontend    │ │   API (x N)   │ │   Ingestion   │
│   (React)     │ │   (FastAPI)   │ │   (UDP)       │
│   Port 3000   │ │   Port 8000   │ │   2055/6343   │
└───────────────┘ └───────┬───────┘ └───────┬───────┘
                          │                 │
                          ▼                 ▼
                  ┌───────────────────────────────┐
                  │         PostgreSQL            │
                  │         (Primary)             │
                  │         Port 5432             │
                  └───────────────────────────────┘
```

### Service Dependencies

| Service | Depends On | Purpose |
|---------|------------|---------|
| postgres | - | Primary data store |
| migrations | postgres | Database schema setup |
| api | migrations | REST API and WebSocket |
| ingestion | migrations | Flow packet reception |
| enrichment | migrations | DNS/GeoIP enrichment |
| resolution | migrations | Dependency detection |
| classification | migrations | Asset auto-classification |
| frontend | api | Web user interface |

---

## Docker Compose Deployment

### Quick Start

```bash
# Clone repository
git clone https://github.com/flowlens/flowlens.git
cd flowlens

# Start all services
docker compose up -d --build

# Verify services are running
docker compose ps

# View logs
docker compose logs -f
```

### Using the System Settings UI

FlowLens includes a web-based configuration interface:

1. Access the UI at `http://localhost:3000`
2. Navigate to **System Settings**
3. Configure services as needed
4. Click **Export docker-compose.yml** to download your configuration
5. Replace your `docker-compose.yml` and restart:

```bash
docker compose down
# Replace docker-compose.yml with exported version
docker compose up -d --build
```

### Environment File Setup

Create a `.env` file in the project root:

```env
# =============================================================================
# Database Configuration
# =============================================================================
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=flowlens
POSTGRES_PASSWORD=your-secure-password-here
POSTGRES_DATABASE=flowlens
POSTGRES_POOL_SIZE=20
POSTGRES_MAX_OVERFLOW=10

# =============================================================================
# API Configuration
# =============================================================================
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
API_CORS_ORIGINS=http://localhost:3000

# =============================================================================
# Authentication
# =============================================================================
AUTH_ENABLED=true
AUTH_SECRET_KEY=generate-a-64-char-random-string-here
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7

# =============================================================================
# Ingestion
# =============================================================================
INGESTION_BIND_ADDRESS=0.0.0.0
INGESTION_NETFLOW_PORT=2055
INGESTION_SFLOW_PORT=6343
INGESTION_BATCH_SIZE=1000
INGESTION_BATCH_TIMEOUT_MS=1000
INGESTION_QUEUE_MAX_SIZE=100000
INGESTION_SAMPLE_THRESHOLD=50000
INGESTION_DROP_THRESHOLD=80000
INGESTION_SAMPLE_RATE=10

# =============================================================================
# Enrichment
# =============================================================================
ENRICHMENT_WORKER_COUNT=4
ENRICHMENT_BATCH_SIZE=500
ENRICHMENT_POLL_INTERVAL_MS=100
ENRICHMENT_DNS_TIMEOUT=2.0
ENRICHMENT_DNS_CACHE_TTL=3600
ENRICHMENT_DNS_CACHE_SIZE=10000

# =============================================================================
# Resolution
# =============================================================================
RESOLUTION_WORKER_COUNT=1
RESOLUTION_WINDOW_SIZE_MINUTES=5
RESOLUTION_BATCH_SIZE=1000
RESOLUTION_POLL_INTERVAL_MS=500
RESOLUTION_STALE_THRESHOLD_HOURS=24
RESOLUTION_EXCLUDE_EXTERNAL_IPS=false
RESOLUTION_EXCLUDE_EXTERNAL_SOURCES=false
RESOLUTION_EXCLUDE_EXTERNAL_TARGETS=true

# =============================================================================
# Classification
# =============================================================================
CLASSIFICATION_WORKER_COUNT=1
CLASSIFICATION_POLL_INTERVAL_MS=30000
CLASSIFICATION_BATCH_SIZE=100
CLASSIFICATION_MIN_OBSERVATION_HOURS=24
CLASSIFICATION_MIN_FLOWS_REQUIRED=100
CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD=0.70
CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD=0.85
CLASSIFICATION_RECLASSIFY_INTERVAL_HOURS=24

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Generating a Secure Secret Key

```bash
# Generate a secure 64-character secret key
openssl rand -hex 32
```

### Docker Compose Commands Reference

```bash
# Start services
docker compose up -d --build

# Stop services
docker compose down

# Stop and remove volumes (WARNING: deletes data)
docker compose down -v

# View logs for all services
docker compose logs -f

# View logs for specific service
docker compose logs -f api

# Restart a specific service
docker compose restart api

# Scale API workers (if configured for scaling)
docker compose up -d --scale api=3

# Execute command in container
docker compose exec api alembic upgrade head

# Check service health
docker compose ps
```

### Production Docker Compose Configuration

For production deployments, create a `docker-compose.prod.yml`:

```yaml
# Shared environment variable definitions
x-db-env: &db-env
  POSTGRES_HOST: postgres
  POSTGRES_PORT: 5432
  POSTGRES_USER: flowlens
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  POSTGRES_DATABASE: flowlens

x-logging-env: &logging-env
  LOG_LEVEL: INFO
  LOG_FORMAT: json

services:
  postgres:
    image: postgres:15-alpine
    container_name: flowlens-postgres
    environment:
      POSTGRES_USER: flowlens
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: flowlens
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"  # Only expose locally
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U flowlens"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  migrations:
    build:
      context: .
      target: production
    container_name: flowlens-migrations
    command: ["alembic", "upgrade", "head"]
    environment:
      <<: *db-env
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build:
      context: .
      target: production
    container_name: flowlens-api
    command: ["python", "-m", "flowlens.api.main"]
    environment:
      ENVIRONMENT: production
      DEBUG: "false"
      <<: *db-env
      API_HOST: "0.0.0.0"
      API_PORT: "8000"
      API_WORKERS: "4"
      API_CORS_ORIGINS: "https://flowlens.example.com"
      AUTH_ENABLED: "true"
      AUTH_SECRET_KEY: ${AUTH_SECRET_KEY}
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    ports:
      - "127.0.0.1:8000:8000"  # Only expose locally, use reverse proxy
    depends_on:
      migrations:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/admin/health/live')"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  ingestion:
    build:
      context: .
      target: production
    container_name: flowlens-ingestion
    command: ["python", "-m", "flowlens.ingestion.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      INGESTION_BIND_ADDRESS: "0.0.0.0"
      INGESTION_NETFLOW_PORT: "2055"
      INGESTION_SFLOW_PORT: "6343"
      INGESTION_BATCH_SIZE: "2000"
      INGESTION_BATCH_TIMEOUT_MS: "500"
      INGESTION_QUEUE_MAX_SIZE: "200000"
      INGESTION_SAMPLE_THRESHOLD: "100000"
      INGESTION_DROP_THRESHOLD: "150000"
      INGESTION_SAMPLE_RATE: "10"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    ports:
      - "2055:2055/udp"
      - "6343:6343/udp"
    depends_on:
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  enrichment:
    build:
      context: .
      target: production
    container_name: flowlens-enrichment
    command: ["python", "-m", "flowlens.enrichment.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      ENRICHMENT_WORKER_COUNT: "4"
      ENRICHMENT_BATCH_SIZE: "1000"
      ENRICHMENT_POLL_INTERVAL_MS: "50"
      ENRICHMENT_DNS_TIMEOUT: "1.0"
      ENRICHMENT_DNS_CACHE_TTL: "3600"
      ENRICHMENT_DNS_CACHE_SIZE: "50000"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    depends_on:
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  resolution:
    build:
      context: .
      target: production
    container_name: flowlens-resolution
    command: ["python", "-m", "flowlens.resolution.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      RESOLUTION_WORKER_COUNT: "2"
      RESOLUTION_WINDOW_SIZE_MINUTES: "5"
      RESOLUTION_BATCH_SIZE: "2000"
      RESOLUTION_POLL_INTERVAL_MS: "250"
      RESOLUTION_STALE_THRESHOLD_HOURS: "48"
      RESOLUTION_EXCLUDE_EXTERNAL_IPS: "false"
      RESOLUTION_EXCLUDE_EXTERNAL_SOURCES: "false"
      RESOLUTION_EXCLUDE_EXTERNAL_TARGETS: "true"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    depends_on:
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  classification:
    build:
      context: .
      target: production
    container_name: flowlens-classification
    command: ["python", "-m", "flowlens.classification.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      CLASSIFICATION_WORKER_COUNT: "1"
      CLASSIFICATION_POLL_INTERVAL_MS: "60000"
      CLASSIFICATION_BATCH_SIZE: "200"
      CLASSIFICATION_MIN_OBSERVATION_HOURS: "24"
      CLASSIFICATION_MIN_FLOWS_REQUIRED: "100"
      CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD: "0.75"
      CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD: "0.85"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    depends_on:
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  frontend:
    build:
      context: ./frontend
      target: production
    container_name: flowlens-frontend
    ports:
      - "127.0.0.1:3000:80"  # Only expose locally, use reverse proxy
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:

networks:
  default:
    name: flowlens-network
```

### Reverse Proxy Configuration (nginx)

Create `/etc/nginx/sites-available/flowlens`:

```nginx
upstream flowlens_api {
    server 127.0.0.1:8000;
}

upstream flowlens_frontend {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name flowlens.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name flowlens.example.com;

    ssl_certificate /etc/letsencrypt/live/flowlens.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/flowlens.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Frontend
    location / {
        proxy_pass http://flowlens_frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API
    location /api/ {
        proxy_pass http://flowlens_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /api/v1/ws {
        proxy_pass http://flowlens_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # Health checks (no auth required)
    location /admin/health/ {
        proxy_pass http://flowlens_api;
        proxy_set_header Host $host;
    }
}
```

---

## Manual Deployment

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Node.js 18+ (for frontend)
- Redis (optional, for caching)

### Backend Installation

```bash
# Create virtual environment
python3 -m venv /opt/flowlens/venv
source /opt/flowlens/venv/bin/activate

# Install FlowLens
pip install -e ".[production]"

# Or install from wheel
pip install flowlens-*.whl
```

### Database Setup

```bash
# Create PostgreSQL user and database
sudo -u postgres psql << EOF
CREATE USER flowlens WITH PASSWORD 'your-secure-password';
CREATE DATABASE flowlens OWNER flowlens;
GRANT ALL PRIVILEGES ON DATABASE flowlens TO flowlens;
EOF

# Run migrations
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=flowlens
export POSTGRES_PASSWORD=your-secure-password
export POSTGRES_DATABASE=flowlens

alembic upgrade head
```

### Systemd Service Files

#### API Service (`/etc/systemd/system/flowlens-api.service`)

```ini
[Unit]
Description=FlowLens API Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=flowlens
Group=flowlens
WorkingDirectory=/opt/flowlens
Environment="PATH=/opt/flowlens/venv/bin"
EnvironmentFile=/opt/flowlens/.env
ExecStart=/opt/flowlens/venv/bin/python -m flowlens.api.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Ingestion Service (`/etc/systemd/system/flowlens-ingestion.service`)

```ini
[Unit]
Description=FlowLens Ingestion Service
After=network.target postgresql.service flowlens-api.service
Requires=postgresql.service

[Service]
Type=simple
User=flowlens
Group=flowlens
WorkingDirectory=/opt/flowlens
Environment="PATH=/opt/flowlens/venv/bin"
EnvironmentFile=/opt/flowlens/.env
ExecStart=/opt/flowlens/venv/bin/python -m flowlens.ingestion.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Enrichment Service (`/etc/systemd/system/flowlens-enrichment.service`)

```ini
[Unit]
Description=FlowLens Enrichment Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=flowlens
Group=flowlens
WorkingDirectory=/opt/flowlens
Environment="PATH=/opt/flowlens/venv/bin"
EnvironmentFile=/opt/flowlens/.env
ExecStart=/opt/flowlens/venv/bin/python -m flowlens.enrichment.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Resolution Service (`/etc/systemd/system/flowlens-resolution.service`)

```ini
[Unit]
Description=FlowLens Resolution Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=flowlens
Group=flowlens
WorkingDirectory=/opt/flowlens
Environment="PATH=/opt/flowlens/venv/bin"
EnvironmentFile=/opt/flowlens/.env
ExecStart=/opt/flowlens/venv/bin/python -m flowlens.resolution.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Classification Service (`/etc/systemd/system/flowlens-classification.service`)

```ini
[Unit]
Description=FlowLens Classification Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=flowlens
Group=flowlens
WorkingDirectory=/opt/flowlens
Environment="PATH=/opt/flowlens/venv/bin"
EnvironmentFile=/opt/flowlens/.env
ExecStart=/opt/flowlens/venv/bin/python -m flowlens.classification.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable and Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable flowlens-api flowlens-ingestion flowlens-enrichment flowlens-resolution flowlens-classification
sudo systemctl start flowlens-api flowlens-ingestion flowlens-enrichment flowlens-resolution flowlens-classification
```

### Frontend Deployment

```bash
cd frontend
npm install
npm run build

# Serve with nginx
sudo cp -r dist/* /var/www/flowlens/
```

---

## Configuration Reference

### Database Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `POSTGRES_HOST` | localhost | postgres | Database hostname |
| `POSTGRES_PORT` | 5432 | 5432 | Database port |
| `POSTGRES_USER` | flowlens | flowlens | Database user |
| `POSTGRES_PASSWORD` | flowlens | *strong password* | Database password |
| `POSTGRES_DATABASE` | flowlens | flowlens | Database name |
| `POSTGRES_POOL_SIZE` | 20 | 20-50 | Connection pool size |
| `POSTGRES_MAX_OVERFLOW` | 10 | 10-20 | Extra connections allowed |
| `POSTGRES_POOL_TIMEOUT` | 30 | 30 | Connection wait timeout (sec) |
| `POSTGRES_POOL_RECYCLE` | 1800 | 1800 | Connection recycle time (sec) |
| `POSTGRES_ECHO` | false | false | Log all SQL (debug only) |

**Recommendations:**
- Use `POSTGRES_POOL_SIZE` = 2-3x your API worker count
- Enable `POSTGRES_ECHO` only for debugging, never in production
- Use strong passwords with special characters (they are properly escaped)

### API Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `API_HOST` | 0.0.0.0 | 0.0.0.0 | Listen address |
| `API_PORT` | 8000 | 8000 | Listen port |
| `API_WORKERS` | 4 | 4-8 | Uvicorn worker count |
| `API_CORS_ORIGINS` | * | your-domain.com | Allowed CORS origins |
| `API_RATE_LIMIT_REQUESTS` | 100 | 100-500 | Requests per window |
| `API_RATE_LIMIT_WINDOW_SECONDS` | 60 | 60 | Rate limit window |
| `API_DEFAULT_PAGE_SIZE` | 50 | 50 | Default pagination size |
| `API_MAX_PAGE_SIZE` | 1000 | 1000 | Maximum pagination size |

**Recommendations:**
- Set `API_WORKERS` to number of CPU cores
- Always set specific `API_CORS_ORIGINS` in production
- Adjust rate limits based on expected client count

### Authentication Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `AUTH_ENABLED` | true | true | Enable authentication |
| `AUTH_SECRET_KEY` | change-me | *64-char random* | JWT signing secret |
| `AUTH_ALGORITHM` | HS256 | HS256 | JWT algorithm |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | 15-60 | Access token lifetime |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | 7 | 7-30 | Refresh token lifetime |

**Recommendations:**
- **Always** change `AUTH_SECRET_KEY` in production
- Generate with: `openssl rand -hex 32`
- Shorter token expiry = more secure but more re-authentication

### Ingestion Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `INGESTION_BIND_ADDRESS` | 0.0.0.0 | 0.0.0.0 | UDP listen address |
| `INGESTION_NETFLOW_PORT` | 2055 | 2055 | NetFlow/IPFIX port |
| `INGESTION_SFLOW_PORT` | 6343 | 6343 | sFlow port |
| `INGESTION_BATCH_SIZE` | 1000 | 2000-5000 | Flows per DB batch |
| `INGESTION_BATCH_TIMEOUT_MS` | 1000 | 500 | Max batch wait time |
| `INGESTION_QUEUE_MAX_SIZE` | 100000 | 200000 | Max queue before backpressure |
| `INGESTION_SAMPLE_THRESHOLD` | 50000 | 100000 | Queue size to start sampling |
| `INGESTION_DROP_THRESHOLD` | 80000 | 150000 | Queue size to start dropping |
| `INGESTION_SAMPLE_RATE` | 10 | 10 | Keep 1 in N when sampling |

**Recommendations:**
- Increase `INGESTION_BATCH_SIZE` for higher throughput
- Lower `INGESTION_BATCH_TIMEOUT_MS` for lower latency
- Set thresholds based on memory: each queued flow ~500 bytes

### Enrichment Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `ENRICHMENT_WORKER_COUNT` | 4 | 4-8 | Parallel enrichment workers |
| `ENRICHMENT_BATCH_SIZE` | 500 | 1000 | Flows per enrichment batch |
| `ENRICHMENT_POLL_INTERVAL_MS` | 100 | 50 | Queue poll interval |
| `ENRICHMENT_DNS_TIMEOUT` | 2.0 | 1.0 | DNS lookup timeout (sec) |
| `ENRICHMENT_DNS_CACHE_TTL` | 3600 | 3600 | DNS cache lifetime (sec) |
| `ENRICHMENT_DNS_CACHE_SIZE` | 10000 | 50000 | Max DNS cache entries |
| `ENRICHMENT_DNS_SERVERS` | (system) | 8.8.8.8,1.1.1.1 | Custom DNS servers |
| `ENRICHMENT_GEOIP_DATABASE_PATH` | - | /data/GeoLite2-City.mmdb | MaxMind database path |

**Recommendations:**
- Increase `ENRICHMENT_DNS_CACHE_SIZE` for large networks
- Use local DNS servers for better performance
- Download GeoIP database from MaxMind for location data

### Resolution Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `RESOLUTION_WORKER_COUNT` | 1 | 2 | Resolution worker count |
| `RESOLUTION_WINDOW_SIZE_MINUTES` | 5 | 5 | Aggregation window |
| `RESOLUTION_BATCH_SIZE` | 1000 | 2000 | Aggregates per batch |
| `RESOLUTION_POLL_INTERVAL_MS` | 500 | 250 | Queue poll interval |
| `RESOLUTION_STALE_THRESHOLD_HOURS` | 24 | 48-72 | Hours before stale |
| `RESOLUTION_EXCLUDE_EXTERNAL_IPS` | false | false | Exclude all external IPs |
| `RESOLUTION_EXCLUDE_EXTERNAL_SOURCES` | false | false | Exclude external sources |
| `RESOLUTION_EXCLUDE_EXTERNAL_TARGETS` | false | true | Exclude external targets |

**Recommendations:**
- Set `RESOLUTION_EXCLUDE_EXTERNAL_TARGETS=true` to focus on internal dependencies
- Increase `RESOLUTION_STALE_THRESHOLD_HOURS` for intermittent connections
- Keep `RESOLUTION_WINDOW_SIZE_MINUTES=5` for balance of granularity and performance

### Classification Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `CLASSIFICATION_WORKER_COUNT` | 1 | 1-2 | Classification workers |
| `CLASSIFICATION_POLL_INTERVAL_MS` | 30000 | 60000 | Classification interval |
| `CLASSIFICATION_BATCH_SIZE` | 100 | 200 | Assets per batch |
| `CLASSIFICATION_MIN_OBSERVATION_HOURS` | 24 | 24-48 | Min observation time |
| `CLASSIFICATION_MIN_FLOWS_REQUIRED` | 100 | 100-500 | Min flows before classifying |
| `CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD` | 0.70 | 0.75 | Auto-update threshold |
| `CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD` | 0.85 | 0.85 | High confidence threshold |
| `CLASSIFICATION_RECLASSIFY_INTERVAL_HOURS` | 24 | 24-168 | Reclassification interval |

**Recommendations:**
- Higher `MIN_OBSERVATION_HOURS` = more accurate but slower classification
- Higher `AUTO_UPDATE_CONFIDENCE_THRESHOLD` = fewer false positives
- Increase `POLL_INTERVAL_MS` to reduce CPU usage

### Logging Settings

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `LOG_LEVEL` | INFO | INFO | Log level |
| `LOG_FORMAT` | json | json | Log format (json/console) |
| `LOG_INCLUDE_TIMESTAMP` | true | true | Include timestamps |
| `LOG_INCLUDE_CALLER` | true | false | Include caller info |

**Recommendations:**
- Always use `LOG_FORMAT=json` in production for log aggregation
- Set `LOG_LEVEL=WARNING` to reduce log volume if needed
- Disable `LOG_INCLUDE_CALLER` in production to reduce log size

---

## Scaling Guidelines

### Vertical Scaling

| Flow Rate | API Workers | Enrichment Workers | Resolution Workers | Pool Size |
|-----------|-------------|-------------------|-------------------|-----------|
| < 1K/sec | 2 | 2 | 1 | 10 |
| 1K-5K/sec | 4 | 4 | 1 | 20 |
| 5K-10K/sec | 4 | 8 | 2 | 30 |
| > 10K/sec | 8 | 8 | 4 | 50 |

### Horizontal Scaling

For high-availability and horizontal scaling:

1. **Database**: Use PostgreSQL streaming replication or managed PostgreSQL
2. **API**: Run multiple instances behind a load balancer
3. **Ingestion**: Single instance (UDP is stateless, but requires single collector)
4. **Background Services**: Single instance each (uses database for coordination)

### High-Availability Architecture

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │ (HAProxy/nginx) │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
   ┌───────────┐       ┌───────────┐       ┌───────────┐
   │  API #1   │       │  API #2   │       │  API #3   │
   └─────┬─────┘       └─────┬─────┘       └─────┬─────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (Primary)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (Replica)     │
                    └─────────────────┘
```

---

## Scaling with Redis and Kafka

FlowLens supports optional Redis and Kafka integration for high-volume deployments. Use this section to determine when and how to enable these components.

### When to Enable Redis

| Scenario | Recommendation |
|----------|----------------|
| < 5K flows/sec | Not needed - PostgreSQL handles load |
| 5K-20K flows/sec | **Recommended** - Redis caching reduces DB load |
| > 20K flows/sec | **Required** - Essential for performance |
| Multiple API instances | **Required** - Shared cache across instances |
| Real-time dashboards | **Recommended** - Faster response times |

### When to Enable Kafka

| Scenario | Recommendation |
|----------|----------------|
| < 10K flows/sec | Not needed - Direct DB writes sufficient |
| 10K-50K flows/sec | **Recommended** - Buffers traffic spikes |
| > 50K flows/sec | **Required** - Essential for durability |
| Multiple ingestion collectors | **Required** - Centralized message bus |
| Guaranteed delivery | **Required** - Kafka provides durability |
| Data reprocessing needs | **Required** - Kafka allows replay |

### Architecture with Redis and Kafka

```
                         ┌─────────────────┐
                         │  Network Flows  │
                         │  (NetFlow/sFlow)│
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │   Ingestion     │
                         │   (Collector)   │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │     Kafka       │
                         │   (Optional)    │
                         │  flows topic    │
                         └────────┬────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Enrichment    │      │   Resolution    │      │ Classification  │
│    Workers      │      │    Workers      │      │    Workers      │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                         ┌────────▼────────┐
                         │   PostgreSQL    │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │     Redis       │
                         │   (Optional)    │
                         │  Cache Layer    │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │   API Servers   │
                         └─────────────────┘
```

### Redis Configuration

#### Docker Compose with Redis

Add Redis to your `docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: flowlens-redis
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 768M

  # Update API service to use Redis
  api:
    # ... existing config ...
    environment:
      # ... existing env vars ...
      REDIS_ENABLED: "true"
      REDIS_HOST: redis
      REDIS_PORT: "6379"
      REDIS_DATABASE: "0"
      REDIS_PASSWORD: ""
      REDIS_CACHE_TTL: "300"
      REDIS_CACHE_PREFIX: "flowlens:"
    depends_on:
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully

volumes:
  redis_data:
```

#### Redis Environment Variables

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `REDIS_ENABLED` | false | true | Enable Redis caching |
| `REDIS_HOST` | localhost | redis | Redis hostname |
| `REDIS_PORT` | 6379 | 6379 | Redis port |
| `REDIS_DATABASE` | 0 | 0 | Redis database number |
| `REDIS_PASSWORD` | (none) | *strong password* | Redis password (optional) |
| `REDIS_CACHE_TTL` | 300 | 300-600 | Default cache TTL (seconds) |
| `REDIS_CACHE_PREFIX` | flowlens: | flowlens: | Cache key prefix |
| `REDIS_MAX_CONNECTIONS` | 10 | 20-50 | Connection pool size |
| `REDIS_SOCKET_TIMEOUT` | 5 | 5 | Socket timeout (seconds) |
| `REDIS_SSL` | false | true (if remote) | Enable SSL/TLS |

#### What Redis Caches

| Cache Type | TTL | Purpose |
|------------|-----|---------|
| Asset lookups | 5 min | Reduces DB queries for asset data |
| Topology data | 5 min | Caches dependency graph |
| Classification results | 10 min | Caches asset classifications |
| Aggregated metrics | 1 min | Dashboard statistics |
| DNS resolution cache | 1 hour | Reduces external DNS lookups |
| Session data | 30 min | User session storage (if enabled) |

#### Redis Memory Sizing

| Flow Rate | Assets | Recommended Memory |
|-----------|--------|-------------------|
| < 10K/sec | < 1,000 | 256 MB |
| 10K-50K/sec | 1,000-10,000 | 512 MB |
| 50K-100K/sec | 10,000-50,000 | 1 GB |
| > 100K/sec | > 50,000 | 2+ GB |

#### Redis High Availability

For production, use Redis Sentinel or Redis Cluster:

```yaml
services:
  redis-master:
    image: redis:7-alpine
    container_name: flowlens-redis-master
    command: redis-server --appendonly yes
    volumes:
      - redis_master_data:/data

  redis-replica:
    image: redis:7-alpine
    container_name: flowlens-redis-replica
    command: redis-server --replicaof redis-master 6379
    depends_on:
      - redis-master

  redis-sentinel:
    image: redis:7-alpine
    container_name: flowlens-redis-sentinel
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf
    depends_on:
      - redis-master
      - redis-replica
```

### Kafka Configuration

#### Docker Compose with Kafka

Add Kafka to your `docker-compose.yml`:

```yaml
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: flowlens-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - zookeeper_data:/var/lib/zookeeper/data
      - zookeeper_log:/var/lib/zookeeper/log
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "2181"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: flowlens-kafka
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
      KAFKA_LOG_RETENTION_HOURS: 24
      KAFKA_LOG_RETENTION_BYTES: 10737418240  # 10GB
    volumes:
      - kafka_data:/var/lib/kafka/data
    ports:
      - "127.0.0.1:9092:9092"
    depends_on:
      zookeeper:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions", "--bootstrap-server", "localhost:9092"]
      interval: 10s
      timeout: 10s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  # Update ingestion service to publish to Kafka
  ingestion:
    # ... existing config ...
    environment:
      # ... existing env vars ...
      KAFKA_ENABLED: "true"
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC_FLOWS: flowlens-flows
      KAFKA_TOPIC_PARTITIONS: "6"
      KAFKA_PRODUCER_BATCH_SIZE: "16384"
      KAFKA_PRODUCER_LINGER_MS: "10"
    depends_on:
      kafka:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully

  # Update enrichment to consume from Kafka
  enrichment:
    # ... existing config ...
    environment:
      # ... existing env vars ...
      KAFKA_ENABLED: "true"
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC_FLOWS: flowlens-flows
      KAFKA_CONSUMER_GROUP: flowlens-enrichment
      KAFKA_AUTO_OFFSET_RESET: earliest
    depends_on:
      kafka:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully

volumes:
  zookeeper_data:
  zookeeper_log:
  kafka_data:
```

#### Kafka Environment Variables

| Variable | Default | Recommended (Prod) | Description |
|----------|---------|-------------------|-------------|
| `KAFKA_ENABLED` | false | true | Enable Kafka integration |
| `KAFKA_BOOTSTRAP_SERVERS` | localhost:9092 | kafka:29092 | Kafka broker addresses |
| `KAFKA_TOPIC_FLOWS` | flowlens-flows | flowlens-flows | Topic for flow records |
| `KAFKA_TOPIC_PARTITIONS` | 6 | 6-12 | Number of partitions |
| `KAFKA_CONSUMER_GROUP` | flowlens-enrichment | flowlens-enrichment | Consumer group ID |
| `KAFKA_AUTO_OFFSET_RESET` | earliest | earliest | Where to start reading |
| `KAFKA_PRODUCER_BATCH_SIZE` | 16384 | 32768 | Producer batch size (bytes) |
| `KAFKA_PRODUCER_LINGER_MS` | 10 | 5-20 | Producer linger time |
| `KAFKA_PRODUCER_ACKS` | 1 | 1 or all | Acknowledgment level |
| `KAFKA_SECURITY_PROTOCOL` | PLAINTEXT | SASL_SSL | Security protocol |
| `KAFKA_SASL_MECHANISM` | (none) | SCRAM-SHA-512 | SASL mechanism |
| `KAFKA_SASL_USERNAME` | (none) | *username* | SASL username |
| `KAFKA_SASL_PASSWORD` | (none) | *password* | SASL password |

#### Kafka Topic Configuration

Recommended topic settings for high-volume deployments:

```bash
# Create optimized flow topic
kafka-topics --create \
  --bootstrap-server kafka:29092 \
  --topic flowlens-flows \
  --partitions 12 \
  --replication-factor 3 \
  --config retention.ms=86400000 \
  --config retention.bytes=10737418240 \
  --config segment.bytes=1073741824 \
  --config cleanup.policy=delete \
  --config compression.type=lz4
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| `partitions` | 12 | Allows 12 parallel consumers |
| `replication-factor` | 3 | Fault tolerance (requires 3+ brokers) |
| `retention.ms` | 86400000 (24h) | Balance storage vs replay capability |
| `compression.type` | lz4 | Fast compression, good ratio |

#### Kafka Partition Sizing

| Flow Rate | Partitions | Consumer Instances |
|-----------|------------|-------------------|
| < 10K/sec | 3 | 1-3 |
| 10K-50K/sec | 6 | 3-6 |
| 50K-100K/sec | 12 | 6-12 |
| > 100K/sec | 24+ | 12-24 |

#### Kafka Cluster for Production

For production, deploy a multi-broker Kafka cluster:

```yaml
services:
  kafka-1:
    image: confluentinc/cp-kafka:7.5.0
    container_name: flowlens-kafka-1
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-1:29092
      KAFKA_DEFAULT_REPLICATION_FACTOR: 3
      KAFKA_MIN_INSYNC_REPLICAS: 2
    volumes:
      - kafka_1_data:/var/lib/kafka/data

  kafka-2:
    image: confluentinc/cp-kafka:7.5.0
    container_name: flowlens-kafka-2
    environment:
      KAFKA_BROKER_ID: 2
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-2:29092
      KAFKA_DEFAULT_REPLICATION_FACTOR: 3
      KAFKA_MIN_INSYNC_REPLICAS: 2
    volumes:
      - kafka_2_data:/var/lib/kafka/data

  kafka-3:
    image: confluentinc/cp-kafka:7.5.0
    container_name: flowlens-kafka-3
    environment:
      KAFKA_BROKER_ID: 3
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka-3:29092
      KAFKA_DEFAULT_REPLICATION_FACTOR: 3
      KAFKA_MIN_INSYNC_REPLICAS: 2
    volumes:
      - kafka_3_data:/var/lib/kafka/data
```

#### KRaft Mode (Zookeeper-less)

For Kafka 3.3+, you can use KRaft mode without Zookeeper:

```yaml
services:
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: flowlens-kafka
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:29092,CONTROLLER://0.0.0.0:29093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:29093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_LOG_RETENTION_HOURS: 24
      CLUSTER_ID: "MkU3OEVBNTcwNTJENDM2Qk"
    volumes:
      - kafka_data:/var/lib/kafka/data
    ports:
      - "127.0.0.1:9092:29092"
```

### Full High-Volume Stack

Complete docker-compose for Redis + Kafka deployment:

```yaml
# FlowLens High-Volume Configuration
# Suitable for 50K+ flows/sec

x-db-env: &db-env
  POSTGRES_HOST: postgres
  POSTGRES_PORT: 5432
  POSTGRES_USER: flowlens
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  POSTGRES_DATABASE: flowlens

x-redis-env: &redis-env
  REDIS_ENABLED: "true"
  REDIS_HOST: redis
  REDIS_PORT: "6379"
  REDIS_CACHE_TTL: "300"

x-kafka-env: &kafka-env
  KAFKA_ENABLED: "true"
  KAFKA_BOOTSTRAP_SERVERS: kafka:29092
  KAFKA_TOPIC_FLOWS: flowlens-flows

services:
  postgres:
    image: postgres:15-alpine
    container_name: flowlens-postgres
    environment:
      POSTGRES_USER: flowlens
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: flowlens
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U flowlens"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4G

  redis:
    image: redis:7-alpine
    container_name: flowlens-redis
    command: redis-server --appendonly yes --maxmemory 1gb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1280M

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: flowlens-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - zookeeper_data:/var/lib/zookeeper/data
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "2181"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: flowlens-kafka
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_LOG_RETENTION_HOURS: 24
      KAFKA_LOG_RETENTION_BYTES: 10737418240
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka_data:/var/lib/kafka/data
    ports:
      - "127.0.0.1:9092:9092"
    depends_on:
      zookeeper:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions", "--bootstrap-server", "localhost:29092"]
      interval: 10s
      timeout: 10s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  migrations:
    build:
      context: .
      target: production
    container_name: flowlens-migrations
    command: ["alembic", "upgrade", "head"]
    environment:
      <<: *db-env
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build:
      context: .
      target: production
    container_name: flowlens-api
    command: ["python", "-m", "flowlens.api.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      <<: *redis-env
      API_HOST: "0.0.0.0"
      API_PORT: "8000"
      API_WORKERS: "8"
      AUTH_ENABLED: "true"
      AUTH_SECRET_KEY: ${AUTH_SECRET_KEY}
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  ingestion:
    build:
      context: .
      target: production
    container_name: flowlens-ingestion
    command: ["python", "-m", "flowlens.ingestion.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      <<: *kafka-env
      INGESTION_BIND_ADDRESS: "0.0.0.0"
      INGESTION_NETFLOW_PORT: "2055"
      INGESTION_SFLOW_PORT: "6343"
      INGESTION_BATCH_SIZE: "5000"
      INGESTION_BATCH_TIMEOUT_MS: "250"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    ports:
      - "2055:2055/udp"
      - "6343:6343/udp"
    depends_on:
      kafka:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped

  enrichment:
    build:
      context: .
      target: production
    container_name: flowlens-enrichment
    command: ["python", "-m", "flowlens.enrichment.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      <<: *redis-env
      <<: *kafka-env
      KAFKA_CONSUMER_GROUP: flowlens-enrichment
      ENRICHMENT_WORKER_COUNT: "8"
      ENRICHMENT_BATCH_SIZE: "2000"
      ENRICHMENT_POLL_INTERVAL_MS: "25"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    depends_on:
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G

  resolution:
    build:
      context: .
      target: production
    container_name: flowlens-resolution
    command: ["python", "-m", "flowlens.resolution.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      <<: *redis-env
      RESOLUTION_WORKER_COUNT: "4"
      RESOLUTION_BATCH_SIZE: "5000"
      RESOLUTION_POLL_INTERVAL_MS: "100"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    depends_on:
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  classification:
    build:
      context: .
      target: production
    container_name: flowlens-classification
    command: ["python", "-m", "flowlens.classification.main"]
    environment:
      ENVIRONMENT: production
      <<: *db-env
      <<: *redis-env
      CLASSIFICATION_WORKER_COUNT: "2"
      CLASSIFICATION_POLL_INTERVAL_MS: "30000"
      LOG_LEVEL: INFO
      LOG_FORMAT: json
    depends_on:
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      target: production
    container_name: flowlens-frontend
    ports:
      - "127.0.0.1:3000:80"
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  zookeeper_data:
  kafka_data:

networks:
  default:
    name: flowlens-network
```

### Monitoring Redis and Kafka

#### Redis Metrics

```bash
# Check Redis info
docker compose exec redis redis-cli info

# Monitor commands in real-time
docker compose exec redis redis-cli monitor

# Check memory usage
docker compose exec redis redis-cli info memory

# Check cache hit rate
docker compose exec redis redis-cli info stats | grep keyspace
```

Key Redis metrics to monitor:

| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| `used_memory` | > 80% of max | Memory approaching limit |
| `connected_clients` | > 90% of max | Connection pool exhaustion |
| `keyspace_hits / misses` | < 80% hit rate | Cache not effective |
| `evicted_keys` | > 0 sustained | Memory pressure |

#### Kafka Metrics

```bash
# Check consumer lag
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:29092 \
  --group flowlens-enrichment \
  --describe

# Check topic size
docker compose exec kafka kafka-log-dirs \
  --bootstrap-server localhost:29092 \
  --describe

# List topics
docker compose exec kafka kafka-topics \
  --bootstrap-server localhost:29092 \
  --list
```

Key Kafka metrics to monitor:

| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| Consumer lag | > 100,000 | Processing falling behind |
| Under-replicated partitions | > 0 | Replication issues |
| Active controller count | != 1 | Cluster instability |
| Request queue size | > 100 | Broker overload |
| Log size | > 80% retention | Disk pressure |

---

## Monitoring and Health Checks

### Health Check Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /admin/health/live` | Liveness probe | `{"status": "ok"}` |
| `GET /admin/health/ready` | Readiness probe | `{"status": "ok", "checks": {...}}` |
| `GET /admin/metrics` | Prometheus metrics | Prometheus format |

### Prometheus Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'flowlens'
    static_configs:
      - targets: ['flowlens-api:8000']
    metrics_path: '/admin/metrics'
    scrape_interval: 15s
```

### Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `flowlens_flows_received_total` | Total flows received | Rate drop > 50% |
| `flowlens_flows_processed_total` | Total flows processed | Rate drop > 50% |
| `flowlens_queue_size` | Current queue size | > 80% of max |
| `flowlens_db_connections_active` | Active DB connections | > 80% of pool |
| `flowlens_api_request_duration_seconds` | API latency | p99 > 1s |
| `flowlens_enrichment_duration_seconds` | Enrichment latency | p99 > 5s |

### Log Aggregation

FlowLens outputs structured JSON logs. Example log entry:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "logger": "flowlens.ingestion.server",
  "message": "Received flow batch",
  "flow_count": 1000,
  "source_ip": "10.0.0.1",
  "protocol": "netflow_v9"
}
```

Configure your log aggregator (Loki, Elasticsearch, Splunk) to parse JSON logs.

---

## Backup and Recovery

### Database Backup

#### Full Backup

```bash
# Create backup
pg_dump -h localhost -U flowlens -Fc flowlens > flowlens_$(date +%Y%m%d_%H%M%S).dump

# Compress
gzip flowlens_*.dump
```

#### Automated Backup Script

Create `/opt/flowlens/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR=/var/backups/flowlens
RETENTION_DAYS=30

# Create backup
pg_dump -h localhost -U flowlens -Fc flowlens > $BACKUP_DIR/flowlens_$(date +%Y%m%d_%H%M%S).dump

# Compress
gzip $BACKUP_DIR/flowlens_*.dump 2>/dev/null

# Remove old backups
find $BACKUP_DIR -name "*.dump.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $(ls -lh $BACKUP_DIR/*.dump.gz | tail -1)"
```

Add to crontab:
```bash
0 2 * * * /opt/flowlens/backup.sh >> /var/log/flowlens-backup.log 2>&1
```

### Database Restore

```bash
# Stop services
docker compose stop api ingestion enrichment resolution classification

# Restore
gunzip -c flowlens_20240115_020000.dump.gz | pg_restore -h localhost -U flowlens -d flowlens -c

# Restart services
docker compose start api ingestion enrichment resolution classification
```

### Data Retention

FlowLens automatically manages data retention:

| Data Type | Default Retention | Configuration |
|-----------|-------------------|---------------|
| Raw flow records | 7 days | Partitioned, auto-dropped |
| 5-minute aggregates | 90 days | Partitioned, auto-dropped |
| Hourly aggregates | 2 years | Partitioned, auto-dropped |
| Daily aggregates | 2 years | Partitioned, auto-dropped |
| Assets | Indefinite | Manual cleanup |
| Dependencies | Indefinite | Soft-delete with valid_to |

---

## Security Considerations

### Network Security

1. **Firewall Rules**
   ```bash
   # Allow flow ingestion from network devices only
   ufw allow from 10.0.0.0/8 to any port 2055 proto udp
   ufw allow from 10.0.0.0/8 to any port 6343 proto udp

   # Allow API access from internal network
   ufw allow from 10.0.0.0/8 to any port 8000

   # Allow HTTPS from anywhere
   ufw allow 443
   ```

2. **Bind to Localhost**
   - Bind API and frontend to `127.0.0.1` in production
   - Use reverse proxy (nginx) for external access

### Authentication

1. **Strong Secret Key**
   ```bash
   # Generate 64-character secret
   AUTH_SECRET_KEY=$(openssl rand -hex 32)
   ```

2. **Token Expiration**
   - Set `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=15` for sensitive environments
   - Use refresh tokens for session continuity

3. **CORS Configuration**
   - Never use `API_CORS_ORIGINS=*` in production
   - Specify exact allowed origins

### Database Security

1. **Strong Passwords**
   - Use passwords with special characters (properly escaped in docker-compose)
   - Rotate passwords periodically

2. **Network Isolation**
   - Keep PostgreSQL on internal network only
   - Use SSL/TLS for database connections in production

3. **Least Privilege**
   - FlowLens only needs access to its own database
   - Don't use PostgreSQL superuser

### Container Security

1. **Run as Non-Root**
   - FlowLens containers run as non-root user by default

2. **Resource Limits**
   - Set memory and CPU limits in docker-compose
   - Prevents resource exhaustion attacks

3. **Image Updates**
   - Regularly rebuild images to get security updates
   - Use specific version tags, not `latest`

---

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check container logs
docker compose logs api

# Check if database is ready
docker compose exec postgres pg_isready -U flowlens

# Check migrations ran successfully
docker compose logs migrations
```

#### No Flows Being Received

```bash
# Verify UDP ports are listening
netstat -ulnp | grep -E "2055|6343"

# Check firewall
iptables -L -n | grep -E "2055|6343"

# Test with netcat
nc -u localhost 2055

# Check ingestion logs
docker compose logs -f ingestion
```

#### High Memory Usage

```bash
# Check container memory
docker stats

# Reduce queue sizes
INGESTION_QUEUE_MAX_SIZE=50000
INGESTION_SAMPLE_THRESHOLD=25000
INGESTION_DROP_THRESHOLD=40000
```

#### Slow API Responses

```bash
# Check database connections
docker compose exec postgres psql -U flowlens -c "SELECT count(*) FROM pg_stat_activity WHERE datname='flowlens';"

# Check slow queries
docker compose exec postgres psql -U flowlens -c "SELECT query, calls, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Increase pool size
POSTGRES_POOL_SIZE=30
```

#### Database Connection Errors

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check connection
docker compose exec api python -c "from flowlens.common.database import get_engine; print('OK')"

# Verify credentials
docker compose exec postgres psql -U flowlens -d flowlens -c "SELECT 1;"
```

### Log Analysis

```bash
# Search for errors
docker compose logs api 2>&1 | grep -i error

# Search for specific asset
docker compose logs resolution 2>&1 | grep "10.0.0.1"

# Count flows by protocol
docker compose logs ingestion 2>&1 | grep "protocol" | jq -r '.protocol' | sort | uniq -c
```

### Performance Tuning

#### PostgreSQL

Add to `postgresql.conf`:

```ini
# Memory
shared_buffers = 256MB
effective_cache_size = 768MB
work_mem = 16MB
maintenance_work_mem = 128MB

# Connections
max_connections = 100

# Write performance
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# Query planning
random_page_cost = 1.1  # For SSD
effective_io_concurrency = 200  # For SSD
```

#### Linux Kernel

Add to `/etc/sysctl.conf`:

```ini
# Increase UDP buffer sizes for flow ingestion
net.core.rmem_max = 134217728
net.core.rmem_default = 134217728

# Increase connection tracking for high flow rates
net.netfilter.nf_conntrack_max = 1048576
```

---

## Maintenance Tasks

### Regular Maintenance

| Task | Frequency | Command/Action |
|------|-----------|----------------|
| Database backup | Daily | `pg_dump` (automated) |
| Log rotation | Daily | Configure logrotate |
| Docker image updates | Weekly | `docker compose pull && docker compose up -d` |
| Database vacuum | Weekly | `VACUUM ANALYZE;` (automatic in PostgreSQL) |
| Check disk space | Daily | Monitor `/var/lib/docker` and PostgreSQL data |
| Review alerts | Daily | Check FlowLens alerts page |

### Updating FlowLens

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose down
docker compose up -d --build

# Migrations run automatically on startup
```

### Database Maintenance

```bash
# Analyze tables for query optimization
docker compose exec postgres psql -U flowlens -c "ANALYZE;"

# Reindex if needed
docker compose exec postgres psql -U flowlens -c "REINDEX DATABASE flowlens;"

# Check table sizes
docker compose exec postgres psql -U flowlens -c "
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;"
```

### Cleanup Tasks

```bash
# Remove old Docker images
docker image prune -a --filter "until=168h"

# Remove old Docker volumes (careful!)
docker volume prune

# Clean up Docker build cache
docker builder prune
```

---

## Support

- **Documentation**: [GitHub Wiki](https://github.com/flowlens/flowlens/wiki)
- **Issues**: [GitHub Issues](https://github.com/flowlens/flowlens/issues)
- **Discussions**: [GitHub Discussions](https://github.com/flowlens/flowlens/discussions)
