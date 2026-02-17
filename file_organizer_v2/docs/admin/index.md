# Administrator Guide

Complete guide for deploying, configuring, and maintaining File Organizer.

## Quick Start

### Docker Deployment (Recommended)

```bash
git clone https://github.com/curdriceaurora/Local-File-Organizer.git
cd Local-File-Organizer
docker-compose up -d
```

Access at `http://localhost:8000`

See [Installation Guide](installation.md) for detailed setup.

## Main Sections

### Deployment

- [Installation Guide](installation.md) - Setup and system requirements
- [Deployment Guide](deployment.md) - Production deployment and configuration
- [Configuration](configuration.md) - Environment variables and settings

### Operations

- [Monitoring & Maintenance](monitoring.md) - Health checks and logs
- [Security](security.md) - Authentication and secure deployment
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

## Key Topics

### Installation

- System requirements
- Docker setup
- Manual installation
- AI model configuration

### Deployment

- Docker Compose setup
- Reverse proxy configuration (nginx, Apache)
- SSL/TLS setup
- Environment variables

### Configuration

- Database setup (PostgreSQL)
- Redis configuration
- Ollama integration
- File upload limits
- Rate limiting

### Monitoring

- Health check endpoints
- Logging configuration
- Metrics collection
- Performance monitoring

### Security

- User authentication
- API key management
- HTTPS/TLS configuration
- Firewall rules

### Backup & Recovery

- Database backups
- File backups
- Restoration procedures
- Disaster recovery

## System Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP/WebSocket
┌──────▼──────────────────┐
│    FastAPI Web Server   │
│    (Python)             │
│    - REST API           │
│    - WebSocket          │
└──────┬──────────────────┘
       │
       ├─► PostgreSQL Database
       ├─► Redis Cache
       └─► Ollama (AI Models)

File System Storage
```

## Installation Steps

1. **Install Docker** (if using Docker)
1. **Clone Repository**
1. **Configure Environment** (copy .env.example to .env)
1. **Start Services** (docker-compose up)
1. **Configure Settings** (web interface)

See [Installation Guide](installation.md) for details.

## Configuration Checklist

- [ ] System meets minimum requirements
- [ ] Docker/Python installed
- [ ] Ollama models pulled
- [ ] PostgreSQL database running
- [ ] Redis cache running
- [ ] Environment variables set
- [ ] File upload limits configured
- [ ] Security settings configured
- [ ] Backups scheduled

## Monitoring Checklist

- [ ] Health checks passing
- [ ] Logs monitored
- [ ] Disk space monitored
- [ ] CPU/Memory usage normal
- [ ] Database health checked
- [ ] API response times acceptable
- [ ] Backups verified

## Maintenance Schedule

### Daily

- Check health endpoints
- Review error logs
- Monitor disk space

### Weekly

- Review user activity logs
- Check backup integrity
- Verify API performance

### Monthly

- Full system backup
- Review security logs
- Test restoration procedures
- Update documentation

### Quarterly

- Update AI models if available
- Security audit
- Performance optimization
- Capacity planning

## Common Tasks

### Start/Stop Services

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f web

# Restart service
docker-compose restart web
```

### Database Maintenance

```bash
# Backup database
docker-compose exec db pg_dump -U postgres file_organizer > backup.sql

# Restore database
docker-compose exec -T db psql -U postgres file_organizer < backup.sql
```

### View Configuration

```bash
# Check current environment
docker-compose config

# View logs
docker-compose logs --tail=100 web
```

## Troubleshooting

### Common Issues

**Services won't start**

- Check Docker running
- Review error logs
- Verify port availability

**Out of memory**

- Check resource limits
- Review running processes
- Increase RAM allocation

**Database connection failed**

- Verify PostgreSQL running
- Check connection string
- Review database logs

See [Troubleshooting Guide](troubleshooting.md) for solutions.

## Upgrade Procedure

1. Backup database and files
1. Pull latest code
1. Review release notes
1. Update Docker images
1. Run migrations
1. Test thoroughly
1. Deploy to production

## Support

- **Documentation**: Full guides for each topic
- **Issues**: [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)

## Next Steps

- [Installation Guide](installation.md)
- [Deployment Guide](deployment.md)
- [Configuration Guide](configuration.md)
- [Monitoring Guide](monitoring.md)
