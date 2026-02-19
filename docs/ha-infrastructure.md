# High-Availability Infrastructure Guide

## PostgreSQL HA

### Option 1: Managed Service (Recommended)
Use **RDS Multi-AZ**, **Cloud SQL HA**, or **Azure Database for PostgreSQL — Flexible Server**.

Set in Helm values:
```yaml
postgres:
  enabled: false  # Disable in-cluster Postgres

backend:
  env:
    DATABASE_URL: "postgresql+asyncpg://aegis:PASSWORD@your-rds-endpoint:5432/aegis"
    DATABASE_READ_URL: "postgresql+asyncpg://aegis:PASSWORD@your-read-replica:5432/aegis"
```

### Option 2: Patroni Cluster (Self-Managed)
Deploy a 3-node Patroni cluster with etcd for consensus:

```bash
helm repo add patroni https://charts.patroni.dev
helm install pg-ha patroni/patroni \
  --set replicas=3 \
  --set persistentVolume.size=50Gi
```

---

## Redis HA

### Option 1: Managed Service
Use **ElastiCache for Redis** (cluster mode) or **Azure Cache for Redis** (Premium tier).

### Option 2: Redis Sentinel (Self-Managed)
AEGIS supports Redis Sentinel natively. Set:
```env
REDIS_SENTINEL_HOSTS=sentinel1:26379,sentinel2:26379,sentinel3:26379
REDIS_SENTINEL_MASTER=mymaster
```

The `redis_client.py` auto-detects Sentinel configuration and uses `aioredis.Sentinel`.

---

## Kubernetes Considerations

| Component | Minimum Replicas | Pod Disruption Budget |
|-----------|-----------------|----------------------|
| Backend   | 2               | minAvailable: 1      |
| Frontend  | 2               | minAvailable: 1      |
| PostgreSQL| 1 (or managed)  | N/A                  |
| Redis     | 1 (or managed)  | N/A                  |
| OPA       | 1               | N/A                  |

### Autoscaling
HPA is pre-configured in the Helm chart:
- **Scale up** at 70% CPU or 80% memory
- **Min 2 / Max 10** replicas for backend

### Topology Spread
Add to `values.yaml` for multi-zone spread:
```yaml
backend:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
```

---

## Backup & Recovery

| What      | How                                                  | Frequency  |
|-----------|------------------------------------------------------|------------|
| PostgreSQL| `pg_dump` via CronJob or managed service snapshots   | Daily      |
| Redis     | AOF + RDB snapshots                                  | Continuous |
| OPA Policies | Git repository (source of truth)                 | On change  |

The existing `backup` service in `docker-compose.yml` handles PostgreSQL backups with 7-day retention.
