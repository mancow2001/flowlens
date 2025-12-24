# FlowLens

**Application Dependency Mapping Platform**

FlowLens is a production-ready, Python-based Application Dependency Mapping (ADM) platform. It ingests network flow data (NetFlow v5/v9, IPFIX, sFlow), automatically discovers assets and their relationships, and provides a comprehensive REST API and web UI for visualization and analysis.

## Features

- **Automatic Discovery**: Discovers assets and dependencies from network flow data
- **Multiple Flow Protocols**: Supports NetFlow v5/v9, IPFIX, and sFlow
- **Real-time Updates**: WebSocket support for live topology updates
- **Graph Analysis**: Impact analysis, blast radius, SPOF detection
- **Alerting**: Change detection with email notifications
- **REST API**: Full-featured API with OpenAPI documentation
- **Web UI**: React-based dashboard with topology visualization

## Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/flowlens.git
cd flowlens

# Create environment file
cp .env.example .env
echo "AUTH_SECRET_KEY=$(openssl rand -hex 32)" >> .env

# Start with Docker Compose
docker compose up -d

# Access the UI
open http://localhost:3000
```

## Documentation

- [Deployment Guide](DEPLOYMENT.md)
- [API Documentation](http://localhost:8000/docs) (when running)
- [Architecture](docs/architecture/)

## Requirements

- Python 3.11+
- PostgreSQL 15+
- Node.js 20+ (for frontend development)

## License

MIT License
