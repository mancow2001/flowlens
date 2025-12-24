# FlowLens Deployment Guide

This guide provides step-by-step instructions for deploying FlowLens in various environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (Docker Compose)](#quick-start-docker-compose)
3. [Development Setup](#development-setup)
4. [Production Deployment](#production-deployment)
5. [Kubernetes Deployment](#kubernetes-deployment)
6. [Configuration Reference](#configuration-reference)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **Docker** 20.10+ and **Docker Compose** v2.0+
- **Python** 3.11+ (for development)
- **Node.js** 20+ (for frontend development)
- **PostgreSQL** 15+ (if running without Docker)

### Hardware Requirements

| Deployment Size | CPU | RAM | Disk | Flows/sec |
|-----------------|-----|-----|------|-----------|
| Small (Dev)     | 2 cores | 4 GB | 20 GB | < 1k |
| Medium          | 4 cores | 8 GB | 100 GB | 1k - 10k |
| Large           | 8+ cores | 16+ GB | 500+ GB | > 10k |

---

## Quick Start (Docker Compose)

The fastest way to get FlowLens running.

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/flowlens.git
cd flowlens
```

### Step 2: Create Environment File

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
# Generate a secure secret key
AUTH_SECRET_KEY=$(openssl rand -hex 32)
echo "AUTH_SECRET_KEY=$AUTH_SECRET_KEY" >> .env
```

### Step 3: Start Services

```bash
# Start all services (PostgreSQL, API, Ingestion, Frontend)
docker compose up -d

# View logs
docker compose logs -f
```

### Step 4: Verify Deployment

```bash
# Check service health
docker compose ps

# Test API health
curl http://localhost:8000/admin/health/live

# Test metrics endpoint
curl http://localhost:8000/admin/metrics
```

### Step 5: Access the UI

Open your browser to: **http://localhost:3000**

### Service Endpoints

| Service | URL | Description |
|---------|-----|-------------|
| Frontend UI | http://localhost:3000 | Web interface |
| API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| NetFlow | udp://localhost:2055 | NetFlow v5/v9/IPFIX receiver |
| sFlow | udp://localhost:6343 | sFlow receiver |

---

## Development Setup

For local development with hot-reload.

### Step 1: Start Database Only

```bash
docker compose up -d postgres
```

### Step 2: Set Up Python Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### Step 3: Run Database Migrations

```bash
# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=flowlens
export POSTGRES_PASSWORD=flowlens
export POSTGRES_DATABASE=flowlens

# Run migrations
alembic upgrade head
```

### Step 4: Start Backend Services

```bash
# Terminal 1: API Service
python -m flowlens.api.main

# Terminal 2: Ingestion Service (optional)
python -m flowlens.ingestion.main
```

### Step 5: Start Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at **http://localhost:3000** with hot-reload.

---

## Production Deployment

### Option A: Docker Compose (Recommended for Small/Medium)

#### Step 1: Prepare Production Environment

```bash
# Create production directory
mkdir -p /opt/flowlens
cd /opt/flowlens

# Clone repository
git clone https://github.com/your-org/flowlens.git .

# Create production environment file
cp .env.example .env
```

#### Step 2: Configure Production Settings

Edit `.env`:

```bash
# Application
ENVIRONMENT=production
DEBUG=false

# Database - use strong password
POSTGRES_PASSWORD=<strong-random-password>

# Authentication - REQUIRED for production
AUTH_ENABLED=true
AUTH_SECRET_KEY=<generate-with-openssl-rand-hex-32>

# API
API_WORKERS=4
API_CORS_ORIGINS=https://your-domain.com

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

#### Step 3: Start Production Stack

```bash
# Build and start
docker compose -f docker-compose.yml up -d --build

# Verify all services are healthy
docker compose ps
```

#### Step 4: Set Up Reverse Proxy (Nginx)

Create `/etc/nginx/sites-available/flowlens`:

```nginx
server {
    listen 80;
    server_name flowlens.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name flowlens.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/flowlens.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/flowlens.your-domain.com/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /api/v1/ws {
        proxy_pass http://localhost:3000/api/v1/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/flowlens /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Step 5: Set Up SSL (Let's Encrypt)

```bash
sudo certbot --nginx -d flowlens.your-domain.com
```

### Option B: High-Scale Deployment (Kafka + Redis)

For deployments handling >10,000 flows/sec:

```bash
# Use the full docker-compose configuration
docker compose -f docker-compose.full.yml up -d --build
```

This adds:
- **Redis** for caching DNS lookups and session data
- **Kafka** for high-throughput flow ingestion
- Multiple replicas of processing services

---

## Kubernetes Deployment

### Step 1: Create Namespace

```bash
kubectl create namespace flowlens
```

### Step 2: Create Secrets

```bash
kubectl create secret generic flowlens-secrets \
  --namespace flowlens \
  --from-literal=postgres-password='<strong-password>' \
  --from-literal=auth-secret-key='<generate-with-openssl>'
```

### Step 3: Deploy PostgreSQL

```bash
# Using Helm (recommended)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install flowlens-db bitnami/postgresql \
  --namespace flowlens \
  --set auth.postgresPassword=<password> \
  --set auth.database=flowlens \
  --set primary.persistence.size=100Gi
```

### Step 4: Apply Kubernetes Manifests

```bash
kubectl apply -f deploy/kubernetes/ --namespace flowlens
```

### Step 5: Expose with Ingress

```yaml
# deploy/kubernetes/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: flowlens-ingress
  namespace: flowlens
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - flowlens.your-domain.com
      secretName: flowlens-tls
  rules:
    - host: flowlens.your-domain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: flowlens-frontend
                port:
                  number: 80
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Environment name |
| `DEBUG` | `true` | Enable debug mode |
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_USER` | `flowlens` | Database user |
| `POSTGRES_PASSWORD` | `flowlens` | Database password |
| `POSTGRES_DATABASE` | `flowlens` | Database name |
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |
| `API_WORKERS` | `4` | Uvicorn workers |
| `AUTH_ENABLED` | `true` | Enable authentication |
| `AUTH_SECRET_KEY` | (required) | JWT secret key |
| `INGESTION_NETFLOW_PORT` | `2055` | NetFlow UDP port |
| `INGESTION_SFLOW_PORT` | `6343` | sFlow UDP port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `json` | Log format (json/console) |

### Configuring Flow Sources

Point your network devices to send flow data:

| Protocol | Port | Notes |
|----------|------|-------|
| NetFlow v5 | UDP 2055 | Legacy, widely supported |
| NetFlow v9 | UDP 2055 | Template-based |
| IPFIX | UDP 2055 | NetFlow v10 |
| sFlow | UDP 6343 | Sampled flow |

Example Cisco configuration:

```
ip flow-export destination <flowlens-ip> 2055
ip flow-export version 9
ip flow-cache timeout active 1
```

---

## Troubleshooting

### Common Issues

#### Database Connection Failed

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Test connection
docker compose exec postgres psql -U flowlens -c '\l'
```

#### API Not Starting

```bash
# Check API logs
docker compose logs api

# Verify migrations ran
docker compose logs migrations

# Restart API
docker compose restart api
```

#### Frontend Can't Connect to API

```bash
# Check API is healthy
curl http://localhost:8000/admin/health/live

# Check frontend logs
docker compose logs frontend

# Verify nginx config
docker compose exec frontend cat /etc/nginx/conf.d/default.conf
```

#### No Flow Data Appearing

```bash
# Check ingestion service
docker compose logs ingestion

# Test UDP port is open
nc -vzu localhost 2055

# Generate test flows (requires softflowd)
softflowd -n localhost:2055 -i eth0
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api

# With timestamps
docker compose logs -f --timestamps api

# Last 100 lines
docker compose logs --tail=100 api
```

### Health Checks

```bash
# API health
curl http://localhost:8000/admin/health/live
curl http://localhost:8000/admin/health/ready

# Prometheus metrics
curl http://localhost:8000/admin/metrics

# Database stats
curl http://localhost:8000/admin/stats
```

### Reset Everything

```bash
# Stop all services
docker compose down

# Remove volumes (WARNING: deletes all data)
docker compose down -v

# Rebuild and start fresh
docker compose up -d --build
```

---

## Support

- **Documentation**: See `/docs` directory
- **Issues**: https://github.com/your-org/flowlens/issues
- **Logs**: Always include relevant logs when reporting issues
