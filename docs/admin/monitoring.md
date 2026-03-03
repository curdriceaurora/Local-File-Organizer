# Monitoring & Maintenance Guide

## Health Checks

### API Health Endpoints

```bash
# Overall health
curl http://localhost:8000/api/v1/health

# Database health
curl http://localhost:8000/api/v1/health/db

# Cache health
curl http://localhost:8000/api/v1/health/cache

# Ollama model availability
curl http://localhost:8000/api/v1/health/models
```

### Response Format

```json
{
  "status": "healthy",
  "timestamp": "2026-02-17T10:30:00Z",
  "components": {
    "database": "connected",
    "cache": "connected",
    "ollama": "available"
  }
}
```

## Logging

### Log Locations

- **Application**: `/var/log/file-organizer/app.log`
- **Database**: `/var/log/file-organizer/db.log`
- **Ollama**: `/var/log/file-organizer/ollama.log`

### Log Levels

- `DEBUG` - Detailed debug information
- `INFO` - General information
- `WARNING` - Warning messages
- `ERROR` - Error messages
- `CRITICAL` - Critical failures

### Viewing Logs

```bash
# Docker logs
docker-compose logs -f web

# File logs
tail -f /var/log/file-organizer/app.log

# Filtered logs
grep "ERROR" /var/log/file-organizer/app.log
```

## Performance Monitoring

### Metrics to Monitor

- **API Response Time**: Average response time per endpoint
- **Database Queries**: Query execution time and count
- **Ollama Response Time**: Model inference time
- **Cache Hit Rate**: Cache effectiveness
- **Disk Usage**: File storage utilization
- **Memory Usage**: Application memory consumption
- **CPU Usage**: Processor utilization

### Prometheus Metrics

```text
# Request metrics
file_organizer_requests_total{method="GET",status="200"}
file_organizer_request_duration_seconds{endpoint="/api/v1/files"}

# System metrics
file_organizer_disk_usage_bytes
file_organizer_memory_usage_bytes
file_organizer_cpu_usage_percent
```

## Database Maintenance

### Backups

```bash
# Full backup
pg_dump -h localhost -U user file_organizer > backup.sql

# Compressed backup
pg_dump -h localhost -U user file_organizer | gzip > backup.sql.gz

# Restore from backup
psql -h localhost -U user file_organizer < backup.sql
```

### Database Optimization

```bash
# Vacuum and analyze
VACUUM ANALYZE;

# Index maintenance
REINDEX INDEX index_name;

# Monitor connections
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;
```

## Redis Cache Maintenance

```bash
# Check Redis status
redis-cli ping

# Monitor Redis commands
redis-cli monitor

# Clear cache
redis-cli FLUSHDB

# Check memory usage
redis-cli INFO memory
```

## Ollama Model Management

```bash
# List running models
ollama ps

# Pull models
ollama pull qwen2.5:3b-instruct-q4_K_M

# Remove models
ollama rm model_name

# Check disk usage
du -sh ~/.ollama/
```

## Common Maintenance Tasks

### Weekly

- Review error logs for patterns
- Check disk space usage
- Verify backup completion
- Monitor cache performance

### Monthly

- Database optimization (VACUUM, ANALYZE)
- Review slow queries
- Check for unused indices
- Update security patches

### Quarterly

- Full system health assessment
- Performance trend analysis
- Capacity planning review
- Security audit

## Troubleshooting

### High Memory Usage

- Check for memory leaks in logs
- Restart Ollama models
- Clear cache: `redis-cli FLUSHDB`
- Increase available memory

### High CPU Usage

- Monitor active processes
- Check for slow queries
- Optimize database indices
- Reduce concurrent workers

### Database Connection Errors

- Verify database connectivity
- Check connection pool status
- Review database logs
- Increase connection pool size

## See Also

- [Configuration Guide](configuration.md)
- [Deployment Guide](deployment.md)
- [Troubleshooting Guide](troubleshooting.md)
