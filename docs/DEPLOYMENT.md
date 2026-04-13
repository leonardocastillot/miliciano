# Miliciano Deployment Guide

Deployment options for Miliciano in different environments.

---

## Docker Deployment

### Quick Start

```bash
# Clone repository
git clone https://github.com/milytics/miliciano.git
cd miliciano

# Create .env file with API keys
cp .env.example .env
nano .env  # Add your API keys

# Start with Docker Compose
docker-compose up -d

# Check status
docker-compose logs -f miliciano
```

### Docker Compose Configuration

**Environment variables** (`.env` file):
```bash
# Required API keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional configuration
NEMOCLAW_POLICY_MODE=enforce
MILICIANO_DEBUG=0
MILICIANO_PORT=8765

# Paths
OBSIDIAN_VAULT_PATH=./data/vault
MILICIANO_LOGS_PATH=./logs
```

**Start services**:
```bash
# Start in background
docker-compose up -d

# Start with logs
docker-compose up

# Stop services
docker-compose down

# Restart services
docker-compose restart
```

**Access container**:
```bash
# Interactive shell
docker-compose exec miliciano bash

# Run miliciano commands
docker-compose exec miliciano miliciano status
docker-compose exec miliciano miliciano think "test query"
```

---

## Standalone Docker

### Build Image

```bash
# Build from source
docker build -t miliciano:latest .

# Or pull from registry (when available)
docker pull ghcr.io/milytics/miliciano:latest
```

### Run Container

```bash
# Basic run
docker run -it --rm \
  -e OPENAI_API_KEY=sk-... \
  miliciano:latest think "Hello"

# With persistent volumes
docker run -d \
  --name miliciano \
  -e OPENAI_API_KEY=sk-... \
  -v miliciano-config:/home/miliciano/.config/miliciano \
  -v miliciano-hermes:/home/miliciano/.hermes \
  -v miliciano-openclaw:/home/miliciano/.openclaw \
  -p 8765:8765 \
  miliciano:latest shell

# With local Obsidian vault
docker run -d \
  --name miliciano \
  -e OPENAI_API_KEY=sk-... \
  -v ~/Documents/Obsidian\ Vault:/data/vault \
  -p 8765:8765 \
  miliciano:latest shell
```

---

## Production Deployment

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 2GB RAM minimum (4GB recommended)
- Network access to API providers

### Production Configuration

**docker-compose.prod.yml**:
```yaml
version: '3.8'

services:
  miliciano:
    image: ghcr.io/milytics/miliciano:latest
    restart: always
    
    environment:
      - NEMOCLAW_POLICY_MODE=enforce
      - MILICIANO_DEBUG=0
    
    env_file:
      - .env.production
    
    volumes:
      - /var/lib/miliciano/config:/home/miliciano/.config/miliciano
      - /var/lib/miliciano/hermes:/home/miliciano/.hermes
      - /var/lib/miliciano/openclaw:/home/miliciano/.openclaw
      - /var/log/miliciano:/home/miliciano/.config/miliciano/logs
    
    ports:
      - "127.0.0.1:8765:8765"  # Only localhost
    
    security_opt:
      - no-new-privileges:true
    
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2048M
        reservations:
          cpus: '0.5'
          memory: 512M
    
    healthcheck:
      test: ["CMD", "miliciano", "status", "--json"]
      interval: 30s
      timeout: 10s
      start_period: 60s
      retries: 3
    
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
```

**Start production**:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## Kubernetes Deployment

### Deployment Manifest

**k8s/deployment.yaml**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: miliciano
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: miliciano
  template:
    metadata:
      labels:
        app: miliciano
    spec:
      containers:
      - name: miliciano
        image: ghcr.io/milytics/miliciano:latest
        ports:
        - containerPort: 8765
          name: http
        env:
        - name: NEMOCLAW_POLICY_MODE
          value: "enforce"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: miliciano-secrets
              key: openai-api-key
        volumeMounts:
        - name: config
          mountPath: /home/miliciano/.config/miliciano
        - name: logs
          mountPath: /home/miliciano/.config/miliciano/logs
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          exec:
            command:
            - miliciano
            - status
            - --json
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
            - miliciano
            - status
            - --json
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: config
        persistentVolumeClaim:
          claimName: miliciano-config
      - name: logs
        persistentVolumeClaim:
          claimName: miliciano-logs
---
apiVersion: v1
kind: Service
metadata:
  name: miliciano
spec:
  selector:
    app: miliciano
  ports:
  - port: 8765
    targetPort: 8765
    name: http
  type: ClusterIP
```

**Secrets**:
```bash
kubectl create secret generic miliciano-secrets \
  --from-literal=openai-api-key=sk-...
```

**Deploy**:
```bash
kubectl apply -f k8s/deployment.yaml
```

---

## Health Monitoring

### Health Check Endpoint

```bash
# HTTP health check
curl http://localhost:8765/health

# Response (healthy)
{
  "timestamp": "2026-04-10T20:00:00Z",
  "healthy": true,
  "components": {
    "hermes": {"status": "healthy"},
    "openclaw": {"status": "healthy"},
    "nemoclaw": {"status": "healthy"}
  }
}
```

### Container Health

```bash
# Docker health status
docker inspect --format='{{.State.Health.Status}}' miliciano

# Logs
docker logs miliciano --tail 50
```

### Monitoring Logs

```bash
# Follow JSON logs
docker exec miliciano tail -f ~/.config/miliciano/logs/miliciano.log | jq .

# Audit trail
docker exec miliciano tail -f ~/.config/miliciano/audit.log | jq .
```

---

## Troubleshooting

### Container Won't Start

**Check logs**:
```bash
docker-compose logs miliciano
```

**Common issues**:
1. Missing API keys → Check `.env` file
2. Port 8765 in use → Change `MILICIANO_PORT`
3. Permission issues → Check volume ownership

**Fix permissions**:
```bash
docker-compose exec miliciano chown -R miliciano:miliciano /home/miliciano
```

### Health Check Failing

**Debug**:
```bash
# Check health manually
docker exec miliciano miliciano status --json

# Check component status
docker exec miliciano hermes profile list
docker exec miliciano openclaw health
```

### Performance Issues

**Check resource usage**:
```bash
docker stats miliciano
```

**Increase limits** in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'
      memory: 4096M
```

---

## Security Hardening

### Production Checklist

- [ ] Use secrets management (not .env files in production)
- [ ] Run as non-root user (default in Dockerfile)
- [ ] Enable policy enforcement: `NEMOCLAW_POLICY_MODE=enforce`
- [ ] Restrict network access (firewall rules)
- [ ] Enable audit logging
- [ ] Regular security scans
- [ ] Keep base image updated

### Docker Security

**Run with security options**:
```bash
docker run \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  --read-only \
  --tmpfs /tmp \
  miliciano:latest
```

**Network isolation**:
```yaml
# docker-compose.yml
services:
  miliciano:
    networks:
      - miliciano-internal
    
networks:
  miliciano-internal:
    driver: bridge
    internal: false
```

---

## Backup and Recovery

### Backup Configuration

```bash
# Backup volumes
docker run --rm \
  -v miliciano-config:/data \
  -v $(pwd):/backup \
  ubuntu tar czf /backup/miliciano-config.tar.gz /data

# Backup logs
docker exec miliciano tar czf /tmp/logs.tar.gz ~/.config/miliciano/logs
docker cp miliciano:/tmp/logs.tar.gz ./miliciano-logs-$(date +%Y%m%d).tar.gz
```

### Restore Configuration

```bash
# Restore volumes
docker run --rm \
  -v miliciano-config:/data \
  -v $(pwd):/backup \
  ubuntu tar xzf /backup/miliciano-config.tar.gz -C /
```

---

## Scaling

### Multiple Instances

**Load balancer** (nginx):
```nginx
upstream miliciano {
    server miliciano-1:8765;
    server miliciano-2:8765;
    server miliciano-3:8765;
}

server {
    listen 80;
    location / {
        proxy_pass http://miliciano;
    }
}
```

**Shared volumes**:
```yaml
volumes:
  shared-config:
    driver: nfs
    driver_opts:
      share: "nfs-server:/miliciano"
```

---

**Version**: 0.3.0  
**Last Updated**: 2026-04-10
